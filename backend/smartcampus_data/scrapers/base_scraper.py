"""Shared, polite scraper engine for official SmartCampus sources.

Rules enforced here:
- robots.txt is checked before every resource;
- only public same-domain pages/brochures from sources.yaml are requested;
- retries are limited and a configurable delay is applied between requests;
- raw HTML/PDF bytes and metadata are preserved;
- missing values stay empty, never inferred or invented.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import settings
from processors.cleaner import (
    clean_text,
    deserialize_list,
    excerpt,
    normalize_key,
    normalize_url,
    same_site,
    serialize_list,
)
from processors.normalizer import (
    count_semesters,
    derive_interest_tags,
    detect_language,
    extract_description,
    extract_fee_rows,
    extract_value,
    formation_name_from_doc,
    make_formation_id,
    normalize_degree_type,
    normalize_language,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime(settings.DATE_FORMAT)


def short_hash(value: str, length: int = 12) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


PDF_RELEVANT_KEYWORDS = (
    "brochure", "guide", "programme", "program", "plan", "admission",
    "criteres", "critères", "licence", "master", "mastère", "lba", "mmd",
)
NON_PAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".css", ".js", ".doc", ".docx", ".xls", ".xlsx", ".zip")


@dataclass
class FetchedDocument:
    document_id: str
    establishment_id: str
    url: str
    document_type: str
    title: str
    text: str
    raw_path: str
    metadata_path: str
    sha256: str
    byte_size: int
    status_code: int
    content_type: str
    language: str
    collection_date: str
    html_lang: str = ""
    parent_url: str = ""
    role: str = ""
    page_texts: list[tuple[int, str]] = field(default_factory=list)
    parse_status: str = "ok"
    error: str = ""
    soup: Any = None


class BaseScraper:
    establishment_id = "BASE"

    def __init__(self, config: dict[str, Any], defaults: dict[str, Any], dry_run: bool = False):
        self.config = config
        self.defaults = defaults
        self.dry_run = dry_run
        self.base_url = config["base_url"]
        self.raw_dir = settings.RAW_DIR / self.establishment_id
        self.html_dir = self.raw_dir / "html"
        self.pdf_dir = self.raw_dir / "pdf"
        self.meta_dir = self.raw_dir / "meta"
        if not dry_run:
            for directory in (self.html_dir, self.pdf_dir, self.meta_dir):
                directory.mkdir(parents=True, exist_ok=True)

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": settings.USER_AGENT, "Accept-Language": "fr,en;q=0.8"})
        retry = Retry(
            total=int(defaults.get("max_retries", settings.MAX_RETRIES)),
            backoff_factor=settings.RETRY_BACKOFF_FACTOR,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        self.robots = RobotFileParser()
        self.robots.set_url(f"{self.base_url}/robots.txt")
        self.robots_available = False
        self.robots_notes: list[str] = []

        self.documents: list[FetchedDocument] = []
        self._documents_by_url: dict[str, FetchedDocument] = {}
        self._seen_urls: set[str] = set()
        self._pdf_urls: set[str] = set()
        self.http_errors: list[dict] = []
        self.parsing_errors: list[dict] = []
        self._last_request_at = 0.0
        self._delay = float(defaults.get("delay_seconds", settings.REQUEST_DELAY_SECONDS))

    # ------------------------------------------------------------------ HTTP
    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self._delay:
            time.sleep(self._delay - elapsed)
        self._last_request_at = time.monotonic()

    def _request(self, url: str, stream: bool = False) -> requests.Response | None:
        self._throttle()
        try:
            response = self.session.get(
                url,
                timeout=int(self.defaults.get("request_timeout", settings.REQUEST_TIMEOUT)),
                stream=stream,
                allow_redirects=True,
            )
            return response
        except requests.RequestException as exc:
            self.http_errors.append({"url": url, "error": clean_text(str(exc))})
            return None

    def _load_robots(self) -> None:
        self._throttle()
        try:
            response = self.session.get(
                f"{self.base_url}/robots.txt",
                timeout=int(self.defaults.get("request_timeout", settings.REQUEST_TIMEOUT)),
            )
            if response.status_code == 200 and response.text.strip():
                self.robots.parse(response.text.splitlines())
                self.robots_available = True
            else:
                self.robots_notes.append(
                    f"robots.txt indisponible (HTTP {response.status_code}) ; aucune autorisation supplémentaire supposée."
                )
        except requests.RequestException as exc:
            self.robots_notes.append(f"robots.txt non consultable : {clean_text(str(exc))}")

    def _allowed(self, url: str) -> bool:
        if not self.robots_available:
            return True
        return bool(self.robots.can_fetch(settings.USER_AGENT, url))

    def _pattern_match(self, url: str, patterns: list[str]) -> bool:
        return any(pattern in url for pattern in patterns)

    @staticmethod
    def _clean_link(url: str) -> bool:
        """Reject anchors built from plain text (addresses) and binary assets."""
        path = unquote(urlparse(url).path)
        if not path or len(path) > 220:
            return False
        if any(character.isspace() for character in path):
            return False
        if path.lower().endswith(NON_PAGE_EXTENSIONS):
            return False
        return True

    @staticmethod
    def _relevant_pdf(url: str, anchor_text: str = "") -> bool:
        context = f"{anchor_text} {unquote(urlparse(url).path)}".lower()
        return any(keyword in context for keyword in PDF_RELEVANT_KEYWORDS)

    def _excluded(self, url: str) -> bool:
        patterns = self.defaults.get("url_exclude_patterns", []) + self.config.get("url_exclude_patterns", [])
        return self._pattern_match(url, [str(pattern) for pattern in patterns])

    def _is_formation_url(self, url: str) -> bool:
        return self._pattern_match(url, [str(p) for p in self.config.get("formation_url_patterns", [])])

    def _is_relevant(self, url: str) -> bool:
        if not normalize_url(url) or not same_site(url, self.base_url) or self._excluded(url):
            return False
        if not self._clean_link(url):
            return False
        if self._is_formation_url(url):
            return True
        includes = self.defaults.get("url_include_patterns", []) + self.config.get("url_include_patterns", [])
        return self._pattern_match(url, [str(pattern) for pattern in includes])

    def _role_for(self, url: str) -> str:
        if self._is_formation_url(url):
            return "formation"
        if any(normalize_url(url) == normalize_url(item) for item in self.config.get("extra_urls", [])):
            return "establishment"
        if any(normalize_url(url) == normalize_url(item) for item in self.config.get("catalog_urls", [])):
            return "catalog"
        return "support"

    # -------------------------------------------------------------- fetching
    def _file_name(self, url: str, extension: str) -> str:
        path = normalize_key(urlparse(url).path)[:70] or "index"
        return f"{path}-{short_hash(url, 8)}.{extension}"

    def fetch(self, url: str, parent_url: str = "") -> FetchedDocument | None:
        url = normalize_url(url)
        if not url:
            return None
        if url in self._documents_by_url:
            return self._documents_by_url[url]
        if not same_site(url, self.base_url):
            self.http_errors.append({"url": url, "error": "Hors domaine officiel configuré"})
            return None
        if not self._allowed(url):
            self.http_errors.append({"url": url, "error": "Refusé par robots.txt"})
            return None

        looks_like_pdf = ".pdf" in urlparse(url).path.lower() or ".pdf" in urlparse(url).query.lower()
        response = self._request(url, stream=looks_like_pdf)
        if response is None:
            return None
        if response.status_code != 200:
            self.http_errors.append({"url": url, "error": f"HTTP {response.status_code}"})
            response.close()
            return None

        content_type = clean_text(response.headers.get("Content-Type", "")).split(";")[0]
        is_pdf = looks_like_pdf or "pdf" in content_type.lower()
        if response.status_code == 200 and not is_pdf:
            content = response.content
        else:
            content = response.raw.read(settings.MAX_PDF_BYTES + 1, decode_content=True) if looks_like_pdf else response.content
        response.close()

        if is_pdf and len(content) > settings.MAX_PDF_BYTES:
            self.http_errors.append({"url": url, "error": "PDF au-delà de la limite de taille configurée"})
            return None
        if not content:
            self.parsing_errors.append({"url": url, "error": "Contenu vide"})
            return None

        doc_id = f"doc-{self.establishment_id}-{short_hash(url)}"
        sha = hashlib.sha256(content).hexdigest()
        collected_at = utc_now()
        html_lang = ""
        page_texts: list[tuple[int, str]] = []
        parse_status = "ok"
        parse_error = ""
        soup = None

        if is_pdf:
            extension = "pdf"
            raw_path = self.pdf_dir / self._file_name(url, extension)
            try:
                reader = PdfReader(io.BytesIO(content))
                if reader.is_encrypted:
                    raise ValueError("PDF protégé : aucun contenu privé ne sera traité")
                for index, page in enumerate(reader.pages, start=1):
                    page_text = clean_text(page.extract_text() or "")
                    if page_text:
                        page_texts.append((index, page_text))
                text = "\n".join(f"# Page {number}\n{content_text}" for number, content_text in page_texts)
                title = Path(urlparse(url).path).name.replace("-", " ").replace("_", " ").strip()
            except Exception as exc:  # noqa: BLE001 - reported explicitly, never fabricated
                parse_status = "error"
                parse_error = clean_text(str(exc))
                self.parsing_errors.append({"url": url, "error": parse_error})
                text = ""
                title = Path(urlparse(url).path).name
        else:
            extension = "html"
            raw_path = self.html_dir / self._file_name(url, extension)
            try:
                soup = BeautifulSoup(content, "lxml")
                title_tag = soup.find("title")
                title = clean_text(title_tag.get_text(" ", strip=True)) if title_tag else url
                html_tag = soup.find("html")
                html_lang = str(html_tag.get("lang", "")) if html_tag else ""
                from processors.cleaner import soup_to_text

                text = soup_to_text(soup)
            except Exception as exc:  # noqa: BLE001
                parse_status = "error"
                parse_error = clean_text(str(exc))
                self.parsing_errors.append({"url": url, "error": parse_error})
                text = ""
                title = url
                soup = None

        raw_relative = ""
        meta_relative = ""
        if not self.dry_run:
            raw_path.write_bytes(content)
            meta = {
                "document_id": doc_id,
                "url": url,
                "parent_url": parent_url,
                "final_url": response.url,
                "http_status": response.status_code,
                "content_type": content_type,
                "sha256": sha,
                "byte_size": len(content),
                "collection_date": collected_at,
                "raw_path": str(raw_path.relative_to(settings.PROJECT_ROOT)),
                "title": title,
                "language": detect_language(text, html_lang),
                "source_type": "pdf" if is_pdf else "html",
            }
            meta_path = self.meta_dir / f"{raw_path.stem}.json"
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            raw_relative = str(raw_path.relative_to(settings.PROJECT_ROOT))
            meta_relative = str(meta_path.relative_to(settings.PROJECT_ROOT))

        document = FetchedDocument(
            document_id=doc_id,
            establishment_id=self.establishment_id,
            url=url,
            document_type="pdf" if is_pdf else "html",
            title=title,
            text=text,
            raw_path=raw_relative,
            metadata_path=meta_relative,
            sha256=sha,
            byte_size=len(content),
            status_code=response.status_code,
            content_type=content_type,
            language=detect_language(text, html_lang),
            collection_date=collected_at,
            html_lang=html_lang,
            parent_url=parent_url,
            role=self._role_for(url),
            page_texts=page_texts,
            parse_status=parse_status,
            error=parse_error,
            soup=soup,
        )
        self.documents.append(document)
        self._documents_by_url[url] = document
        return document

    def _sitemap_urls(self) -> list[str]:
        urls: list[str] = []
        for sitemap in self.config.get("sitemaps", []):
            sitemap = normalize_url(sitemap)
            response = self._request(sitemap)
            if response is None or response.status_code != 200:
                if response is not None:
                    self.http_errors.append({"url": sitemap, "error": f"HTTP {response.status_code}"})
                continue
            xml = response.text
            urls.extend(normalize_url(value) for value in re.findall(r"<loc>\s*([^<]+)\s*</loc>", xml))
        return [url for url in dict.fromkeys(urls) if url and self._is_relevant(url)]

    # -------------------------------------------------------------- crawling
    def discover(self) -> None:
        self._load_robots()
        seeds: list[str] = []
        for url in self.config.get("catalog_urls", []) + self.config.get("extra_urls", []) + [self.base_url]:
            normalized = normalize_url(url)
            if normalized and normalized not in seeds:
                seeds.append(normalized)
        for url in self._sitemap_urls():
            if url not in seeds:
                seeds.append(url)

        max_pages = int(self.defaults.get("max_pages", settings.MAX_PAGES_PER_SITE))
        max_pdfs = int(self.defaults.get("max_pdfs", settings.MAX_PDFS_PER_SITE))
        max_depth = int(self.defaults.get("max_depth", settings.MAX_CRAWL_DEPTH))
        queue = deque((url, 0) for url in seeds)
        html_count = 0

        while queue and html_count < max_pages:
            url, depth = queue.popleft()
            if url in self._seen_urls:
                continue
            self._seen_urls.add(url)
            document = self.fetch(url)
            if document is None:
                continue
            if document.document_type == "pdf":
                continue
            html_count += 1
            if document.parse_status != "ok" or document.soup is None:
                continue

            for anchor in document.soup.find_all("a", href=True):
                href = normalize_url(anchor["href"], url)
                if not href or not same_site(href, self.base_url) or not self._allowed(href):
                    continue
                if ".pdf" in urlparse(href).path.lower():
                    anchor_text = anchor.get_text(" ", strip=True)
                    if (
                        self._clean_link(href)
                        and self._relevant_pdf(href, anchor_text)
                        and href not in self._pdf_urls
                        and len(self._pdf_urls) < max_pdfs
                    ):
                        self._pdf_urls.add(href)
                    continue
                if depth < max_depth and self._is_relevant(href) and href not in self._seen_urls:
                    queue.append((href, depth + 1))

        for pdf_url in sorted(self._pdf_urls):
            if len([doc for doc in self.documents if doc.document_type == "pdf"]) >= max_pdfs:
                break
            self.fetch(pdf_url)

    # -------------------------------------------------------------- planning
    def plan(self) -> dict:
        """Dry-run: verify configured URLs and list what would be collected."""
        self._load_robots()
        planned_pages: list[str] = []
        planned_pdfs: list[str] = []
        seen_pages: set[str] = set()
        seen_pdfs: set[str] = set()

        for url in self.config.get("catalog_urls", []) + self.config.get("extra_urls", []) + [self.base_url]:
            normalized = normalize_url(url)
            if not normalized or normalized in seen_pages:
                continue
            seen_pages.add(normalized)
            response = self._request(normalized)
            status = response.status_code if response else "erreur réseau"
            if response and response.status_code != 200:
                self.http_errors.append({"url": normalized, "error": f"HTTP {response.status_code}"})
            planned_pages.append(f"{normalized} [{status}]")
            if response and response.status_code == 200 and "html" in response.headers.get("Content-Type", ""):
                soup = BeautifulSoup(response.content, "lxml")
                for anchor in soup.find_all("a", href=True):
                    href = normalize_url(anchor["href"], normalized)
                    if not href or not same_site(href, self.base_url):
                        continue
                    if ".pdf" in urlparse(href).path.lower():
                        if (
                            self._clean_link(href)
                            and self._relevant_pdf(href, anchor.get_text(" ", strip=True))
                            and href not in seen_pdfs
                        ):
                            seen_pdfs.add(href)
                            planned_pdfs.append(href)
                    elif self._is_relevant(href) and href not in seen_pages:
                        seen_pages.add(href)
                        planned_pages.append(href)
        return {
            "establishment": self.establishment_id,
            "robots_available": self.robots_available,
            "robots_notes": self.robots_notes,
            "planned_pages": planned_pages[: int(self.defaults.get("max_pages", settings.MAX_PAGES_PER_SITE))],
            "planned_pdfs": planned_pdfs[: int(self.defaults.get("max_pdfs", settings.MAX_PDFS_PER_SITE))],
            "http_errors": self.http_errors,
        }

    # ------------------------------------------------------------- extraction
    def _establishment_document(self) -> FetchedDocument | None:
        for document in self.documents:
            if document.role == "establishment" and document.document_type == "html" and document.parse_status == "ok":
                return document
        return next((doc for doc in self.documents if doc.url.rstrip("/") == self.base_url.rstrip("/")), None)

    def _blocks_for(self, formation_doc: FetchedDocument, formation_name: str) -> list[dict]:
        tokens = [token for token in re.findall(r"\w+", formation_name.lower()) if len(token) > 4]
        blocks: list[dict] = [
            {
                "text": formation_doc.text,
                "url": formation_doc.url,
                "title": formation_doc.title,
                "priority": 0,
                "document_id": formation_doc.document_id,
                "source_type": formation_doc.document_type,
                "raw_path": formation_doc.raw_path,
            }
        ]
        for document in self.documents:
            if document is formation_doc or document.parse_status != "ok" or not document.text:
                continue
            if document.document_type == "pdf":
                related = document.parent_url == formation_doc.url or any(token in document.title.lower() for token in tokens)
                if not related:
                    continue
                priority = 1
            elif document.role == "establishment":
                priority = 2
            elif document.role == "catalog":
                priority = 3
            else:
                continue
            blocks.append(
                {
                    "text": document.text,
                    "url": document.url,
                    "title": document.title,
                    "priority": priority,
                    "document_id": document.document_id,
                    "source_type": document.document_type,
                    "raw_path": document.raw_path,
                }
            )
        return blocks

    def _contact_info(self) -> dict:
        text = "\n".join(doc.text for doc in self.documents if doc.role in {"establishment", "catalog"} and doc.parse_status == "ok")
        emails = []
        for candidate in re.findall(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text):
            if candidate.lower() not in [email.lower() for email in emails]:
                emails.append(candidate)
        preferred = [email for email in emails if email.lower().startswith(("info@", "contact@"))]
        phones = []
        for candidate in re.findall(r"\+?\s*216[\s().\-]?\d[\d\s().\-]{7,}\d", text):
            cleaned = clean_text(candidate)
            if cleaned not in phones:
                phones.append(cleaned)
        location_hits = re.findall(r"(?im)^.*(?:route de tunis|route mharza|campus group[ée] nau|cit[ée] el ons)[^\n]{0,120}$", text)
        return {
            "contact_email": (preferred or emails or [""])[0],
            "contact_phone": (phones or [""])[0],
            "campus_location": clean_text(location_hits[0]) if location_hits else "",
        }

    def _source_rows(self, attribute: str, result: dict, formation_id: str, origin: str = "official") -> dict | None:
        if not result.get("value"):
            return None
        # Resolve provenance from the exact document the value was read from.
        document = next(
            (doc for doc in self.documents if doc.document_id == result.get("document_id")),
            None,
        )
        source_type = document.document_type if document else "html"
        return {
            "source_id": f"src-{short_hash(formation_id + attribute + result.get('source_url', ''), 16)}",
            "etablissement_id": self.establishment_id,
            "formation_id": formation_id,
            "source_url": result.get("source_url", ""),
            "source_title": result.get("source_title", ""),
            "source_type": source_type,
            "attribute": attribute,
            "value_excerpt": excerpt(result.get("value"), 300),
            "raw_path": document.raw_path if document else "",
            "value_origin": origin,
            "document_language": result.get("language", "") or (document.language if document else ""),
            "collection_date": self.collection_date,
            "last_verified_at": "",
            "http_status": 200,
            "verification_status": "collected_unverified",
            "evidence_excerpt": result.get("evidence", ""),
        }

    def build_data(self) -> dict:
        self.collection_date = utc_now()
        formation_docs = [
            doc
            for doc in self.documents
            if doc.document_type == "html" and doc.parse_status == "ok" and doc.text
            and (self._is_formation_url(doc.url) or doc.role == "formation")
        ]

        candidates: list[tuple[FetchedDocument, str]] = []
        for document in formation_docs:
            name = formation_name_from_doc(
                document.title,
                document.text,
                [str(pattern) for pattern in self.config.get("formation_title_patterns", [])],
            )
            if name:
                candidates.append((document, clean_text(name)[:180]))

        # Keep the richest official page when two URLs describe the same formation.
        unique: dict[str, tuple[FetchedDocument, str]] = {}
        for document, name in sorted(candidates, key=lambda item: len(item[0].text), reverse=True):
            key = normalize_key(name)
            if key not in unique:
                unique[key] = (document, name)
        candidates = list(unique.values())

        tables: dict[str, list[dict]] = {
            "etablissements": [],
            "formations": [],
            "admissions": [],
            "programmes": [],
            "tarifs": [],
            "sources": [],
            "documents": [],
        }
        rag_documents: list[dict] = []
        missing_fields: dict[str, list[str]] = {}
        contact = self._contact_info()

        establishment_doc = self._establishment_document()
        tables["etablissements"].append(
            {
                "etablissement_id": self.establishment_id,
                "name": self.config["name"],
                "short_name": self.config.get("short_name", self.establishment_id),
                "country": self.config.get("country", ""),
                "city": self.config.get("city", ""),
                "website_url": self.base_url,
                "official_name_source_url": establishment_doc.url if establishment_doc else self.base_url,
                "contact_email": contact["contact_email"],
                "contact_phone": contact["contact_phone"],
                "campus_location": contact["campus_location"],
                "collection_date": self.collection_date,
                "document_language": establishment_doc.language if establishment_doc else "fr",
                "verification_status": "collected_unverified",
            }
        )

        formation_ids_by_url: dict[str, str] = {}
        formation_names_by_id: dict[str, str] = {}

        for formation_doc, formation_name in candidates:
            formation_id = make_formation_id(self.establishment_id, formation_name, formation_doc.url)
            if formation_id in formation_names_by_id:
                formation_id = f"{formation_id}-{short_hash(formation_doc.url, 6)}"
            formation_ids_by_url[formation_doc.url] = formation_id
            formation_names_by_id[formation_id] = formation_name
            blocks = self._blocks_for(formation_doc, formation_name)
            combined_text = "\n".join(block["text"] for block in blocks[:2])

            descriptors = [
                "field",
                "speciality",
                "duration_years",
                "language",
                "study_mode",
                "diploma_awarded",
                "required_baccalaureate",
                "minimum_grade",
                "required_level",
                "admission_method",
                "required_documents",
                "registration_period",
                "special_conditions",
                "admission_year",
                "subjects",
                "modules",
                "semester_count",
                "internships",
                "projects",
                "specializations",
                "skills_acquired",
                "career_opportunities",
                "further_studies",
                "career_field",
                "bridges",
                "recommended_profile",
                "prerequisite_skills",
            ]
            extracted: dict[str, dict] = {field_name: extract_value(field_name, blocks) for field_name in descriptors}
            description = extract_description(blocks, formation_name)
            extracted["description"] = description

            values: dict[str, Any] = {key: item["value"] for key, item in extracted.items()}
            formation_row = {
                "formation_id": formation_id,
                "etablissement_id": self.establishment_id,
                "formation_name": formation_name,
                "degree_type": normalize_degree_type(formation_name, formation_doc.text),
                "field": values["field"],
                "speciality": values["speciality"],
                "description": values["description"],
                "duration_years": values["duration_years"],
                "language": normalize_language(values["language"]) or formation_doc.language,
                "study_mode": values["study_mode"],
                "diploma_awarded": values["diploma_awarded"],
                "career_opportunities": values["career_opportunities"],
                "further_studies": values["further_studies"],
                "career_field": values["career_field"],
                "bridges": values["bridges"],
                "recommended_profile": values["recommended_profile"],
                "interest_tags": derive_interest_tags(combined_text),
                "interest_tags_origin": "derived_from_official_text_fixed_rules",
                "prerequisite_skills": values["prerequisite_skills"] or values["required_baccalaureate"],
                "source_url": formation_doc.url,
                "source_title": formation_doc.title,
                "source_type": "html",
                "collection_date": self.collection_date,
                "last_verified_at": "",
                "academic_year": values["admission_year"],
                "verification_status": "collected_unverified",
                "document_language": formation_doc.language,
            }
            tables["formations"].append(formation_row)

            admission_fields = (
                "required_baccalaureate",
                "minimum_grade",
                "required_level",
                "admission_method",
                "required_documents",
                "registration_period",
                "special_conditions",
                "admission_year",
            )
            admission_source = next(
                (extracted[name]["source_url"] for name in admission_fields if extracted[name]["source_url"]),
                establishment_doc.url if establishment_doc else formation_doc.url,
            )
            tables["admissions"].append(
                {
                    "admission_id": f"adm-{formation_id}",
                    "formation_id": formation_id,
                    "etablissement_id": self.establishment_id,
                    "required_baccalaureate": values["required_baccalaureate"],
                    "minimum_grade": values["minimum_grade"].replace(",", "."),
                    "required_level": values["required_level"],
                    "admission_method": values["admission_method"],
                    "required_documents": values["required_documents"],
                    "registration_period": values["registration_period"],
                    "special_conditions": values["special_conditions"],
                    "admission_year": values["admission_year"],
                    "source_url": admission_source,
                    "source_title": formation_doc.title,
                    "collection_date": self.collection_date,
                    "document_language": formation_doc.language,
                    "verification_status": "collected_unverified",
                }
            )

            programme_source = next(
                (extracted[name]["source_url"] for name in ("subjects", "modules", "skills_acquired") if extracted[name]["source_url"]),
                formation_doc.url,
            )
            semester_count = count_semesters(combined_text) or values["semester_count"]
            tables["programmes"].append(
                {
                    "programme_id": f"prg-{formation_id}",
                    "formation_id": formation_id,
                    "etablissement_id": self.establishment_id,
                    "subjects": values["subjects"],
                    "modules": values["modules"],
                    "semester_count": semester_count,
                    "internships": values["internships"],
                    "projects": values["projects"],
                    "specializations": values["specializations"],
                    "skills_acquired": values["skills_acquired"],
                    "source_url": programme_source,
                    "source_title": formation_doc.title,
                    "collection_date": self.collection_date,
                    "document_language": formation_doc.language,
                    "verification_status": "collected_unverified",
                }
            )

            fee_rows = extract_fee_rows(blocks)
            unique_fees: dict[tuple[Any, ...], dict] = {}
            for fee in fee_rows:
                key = (fee.get("fee_type"), fee.get("fee_scope"), fee.get("tuition_fee"), fee.get("registration_fee"), fee.get("fee_currency"))
                if key not in unique_fees:
                    unique_fees[key] = fee
            if not unique_fees:
                unique_fees[("not_published", "", None, None, "")] = {
                    "fee_type": "not_published",
                    "fee_scope": "",
                    "tuition_fee": None,
                    "registration_fee": None,
                    "fee_currency": "",
                    "fee_period": "",
                    "other_fees": "",
                    "evidence": "",
                    "source_url": admission_source,
                    "source_title": formation_doc.title,
                    "document_id": "",
                }
            for index, fee in enumerate(unique_fees.values(), start=1):
                published = any(isinstance(fee.get(key), (int, float)) for key in ("tuition_fee", "registration_fee"))
                tables["tarifs"].append(
                    {
                        "tarif_id": f"tar-{formation_id}-{index:02d}",
                        "formation_id": formation_id,
                        "etablissement_id": self.establishment_id,
                        "fee_type": fee.get("fee_type", ""),
                        "fee_scope": fee.get("fee_scope", ""),
                        "tuition_fee": fee.get("tuition_fee") or "",
                        "registration_fee": fee.get("registration_fee") or "",
                        "other_fees": fee.get("other_fees", ""),
                        "fee_currency": fee.get("fee_currency", ""),
                        "fee_period": fee.get("fee_period", ""),
                        "fee_academic_year": values["admission_year"],
                        "payment_terms": fee.get("other_fees", "") if fee.get("fee_type") == "practical_information" else "",
                        "campus_location": contact["campus_location"],
                        "contact_email": contact["contact_email"],
                        "contact_phone": contact["contact_phone"],
                        "fee_status": "published" if published else "not_published",
                        "source_url": fee.get("source_url", ""),
                        "source_title": fee.get("source_title", ""),
                        "collection_date": self.collection_date,
                        "document_language": formation_doc.language,
                        "verification_status": "collected_unverified",
                    }
                )

            for attribute, result in extracted.items():
                source_row = self._source_rows(attribute, {**result, "language": formation_doc.language}, formation_id)
                if source_row:
                    tables["sources"].append(source_row)
            if formation_row["interest_tags"]:
                tables["sources"].append(
                    {
                        "source_id": f"src-{short_hash(formation_id + 'interest_tags', 16)}",
                        "etablissement_id": self.establishment_id,
                        "formation_id": formation_id,
                        "source_url": formation_doc.url,
                        "source_title": formation_doc.title,
                        "source_type": "html",
                        "attribute": "interest_tags",
                        "value_excerpt": formation_row["interest_tags"],
                        "raw_path": "",
                        "value_origin": "derived_from_official_text_fixed_rules",
                        "document_language": formation_doc.language,
                        "collection_date": self.collection_date,
                        "last_verified_at": "",
                        "http_status": 200,
                        "verification_status": "derived_not_official_fact",
                        "evidence_excerpt": "Table de mots-clés déterministe appliquée au texte officiel collecté.",
                    }
                )
            for fee in fee_rows:
                source_row = self._source_rows(
                    "tarifs",
                    {
                        **fee,
                        "source_type": "pdf" if fee.get("source_url", "").endswith(".pdf") else "html",
                        "language": formation_doc.language,
                    },
                    formation_id,
                )
                if source_row:
                    tables["sources"].append(source_row)

            empty = [
                name
                for name in ("degree_type", "description", "duration_years", "language", "required_baccalaureate", "subjects", "career_opportunities", "tuition_fee")
                if not formation_row.get(name)
                and not any(str(row.get(name, "")).strip() for row in tables["admissions"] + tables["programmes"] + tables["tarifs"] if row.get("formation_id") == formation_id)
            ]
            missing_fields[formation_id] = empty

        # Documents, provenance and RAG text chunks.
        for document in self.documents:
            formation_id = formation_ids_by_url.get(document.url, "")
            if not formation_id and document.parent_url:
                formation_id = formation_ids_by_url.get(document.parent_url, "")
            if not formation_id and document.role in {"establishment", "catalog"}:
                formation_id = ""
            tables["documents"].append(
                {
                    "document_id": document.document_id,
                    "etablissement_id": self.establishment_id,
                    "formation_id": formation_id,
                    "document_type": document.document_type,
                    "title": document.title,
                    "url": document.url,
                    "parent_url": document.parent_url,
                    "raw_path": document.raw_path,
                    "metadata_path": document.metadata_path,
                    "sha256": document.sha256,
                    "byte_size": document.byte_size,
                    "http_status": document.status_code,
                    "content_type": document.content_type,
                    "language": document.language,
                    "text_chars": len(document.text),
                    "page_count": len(document.page_texts),
                    "collection_date": document.collection_date,
                    "parse_status": document.parse_status,
                    "error": document.error,
                }
            )
            tables["sources"].append(
                {
                    "source_id": f"src-doc-{short_hash(document.url, 16)}",
                    "etablissement_id": self.establishment_id,
                    "formation_id": formation_id,
                    "source_url": document.url,
                    "source_title": document.title,
                    "source_type": document.document_type,
                    "attribute": "document",
                    "value_excerpt": excerpt(document.text, 300),
                    "raw_path": document.raw_path,
                    "value_origin": "official_raw_document",
                    "document_language": document.language,
                    "collection_date": document.collection_date,
                    "last_verified_at": "",
                    "http_status": document.status_code,
                    "verification_status": "collected_unverified",
                    "evidence_excerpt": "",
                }
            )
            base_rag = {
                "document_id": document.document_id,
                "etablissement_id": self.establishment_id,
                "establishment_name": self.config["name"],
                "formation_id": formation_id,
                "formation_name": formation_names_by_id.get(formation_id, ""),
                "title": document.title,
                "url": document.url,
                "document_type": document.document_type,
                "language": document.language,
                "collection_date": document.collection_date,
                "raw_path": document.raw_path,
            }
            if document.document_type == "pdf" and document.page_texts:
                for page_number, page_text in document.page_texts:
                    rag_documents.append({**base_rag, "text": page_text, "page_number": page_number})
            elif document.text:
                rag_documents.append({**base_rag, "text": document.text, "page_number": None})

        return {
            "establishment_id": self.establishment_id,
            "collection_date": self.collection_date,
            "tables": tables,
            "rag_documents": rag_documents,
            "stats": {
                "pages_analyzed": len([doc for doc in self.documents if doc.document_type == "html"]),
                "documents_retrieved": len(self.documents),
                "pdf_retrieved": len([doc for doc in self.documents if doc.document_type == "pdf"]),
                "formations_identified": len(tables["formations"]),
                "missing_fields": missing_fields,
                "http_errors": self.http_errors,
                "parsing_errors": self.parsing_errors,
                "robots_available": self.robots_available,
                "robots_notes": self.robots_notes,
            },
        }

    def run(self) -> dict:
        self.discover()
        return self.build_data()
