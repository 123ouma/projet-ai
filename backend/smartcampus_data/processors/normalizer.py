"""Deterministic normalisation and rule-based extraction of official facts.

Every extracted value keeps the URL and the exact evidence sentence it came
from. `interest_tags` are derived from official text with a fixed keyword map
and are always labelled as derived, never as official facts.
"""

from __future__ import annotations

import re
from typing import Iterable

from processors.cleaner import (
    clean_text,
    deserialize_list,
    excerpt,
    extract_lines,
    extract_section_items,
    find_sentences,
    normalize_key,
    parse_count,
    parse_int,
    serialize_list,
)

FIELD_PATTERNS: dict[str, list[str]] = {
    "formation_name": [r"(?im)^#\s+(.+)$"],
    "field": [r"(?i)\bdomaine\s*\|?\s*:?\s*([^\n]{3,140})"],
    "speciality": [r"(?i)\bsp[ée]cialit[ée]\s*\|?\s*:?\s*([^\n]{3,120})"],
    "duration_years": [
        r"(?i)\bdur[ée]e\s*\|?\s*:?\s*(\d+)\s*ans?\b",
        r"(?i)s['’]?[eé]tale sur\s*(?:six\s*)?\((\d+)\)",
        r"(?i)\b(\d+)\s*ans?\s+d['’]?[eé]tudes?\b",
        r"(?i)\bsix\s*\((\d+)\)\s*ann[ée]es\b",
    ],
    "language": [
        r"(?i)\blangue\s*\|?\s*:?\s*([^\n]{2,80})",
        r"(?i)enseignement\s+(?:est\s+)?assur[ée] en langue\s+([^\n.,;]{2,60})",
        r"(?i)dispens[ée]s?\s+en\s+(fran[çc]ais\s+ou\s+en\s+anglais)",
    ],
    "study_mode": [
        r"(?i)(formation initiale,?\s+pr[ée]sentielle)",
        r"(?i)(pr[ée]sentiel(?:le)?)",
    ],
    "diploma_awarded": [
        r"(?i)(dipl[ôo]me national d['’]?architecte)",
        r"(?i)(dipl[ôo]me du premier cycle d['’]?[eé]tudes en architecture)",
        r"(?i)(\blicence\b[^\n]{0,60})",
        r"(?i)(\bmast[èe]re\b[^\n]{0,60})",
    ],
    "required_baccalaureate": [
        r"(?i)(?:pr[ée]-?requis|baccalaur[ée]ats?\s+[ée]ligibles?)\s*\|?\s*:?\s*([^\n]{3,180})",
        r"(?i)(avoir un dipl[ôo]me d['’]?[eé]tudes secondaires[^\n]{0,100})",
    ],
    "minimum_grade": [r"(?<![\d.,])(\d{1,2}(?:[.,]\d+)?)\s*/\s*20\b"],
    "required_level": [
        r"(?i)(niveau\s+(?:bac|licence|master)[^\n]{0,80})",
        r"(?i)(apr[èe]s un baccalaur[ée]at[^\n]{0,100})",
    ],
    "admission_method": [
        r"(?i)(concours sur dossier)",
        r"(?i)([ée]tude du dossier)",
        r"(?i)(entretien individuel)",
        r"(?i)(pr[ée]inscription en ligne)",
        r"(?i)(test d['’]?admission)",
    ],
    "registration_period": [
        r"(?i)(?:date\s+limite\s+d['’]?inscription|date\s+limite)\s*\|?\s*:?\s*([^\n]{3,80})",
        r"(?i)(les inscriptions sont ouvertes[^\n]{0,80})",
        r"(?i)(rentr[ée]e\s+20\d{2})",
    ],
    "admission_year": [
        r"(?i)(?:rentr[ée]e|ann[ée]e\s+(?:universitaire|acad[ée]mique|scolaire))\s*(20\d{2}(?:\s*[-/]\s*20\d{2})?)",
        r"\b(20\d{2}\s*[-/]\s*20\d{2})\b",
    ],
    "semester_count": [
        r"(?i)\b(?:six|sept|huit)\s+\((\d+)\)\s+semestres\b",
        r"(?i)\b(\d+)\s+semestres\b",
    ],
    "career_field": [r"(?i)\bdomaine\s*\|?\s*:?\s*([^\n]{3,140})"],
}

SECTION_FIELDS: dict[str, list[str]] = {
    "modules": ["principaux modules", "les modules", "^modules", "plan d['’]?[eé]tudes?", "curriculum"],
    "subjects": ["semestre", "mati[èe]res", "subjects", "plan d['’]?[eé]tudes?"],
    "internships": ["stages", "stage", "internships"],
    "projects": ["projets de fin d['’]?[eé]tudes", "projets", "projects"],
    "skills_acquired": [
        "comp[ée]tences cl[ée]s",
        "comp[ée]tences vis[ée]es",
        "r[ée]sultat d['’]?apprentissage",
        "learning outcomes",
    ],
    "specializations": ["parcours de sp[ée]cialisation", "sp[ée]cialisations", "specializations"],
    "required_documents": ["pi[èe]ces [àa] fournir", "documents requis", "documents n[ée]cessaires"],
    "career_opportunities": [
        "d[ée]bouch[ée]s professionnels",
        "m[ée]tiers et d[ée]bouch[ée]s",
        "perspectives professionnelles",
        "r[ée]f[ée]rentiel m[ée]tiers",
    ],
    "prerequisite_skills": ["pr[ée]-?requis", "pr[ée]requis", "conditions d['’]?admission"],
}

SENTENCE_FIELDS: dict[str, list[str]] = {
    "special_conditions": [
        r"sous r[ée]serve",
        r"tous les cours[^\n]{0,80}enseign[ée]s",
        r"commission d['’]?admission",
        r"majoritation annuelle",
    ],
    "further_studies": [
        r"poursuivre (?:une|leurs|[eé]tudes|une carri[èe]re)",
        r"acc[èe]s aux masters?",
        r"perspectives acad[ée]miques",
        r"masters? en",
    ],
    "bridges": [r"passerelle", r"acc[èe]s aux masters?", r"[eé]tudes [àa] l['’]?[eé]tranger"],
    "recommended_profile": [
        r"sens de la cr[ée]ativit[ée]",
        r"autonomie",
        r"profil",
        r"aisance relationnelle",
    ],
}

_LANG_MAP = {
    "anglais": "en",
    "english": "en",
    "en": "en",
    "français": "fr",
    "francais": "fr",
    "french": "fr",
    "fr": "fr",
}

_INTEREST_RULES = [
    (r"\b(intelligence artificielle|machine learning|deep learning|\bIA\b)\b", ["intelligence artificielle"]),
    (r"\b(big data|data science|data engineering|analyse de donn[ée]es)\b", ["données"]),
    (r"\b(cybers[ée]curit[ée]|s[ée]curit[ée] informatique)\b", ["cybersécurité"]),
    (r"\b(cloud|mlops|virtualisation)\b", ["cloud"]),
    (r"\b(business intelligence|analyse du march[ée])\b", ["business intelligence"]),
    (r"\b(comptabilit[ée]|finance|gestion financi[èe]re)\b", ["finance"]),
    (r"\b(marketing|digital)\b", ["marketing digital"]),
    (r"\b(architecture|urbanisme|b[âatim]timent)\b", ["architecture"]),
    (r"\b(infirmier|sant[ée]|soins|clinique)\b", ["santé"]),
    (r"\b(droit|juridique)\b", ["droit"]),
    (r"\b(entrepreneuriat|e-business)\b", ["entrepreneuriat"]),
    (r"\b(g[ée]nie industriel|production|logistique)\b", ["industrie"]),
]


def detect_language(text: str, html_lang: str | None = None) -> str:
    """Heuristic language detection, only used as document metadata."""
    if html_lang:
        lang = clean_text(html_lang).lower()[:2]
        if lang in {"fr", "en"}:
            return lang
    sample = " ".join(extract_lines(text)[:80]).lower()
    fr_markers = sum(len(re.findall(rf"\b{word}\b", sample)) for word in ("le", "la", "des", "est", "une", "dans", "pour", "avec"))
    en_markers = sum(len(re.findall(rf"\b{word}\b", sample)) for word in ("the", "and", "of", "is", "in", "for", "with", "this"))
    return "en" if en_markers > fr_markers else "fr"


def normalize_language(value: str | None) -> str:
    text = clean_text(value).lower()
    for key, lang in _LANG_MAP.items():
        if key in text:
            if "bilingue" in text or ("français" in text and "anglais" in text):
                return "fr|en"
            return lang
    return ""


def normalize_degree_type(name: str, text: str = "") -> str:
    """Derive the degree from the official formation name first.

    Falling back to raw page text can pick up a navigation link such as
    "Cycle Préparatoire" and misclassify an unrelated formation, so the name
    is always tried first and the text is only used when the name is unclear.
    """
    rules = [
        (r"doctorat", "Doctorat"),
        (r"dipl[ôo]me national d['’]?architecte", "Diplôme national d'architecte"),
        (r"cycle pr[ée]paratoire|\bpr[ée]pa\b", "Cycle préparatoire"),
        (r"master of science|\bmsc\b", "Master of Science"),
        (r"master in business administration|\bmba\b", "Master in Business Administration"),
        (r"mast[èe]re", "Mastère"),
        (r"\bmaster\b", "Master"),
        (r"\blicence\b|\blicense\b|licenciatura", "Licence"),
        (r"cycle ing[ée]nieur|fili[èe]re ing[ée]nieur|ing[ée]nierie|\bg[ée]nie\s+[a-zà-ÿ]", "Cycle ingénieur"),
    ]
    for pattern, label in rules:
        if re.search(pattern, name, re.I):
            return label
    # The name may be a generic marketing title. Only unambiguous official
    # degree titles are accepted from the page text, so a navigation link such
    # as "Licence" or "Cycle préparatoire" cannot misclassify a formation.
    strong_text_rules = [
        (r"dipl[ôo]me national d['’]?architecte", "Diplôme national d'architecte"),
        (r"doctorat", "Doctorat"),
        (r"master of science|\bmsc\b", "Master of Science"),
        (r"master in business administration|\bmba\b", "Master in Business Administration"),
        (r"mast[èe]re professionnel", "Mastère"),
    ]
    source = clean_text(text)
    for pattern, label in strong_text_rules:
        if re.search(pattern, source, re.I):
            return label
    return ""


def make_formation_id(establishment_id: str, name: str, url: str = "") -> str:
    slug = normalize_key(name) or normalize_key(url.split("/")[-2:] and "/".join(url.rstrip("/").split("/")[-2:])) or "formation"
    return f"{establishment_id}-{slug}"


def derive_interest_tags(text: str) -> str:
    """Fixed, auditable keyword mapping. Never uses a generative model."""
    tags: list[str] = []
    for pattern, tag in _INTEREST_RULES:
        if re.search(pattern, text, re.I):
            tags.extend(tag)
    return serialize_list(tags)


def _first_match(text: str, patterns: Iterable[str]) -> tuple[str, str]:
    for pattern in patterns:
        match = re.search(pattern, text, re.I | re.M)
        if not match:
            continue
        value = clean_text(match.group(1) if match.groups() else match.group(0))
        line = ""
        for candidate in text.splitlines():
            if value[:20] in candidate:
                line = clean_text(candidate)
                break
        return value, line or value
    return "", ""


def extract_value(field: str, blocks: list[dict]) -> dict:
    """Extract one field from priority-sorted text blocks.

    Each block: {"text": str, "url": str, "title": str, "priority": int,
    "document_id": str}. The first non-empty match wins.
    """
    empty = {"value": "", "evidence": "", "source_url": "", "source_title": "", "document_id": ""}
    ordered = sorted(blocks, key=lambda block: block.get("priority", 99))

    if field in SECTION_FIELDS:
        for block in ordered:
            items = extract_section_items(block.get("text", ""), SECTION_FIELDS[field])
            # Single-word modules such as "Python" or "MLOps" are legitimate.
            items = [item for item in items if len(item.strip()) >= 2 and not item.startswith("#")]
            if items:
                value = serialize_list(items)
                return {
                    "value": value,
                    "evidence": excerpt(" ; ".join(items)),
                    "source_url": block.get("url", ""),
                    "source_title": block.get("title", ""),
                    "document_id": block.get("document_id", ""),
                }
        return empty

    if field in SENTENCE_FIELDS:
        for block in ordered:
            sentences = find_sentences(block.get("text", ""), SENTENCE_FIELDS[field])
            if sentences:
                return {
                    "value": serialize_list(sentences),
                    "evidence": excerpt(sentences[0]),
                    "source_url": block.get("url", ""),
                    "source_title": block.get("title", ""),
                    "document_id": block.get("document_id", ""),
                }
        return empty

    patterns = FIELD_PATTERNS.get(field, [])
    for block in ordered:
        value, evidence = _first_match(block.get("text", ""), patterns)
        if value:
            return {
                "value": value,
                "evidence": excerpt(evidence),
                "source_url": block.get("url", ""),
                "source_title": block.get("title", ""),
                "document_id": block.get("document_id", ""),
            }
    return empty


def normalize_extracted(field: str, value: str) -> str | int | None:
    """Convert a raw official value to the CSV representation."""
    value = clean_text(value)
    if not value:
        return None
    if field in {"duration_years", "semester_count"}:
        return parse_int(value)
    if field in {"minimum_grade"}:
        return value.replace(",", ".")
    if field == "language":
        return normalize_language(value)
    if field == "admission_year":
        match = re.search(r"20\d{2}(?:\s*[-/]\s*20\d{2})?", value)
        return clean_text(match.group(0)).replace(" ", "") if match else value
    return value


def extract_description(blocks: list[dict], formation_name: str = "") -> dict:
    """Choose the first substantial official paragraph, not navigation text."""
    tokens = [token for token in re.findall(r"\w+", formation_name.lower()) if len(token) > 3]
    for block in sorted(blocks, key=lambda item: item.get("priority", 99)):
        lines = extract_lines(block.get("text", ""))
        for line in lines:
            if line.startswith("#") or line.startswith("|") or line.startswith("-"):
                continue
            if len(line) < 80 or len(line) > 1200:
                continue
            if any(label in line.lower() for label in ("copyright", "cookies", "nos utilisons", "all rights reserved")):
                continue
            if not tokens or any(token in line.lower() for token in tokens):
                return {
                    "value": line,
                    "evidence": excerpt(line),
                    "source_url": block.get("url", ""),
                    "source_title": block.get("title", ""),
                    "document_id": block.get("document_id", ""),
                }
    return {"value": "", "evidence": "", "source_url": "", "source_title": "", "document_id": ""}


def count_semesters(text: str) -> int | None:
    numbers = {int(value) for value in re.findall(r"(?i)semestre\s*(\d+)", text)}
    if numbers:
        return max(numbers)
    result = _first_match(text, FIELD_PATTERNS["semester_count"])
    return parse_int(result[0])


def extract_fee_rows(blocks: list[dict]) -> list[dict]:
    """Extract published fees only; never estimates a missing amount."""
    rows: list[dict] = []
    currency_pattern = r"(DT|TND|€|EUR)"
    amount_pattern = r"([\d\s\u00a0\u202f]+(?:[.,]\d+)?)"
    patterns = [
        ("tuition", "national", rf"(?i)(?:frais\s+(?:national|nationaux|de scolarit[ée])\s*\|?\s*:?\s*){amount_pattern}\s*{currency_pattern}"),
        ("tuition", "international", rf"(?i)(?:frais\s+internation(?:al|aux)\s*\|?\s*:?\s*){amount_pattern}\s*{currency_pattern}"),
        ("registration", "national", rf"(?i)droit d['’]?inscription de\s*{amount_pattern}\s*{currency_pattern}"),
        ("registration", "international", rf"(?i)droit d['’]?inscription[^\n]{{0,40}}internation(?:al|aux)[^\n]{{0,40}}?{amount_pattern}\s*{currency_pattern}"),
    ]
    for block in sorted(blocks, key=lambda item: item.get("priority", 99)):
        text = block.get("text", "")
        for fee_type, scope, pattern in patterns:
            for match in re.finditer(pattern, text):
                amount = clean_text(match.group(1)).replace("\u00a0", "").replace("\u202f", "").replace(" ", "")
                amount = amount.replace(",", ".")
                currency = clean_text(match.group(2)).upper()
                if currency == "€":
                    currency = "EUR"
                try:
                    number = float(amount)
                except ValueError:
                    continue
                period_match = re.search(r"/\s*(\d+\s*mois|an|ann[ée]e)", text[match.end() : match.end() + 30], re.I)
                rows.append(
                    {
                        "fee_type": fee_type,
                        "fee_scope": scope,
                        "tuition_fee": number if fee_type == "tuition" else None,
                        "registration_fee": number if fee_type == "registration" else None,
                        "fee_currency": currency,
                        "fee_period": clean_text(period_match.group(1)) if period_match else "",
                        "evidence": excerpt(text[match.start() : match.end() + 60]),
                        "source_url": block.get("url", ""),
                        "source_title": block.get("title", ""),
                        "document_id": block.get("document_id", ""),
                    }
                )
        other = find_sentences(text, [r"sur demande", r"[eé]chelonné par tranches", r"majoritation annuelle", r"payement se fait par virement"], limit=2)
        if other:
            rows.append(
                {
                    "fee_type": "practical_information",
                    "fee_scope": "",
                    "tuition_fee": None,
                    "registration_fee": None,
                    "fee_currency": "",
                    "fee_period": "",
                    "other_fees": serialize_list(other),
                    "evidence": excerpt(other[0]),
                    "source_url": block.get("url", ""),
                    "source_title": block.get("title", ""),
                    "document_id": block.get("document_id", ""),
                }
            )
    return rows


def formation_name_from_doc(title: str, text: str, patterns: Iterable[str]) -> str:
    """Accept a formation page only when an official heading/title matches."""
    result = _first_match(text, [r"(?im)^#\s+(.+)$"])
    candidate = clean_text(result[0] or title)
    if not candidate:
        return ""
    if not any(re.search(pattern, candidate, re.I) for pattern in patterns):
        return ""
    return candidate
