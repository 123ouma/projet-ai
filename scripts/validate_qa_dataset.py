"""Validate the final SmartCampus multilingual QA dataset."""

from __future__ import annotations

import csv
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
QA_PATH = ROOT / "docs" / "llm" / "smartcampus_qa_final.jsonl"
EXPECTED_IDS = {f"QA{number:03d}" for number in range(1, 54)}
ALLOWED_STATUSES = {
    "collected_unverified",
    "teammate_confirmed",
    "independently_verified",
}
REQUIRED_FIELDS = {
    "id",
    "category",
    "question",
    "answer",
    "source",
    "verification_status",
    "keywords",
    "alternate_questions",
}
ALLOWED_LANGUAGES = {"fr", "en", "arabizi"}
REQUIRED_LANGUAGES = ALLOWED_LANGUAGES
IDENTIFIER_COLUMNS = {
    "id",
    "formation_id",
    "programme_id",
    "admission_id",
    "tarif_id",
    "etablissement_id",
    "source_id",
    "document_id",
}
URL_COLUMNS = {"source_url", "url", "website_url"}
ARABIC_SCRIPT_RANGES = (
    (0x0600, 0x06FF),
    (0x0750, 0x077F),
    (0x0870, 0x089F),
    (0x08A0, 0x08FF),
    (0xFB50, 0xFDFF),
    (0xFE70, 0xFEFF),
    (0x10EC0, 0x10EFF),
    (0x1EE00, 0x1EEFF),
)


def _normalize_question(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_accents = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    return " ".join(re.findall(r"[a-z0-9]+", without_accents))


def _contains_arabic_script(value: str) -> bool:
    return any(
        start <= ord(char) <= end
        for char in value
        for start, end in ARABIC_SCRIPT_RANGES
    )


def _walk_source_references(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        if "dataset" in value or "record_id" in value or "source_url" in value:
            yield value
        for child in value.values():
            yield from _walk_source_references(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_source_references(child)


def _load_csv(path: Path, cache: dict[Path, list[dict[str, str]]]) -> list[dict[str, str]]:
    if path not in cache:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            cache[path] = list(csv.DictReader(handle))
    return cache[path]


def _validate_sources(
    source: Any,
    qa_id: str,
    errors: list[str],
    cache: dict[Path, list[dict[str, str]]],
) -> None:
    if not isinstance(source, dict):
        errors.append(f"{qa_id}: source doit être un objet.")
        return

    references = list(_walk_source_references(source))
    if not references:
        errors.append(f"{qa_id}: au moins une référence source est requise.")
        return

    for reference in references:
        dataset = reference.get("dataset")
        record_id = reference.get("record_id")
        source_url = reference.get("source_url")
        if not isinstance(dataset, str) or not dataset:
            errors.append(f"{qa_id}: référence source sans chemin de dataset valide.")
            continue
        if not isinstance(record_id, str) or not record_id:
            errors.append(f"{qa_id}: référence source sans record_id valide.")
            continue
        if not isinstance(source_url, str) or not source_url:
            errors.append(f"{qa_id}: référence source sans URL valide ({record_id}).")
            continue

        relative_path = Path(dataset)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            errors.append(f"{qa_id}: chemin de source interdit: {dataset}")
            continue
        path = (ROOT / relative_path).resolve()
        try:
            path.relative_to(ROOT.resolve())
        except ValueError:
            errors.append(f"{qa_id}: la source sort du repository: {dataset}")
            continue
        if path.suffix.casefold() != ".csv" or not path.is_file():
            errors.append(f"{qa_id}: fichier CSV source introuvable: {dataset}")
            continue

        try:
            rows = _load_csv(path, cache)
        except (OSError, UnicodeError, csv.Error) as exc:
            errors.append(f"{qa_id}: lecture de la source impossible ({dataset}): {exc}.")
            continue

        matches = [
            row
            for row in rows
            if any(row.get(column) == record_id for column in IDENTIFIER_COLUMNS)
        ]
        if not matches:
            errors.append(
                f"{qa_id}: record_id absent du CSV source {dataset}: {record_id}."
            )
            continue
        if not any(
            row.get(column) == source_url
            for row in matches
            for column in URL_COLUMNS
        ):
            errors.append(
                f"{qa_id}: URL source non associée à {record_id}: {source_url}."
            )
        for row in matches:
            status = row.get("verification_status")
            if status and status != "collected_unverified":
                errors.append(
                    f"{qa_id}: le statut d’origine CSV de {record_id} doit rester "
                    f"collected_unverified (valeur trouvée: {status})."
                )


def validate() -> list[str]:
    errors: list[str] = []
    if not QA_PATH.is_file():
        return [f"Fichier QA introuvable: {QA_PATH}"]

    try:
        content = QA_PATH.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [f"Fichier QA non lisible en UTF-8: {exc}"]

    entries: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(content.splitlines(), 1):
        if not raw_line.strip():
            errors.append(f"Ligne {line_number}: ligne JSONL vide.")
            continue
        try:
            entry = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            errors.append(f"Ligne {line_number}: JSON invalide: {exc.msg}.")
            continue
        if not isinstance(entry, dict):
            errors.append(f"Ligne {line_number}: chaque objet JSON doit être un objet.")
            continue
        entries.append(entry)

    if len(entries) != len(EXPECTED_IDS):
        errors.append(
            f"Le dataset doit contenir exactement {len(EXPECTED_IDS)} enregistrements "
            f"(trouvé: {len(entries)})."
        )

    cache: dict[Path, list[dict[str, str]]] = {}
    seen_ids: set[str] = set()
    seen_alternates: dict[str, str] = {}
    found_ids: set[str] = set()

    for line_number, entry in enumerate(entries, 1):
        raw_id = entry.get("id")
        qa_id = raw_id if isinstance(raw_id, str) else f"ligne {line_number}"
        missing_fields = REQUIRED_FIELDS - entry.keys()
        if missing_fields:
            errors.append(
                f"{qa_id}: champs requis absents: {', '.join(sorted(missing_fields))}."
            )

        if not isinstance(raw_id, str) or not raw_id.strip():
            errors.append(f"{qa_id}: identifiant unique requis.")
        elif raw_id in seen_ids:
            errors.append(f"{qa_id}: identifiant dupliqué.")
        else:
            seen_ids.add(raw_id)
            found_ids.add(raw_id)

        for field in ("category", "question", "answer"):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                errors.append(f"{qa_id}: {field} doit être une chaîne non vide.")

        keywords = entry.get("keywords")
        if not isinstance(keywords, list) or not keywords or not all(
            isinstance(word, str) and word.strip() for word in keywords
        ):
            errors.append(f"{qa_id}: keywords doit contenir des chaînes non vides.")

        alternate_questions = entry.get("alternate_questions")
        languages: set[str] = set()
        if not isinstance(alternate_questions, list):
            errors.append(f"{qa_id}: alternate_questions doit être une liste.")
        else:
            for alternate in alternate_questions:
                if not isinstance(alternate, dict):
                    errors.append(
                        f"{qa_id}: chaque alternative doit préciser language et text."
                    )
                    continue
                language = alternate.get("language")
                text = alternate.get("text")
                if language not in ALLOWED_LANGUAGES:
                    errors.append(f"{qa_id}: langue alternative non autorisée: {language!r}.")
                    continue
                if not isinstance(text, str) or not text.strip():
                    errors.append(f"{qa_id}: le texte alternatif doit être non vide.")
                    continue

                languages.add(language)
                if _contains_arabic_script(text):
                    errors.append(f"{qa_id}: formulation en écriture arabe interdite.")
                normalized = _normalize_question(text)
                if normalized:
                    prior = seen_alternates.get(normalized)
                    if prior:
                        errors.append(
                            f"{qa_id}: question alternative dupliquée ou quasi-identique "
                            f"à {prior}."
                        )
                    else:
                        seen_alternates[normalized] = qa_id

        missing_languages = REQUIRED_LANGUAGES - languages
        if missing_languages:
            errors.append(
                f"{qa_id}: formulations alternatives manquantes pour: "
                f"{', '.join(sorted(missing_languages))}."
            )

        status = entry.get("verification_status")
        if status not in ALLOWED_STATUSES:
            errors.append(f"{qa_id}: statut de vérification inconnu: {status!r}.")

        _validate_sources(entry.get("source"), qa_id, errors, cache)

    missing_ids = EXPECTED_IDS - found_ids
    unexpected_ids = found_ids - EXPECTED_IDS
    if missing_ids:
        errors.append(f"Identifiants QA manquants: {', '.join(sorted(missing_ids))}.")
    if unexpected_ids:
        errors.append(f"Identifiants QA inattendus: {', '.join(sorted(unexpected_ids))}.")

    return errors


def main() -> int:
    errors = validate()
    if errors:
        print(f"Échec de validation : {len(errors)} erreur(s).")
        for error in errors:
            print(f"- {error}")
        return 1

    with QA_PATH.open("r", encoding="utf-8") as handle:
        entries = [json.loads(line) for line in handle if line.strip()]
    language_counts = Counter(
        alternate["language"]
        for entry in entries
        for alternate in entry["alternate_questions"]
    )
    print(f"Validation réussie : {QA_PATH.relative_to(ROOT)}")
    print(f"{len(entries)} entrées JSONL valides; IDs QA001–QA053.")
    print(
        "Variantes alternatives : "
        + ", ".join(f"{language}={language_counts[language]}" for language in sorted(ALLOWED_LANGUAGES))
        + "."
    )
    print("Champs, langues, statuts, références CSV et doublons contrôlés.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
