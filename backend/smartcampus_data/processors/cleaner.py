"""Text, URL and value cleaning helpers.

No value is ever invented here: these helpers only normalise text that was
actually present in a collected document.
"""

from __future__ import annotations

import math
import re
import unicodedata
from datetime import datetime
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from config.settings import LIST_SEPARATOR

_TRACKING_PARAMS = {
    "fbclid",
    "gclid",
    "gbraid",
    "wbraid",
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "mc_cid",
    "mc_eid",
}

_WHITESPACE_RE = re.compile(r"\s+")
_ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\ufeff]")


def clean_text(value: object | None) -> str:
    """Return compact, human-readable text or an empty string."""
    if value is None:
        return ""
    text = str(value)
    text = text.replace("\u00a0", " ").replace("\u202f", " ")
    text = _ZERO_WIDTH_RE.sub("", text)
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


def strip_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize_key(value: str | None) -> str:
    """Stable slug used to build identifiers."""
    value = strip_accents(clean_text(value)).lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def normalize_url(url: str | None, base: str | None = None) -> str:
    """Normalise a URL without following redirects or changing its meaning."""
    url = clean_text(url)
    if not url:
        return ""
    if base:
        url = urljoin(base, url)
    parts = urlparse(url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return ""
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in _TRACKING_PARAMS]
    path = parts.path or "/"
    return urlunparse((parts.scheme.lower(), parts.netloc.lower(), path, "", urlencode(query), ""))


def is_valid_url(url: object | None) -> bool:
    if not isinstance(url, str) or not url.strip():
        return False
    parts = urlparse(url.strip())
    return parts.scheme in {"http", "https"} and bool(parts.netloc) and "." in parts.netloc


def same_site(url: str, base_url: str) -> bool:
    return urlparse(normalize_url(url)).netloc == urlparse(normalize_url(base_url)).netloc


def dedupe(values: Iterable[object]) -> list[str]:
    """Remove duplicates while preserving order."""
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = clean_text(value)
        if not text:
            continue
        key = strip_accents(text).casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def serialize_list(values: Iterable[object] | None) -> str:
    if values is None:
        return ""
    if isinstance(values, str):
        values = [values]
    return LIST_SEPARATOR.join(dedupe(values))


def deserialize_list(value: object | None) -> list[str]:
    text = clean_text(value)
    if not text:
        return []
    return dedupe(text.split(LIST_SEPARATOR))


def extract_lines(text: str | None) -> list[str]:
    """Split collected text into cleaned, non-empty lines."""
    if not text:
        return []
    lines: list[str] = []
    for raw in text.splitlines():
        line = clean_text(raw)
        # Keep leading '#' markers: they identify headings produced by
        # soup_to_text and are needed to delimit extraction sections.
        line = re.sub(r"^[>*\-\u2022\u2023\u25e6]+\s*", "", line).strip()
        if line:
            lines.append(line)
    return lines


def parse_number(value: object | None) -> float | None:
    """Parse a published French/English number. Returns None when absent."""
    text = clean_text(value)
    if not text:
        return None
    match = re.search(r"(?<![\d.,])(\d{1,3}(?:[ \u00a9\u202f.,]\d{3})*(?:[.,]\d+)?|\d+(?:[.,]\d+)?)", text)
    if not match:
        return None
    token = match.group(1).replace("\u00a0", "").replace(" ", "").replace("\u202f", "")
    if "," in token and "." in token:
        token = token.replace(".", "").replace(",", ".")
    elif "," in token:
        token = token.replace(",", ".")
    try:
        number = float(token)
    except ValueError:
        return None
    if not math.isfinite(number):
        return None
    return number


def parse_int(value: object | None) -> int | None:
    number = parse_number(value)
    if number is None:
        return None
    return int(number) if number.is_integer() else None


_WORD_NUMBERS = {
    "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
    "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10,
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


def parse_count(value: str | None) -> int | None:
    """Parse either digits or a small French/English number word."""
    text = clean_text(value).lower()
    match = re.search(r"\b(\d+)\b", text)
    if match:
        return int(match.group(1))
    for word, number in _WORD_NUMBERS.items():
        if re.search(rf"\b{word}\b", text):
            return number
    return None


def parse_date(value: object | None) -> str | None:
    """Return an ISO date (YYYY-MM-DD or YYYY-MM) when the text contains one."""
    text = clean_text(value)
    if not text:
        return None
    match = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})(?!\d)", text)
    if match:
        year, month, day = (int(part) for part in match.groups())
        try:
            return datetime(year, month, day).date().isoformat()
        except ValueError:
            return None
    match = re.search(r"\b(0[1-9]|[12]\d|3[01])/(0[1-9]|1[0-2])/(20\d{2})\b", text)
    if match:
        day, month, year = (int(part) for part in match.groups())
        try:
            return datetime(year, month, day).date().isoformat()
        except ValueError:
            return None
    match = re.search(r"\b(20\d{2})[/-](0[1-9]|1[0-2])\b", text)
    if match:
        return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}"
    match = re.search(r"\b(20\d{2})\b", text)
    if match:
        return match.group(1)
    return None


def excerpt(text: str | None, limit: int = 240) -> str:
    text = clean_text(text)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


_BOILERPLATE_RE = re.compile(
    r"(?i)(copyright|all rights reserved|tous droits r[ée]serv[ée]s|cookies|"
    r"nous utilisons|@[\w.-]+\.[a-z]{2,}|\(\+?216\)|\broute de\b|\bkm\s+\d)"
)


def extract_section_items(text: str, heading_patterns: Iterable[str]) -> list[str]:
    """Collect short bullet-like lines below a heading found in collected text.

    Official pages use both real HTML headings (rendered as ``# ...``) and
    plain styled ``<div>`` labels such as ``Principaux modules :``. Both are
    recognised here; nothing is added that is not present in the text.
    """
    lines = extract_lines(text)
    patterns = [re.compile(pattern, re.I) for pattern in heading_patterns]
    items: list[str] = []
    active = False
    for line in lines:
        label = line.lstrip("# ").strip()
        marked_heading = line.startswith("#")
        matches = any(pattern.search(label) for pattern in patterns)
        plain_heading = (
            not marked_heading
            and matches
            and len(line) <= 100
            and len(line.split()) <= 10
        )
        if marked_heading or plain_heading:
            if active and items:
                break
            active = matches
            continue
        if _BOILERPLATE_RE.search(line):
            if active and items:
                break
            continue
        if not active:
            continue
        if len(line) > 220:
            continue
        if re.match(r"^(?:[A-ZÉÈÀÇ][^:]{3,60}:|\d+[.)]\s)", line) and len(line.split()) < 8:
            continue
        items.append(line)
    return dedupe(items)


def find_sentences(text: str, keyword_patterns: Iterable[str], limit: int = 3) -> list[str]:
    """Return complete sentences that contain any of the given patterns."""
    patterns = [re.compile(pattern, re.I) for pattern in keyword_patterns]
    sentences = re.split(r"(?<=[.!?])\s+", clean_text(text))
    found = [clean_text(sentence) for sentence in sentences if any(p.search(sentence) for p in patterns)]
    return dedupe(found)[:limit]


def soup_to_text(soup) -> str:
    """Convert BeautifulSoup content to line-oriented text with light structure.

    ``get_text(strip=True)`` strips whitespace-only strings, which silently
    removes the ``\\n`` markers used to separate blocks. A non-whitespace
    sentinel is inserted instead and expanded afterwards so every block stays
    on its own line.
    """
    from bs4 import Comment

    sentinel = "\x00"

    for element in soup(
        ["script", "style", "noscript", "svg", "form", "nav", "header", "footer", "aside", "iframe", "button"]
    ):
        element.decompose()
    for comment in soup.find_all(string=lambda value: isinstance(value, Comment)):
        comment.extract()

    for element in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        level = int(element.name[1])
        element.insert_before(f"{sentinel}{'#' * level} ")
        element.append(sentinel)

    # Many official pages build section labels from styled <div>/<p> elements
    # rather than semantic headings. Mark short "title" elements so section
    # extraction can stop at the next label instead of swallowing the footer.
    heading_hints = ("title", "heading", "titre", "accordion", "sous-titre", "subtitle")
    marked: set[int] = set()
    for element in soup.find_all(["div", "p", "span"]):
        classes = " ".join(element.get("class") or []).lower()
        if not any(hint in classes for hint in heading_hints):
            continue
        label = clean_text(element.get_text(" ", strip=True))
        if not label or len(label) > 100 or len(label.split()) > 10:
            continue
        if id(element) in marked:
            continue
        marked.add(id(element))
        element.insert_before(f"{sentinel}## ")
        element.append(sentinel)

    for element in soup.find_all(["li"]):
        element.insert_before(f"{sentinel}- ")
        element.append(sentinel)
    for element in soup.find_all(["p", "div", "section", "article", "br", "tr"]):
        element.append(sentinel)
    for element in soup.find_all(["td", "th"]):
        element.append(" | ")

    raw = soup.get_text(separator=" ", strip=True).replace(sentinel, "\n")
    lines: list[str] = []
    for line in raw.splitlines():
        line = clean_text(line.replace("|", " | "))
        line = re.sub(r"\s*\|\s*", " | ", line)
        line = re.sub(r"^\|\s*", "", line)
        line = re.sub(r"\s*\|$", "", line)
        if line and line != "|":
            lines.append(line)
    return "\n".join(lines)
