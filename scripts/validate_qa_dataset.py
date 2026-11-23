"""Validate the SmartCampus reference QA JSONL against its source CSV files."""

from __future__ import annotations

import csv
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
QA_PATH = ROOT / "docs" / "llm" / "qa_reference.jsonl"
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
    "verification_basis",
    "source_verification_status",
    "keywords",
    "alternate_questions",
}
REQUIRED_ALTERNATE_LANGUAGES = {"fr", "tn", "arabizi"}
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
URL_COLUMNS = {"source_url", "source_urls", "url", "website_url", "official_name_source_url"}


def _normalize_question(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", without_accents))


def _load_csv(path: Path, cache: dict[Path, list[dict[str, str]]]) -> list[dict[str, str]]:
    if path not in cache:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            cache[path] = list(csv.DictReader(handle))
    return cache[path]


def _source_paths(source: dict[str, Any], qa_id: str, errors: list[str]) -> list[Path]:
    references = source.get("datasets")
    if references is None:
        references = [source.get("dataset")] if source.get("dataset") else []
    elif not isinstance(references, list):
        errors.append(f"{qa_id}: source.datasets doit être une liste.")
        return []

    paths: list[Path] = []
    for reference in references:
        if not isinstance(reference, str) or not reference:
            errors.append(f"{qa_id}: référence de dataset absente ou invalide.")
            continue
        relative = Path(reference)
        if relative.is_absolute() or ".." in relative.parts:
            errors.append(f"{qa_id}: chemin de source interdit: {reference}")
            continue
        path = (ROOT / relative).resolve()
        try:
            path.relative_to(ROOT.resolve())
        except ValueError:
            errors.append(f"{qa_id}: la source sort du repository: {reference}")
            continue
        if path.suffix.casefold() != ".csv" or not path.is_file():
            errors.append(f"{qa_id}: fichier CSV source introuvable: {reference}")
            continue
        paths.append(path)
    if not paths:
        errors.append(f"{qa_id}: au moins un fichier CSV source est requis.")
    return paths


def _record_ids(source: dict[str, Any], qa_id: str, errors: list[str]) -> list[str]:
    identifiers: list[str] = []
    for key in ("record_id", "record_ids"):
        value = source.get(key)
        if value is None:
            continue
        values = [value] if isinstance(value, str) else value
        if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
            errors.append(f"{qa_id}: source.{key} doit contenir une chaîne ou une liste de chaînes.")
            continue
        identifiers.extend(values)
    return identifiers


def validate() -> list[str]:
    errors: list[str] = []
    if not QA_PATH.is_file():
        return [f"Fichier QA introuvable: {QA_PATH}"]

    entries: list[dict[str, Any]] = []
    with QA_PATH.open("r", encoding="utf-8-sig") as handle:
        for line_number, raw_line in enumerate(handle, 1):
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

    cache: dict[Path, list[dict[str, str]]] = {}
    seen_ids: set[str] = set()
    seen_questions: dict[str, str] = {}

    for line_number, entry in enumerate(entries, 1):
        qa_id = entry.get("id") if isinstance(entry.get("id"), str) else f"ligne {line_number}"
        missing = REQUIRED_FIELDS - entry.keys()
        if missing:
            errors.append(f"{qa_id}: champs requis absents: {', '.join(sorted(missing))}.")

        if not isinstance(entry.get("id"), str) or not entry["id"].strip():
            errors.append(f"{qa_id}: identifiant unique requis.")
        elif entry["id"] in seen_ids:
            errors.append(f"{qa_id}: identifiant dupliqué.")
        else:
            seen_ids.add(entry["id"])

        for field in ("category", "question", "answer"):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                errors.append(f"{qa_id}: {field} doit être une chaîne non vide.")

        for field in ("keywords", "alternate_questions"):
            if not isinstance(entry.get(field), list):
                errors.append(f"{qa_id}: {field} doit être une liste.")
        if isinstance(entry.get("keywords"), list) and (
            not entry["keywords"] or not all(isinstance(word, str) and word.strip() for word in entry["keywords"])
        ):
            errors.append(f"{qa_id}: keywords doit contenir des chaînes non vides.")

        alternate_questions = entry.get("alternate_questions")
        languages: set[str] = set()
        if isinstance(alternate_questions, list):
            if len(alternate_questions) < 3:
                errors.append(f"{qa_id}: prévoir au moins trois formulations alternatives.")
            for alternate in alternate_questions:
                if not isinstance(alternate, dict):
                    errors.append(f"{qa_id}: chaque alternative doit préciser language et text.")
                    continue
                language = alternate.get("language")
                text = alternate.get("text")
                if language not in {"fr", "tn", "arabizi"} or not isinstance(text, str) or not text.strip():
                    errors.append(f"{qa_id}: alternative invalide: {alternate!r}.")
                    continue
                languages.add(language)
                normalized = _normalize_question(text)
                if normalized:
                    prior = seen_questions.get(normalized)
                    if prior:
                        errors.append(f"{qa_id}: question dupliquée ou quasi-identique à {prior}.")
                    else:
                        seen_questions[normalized] = qa_id
        if not REQUIRED_ALTERNATE_LANGUAGES <= languages:
            missing_languages = ", ".join(sorted(REQUIRED_ALTERNATE_LANGUAGES - languages))
            errors.append(f"{qa_id}: formulations alternatives manquantes pour: {missing_languages}.")

        main_question = entry.get("question")
        if isinstance(main_question, str) and main_question.strip():
            normalized = _normalize_question(main_question)
            prior = seen_questions.get(normalized)
            if normalized and prior:
                errors.append(f"{qa_id}: question dupliquée ou quasi-identique à {prior}.")
            elif normalized:
                seen_questions[normalized] = qa_id

        status = entry.get("verification_status")
        if status not in ALLOWED_STATUSES:
            errors.append(f"{qa_id}: statut de vérification inconnu: {status!r}.")
        if entry.get("source_verification_status") != "collected_unverified":
            errors.append(f"{qa_id}: le statut d’origine CSV doit rester collected_unverified.")
        basis = entry.get("verification_basis")
        if not isinstance(basis, dict):
            errors.append(f"{qa_id}: verification_basis doit être un objet.")
        elif status == "teammate_confirmed":
            if basis.get("type") != "teammate_confirmation" or basis.get("confirmed_by") != "Islem":
                errors.append(f"{qa_id}: la confirmation du coéquipier doit être attribuée.")
            if basis.get("independent_official_verification") is not False:
                errors.append(f"{qa_id}: ne pas assimiler la confirmation du coéquipier à une vérification officielle.")
        elif status == "independently_verified" and basis.get("type") != "independent_official_verification":
            errors.append(f"{qa_id}: une vérification officielle indépendante doit être explicitement documentée.")

        source = entry.get("source")
        if not isinstance(source, dict):
            errors.append(f"{qa_id}: source doit être un objet.")
            continue
        paths = _source_paths(source, qa_id, errors)
        source_rows: list[tuple[Path, dict[str, str]]] = []
        for path in paths:
            try:
                source_rows.extend((path, row) for row in _load_csv(path, cache))
            except (OSError, csv.Error) as exc:
                errors.append(f"{qa_id}: lecture de la source impossible ({path.name}): {exc}.")

        identifiers = _record_ids(source, qa_id, errors)
        matched_rows: list[tuple[Path, dict[str, str]]] = []
        if identifiers:
            for identifier in identifiers:
                matches = [
                    (path, row)
                    for path, row in source_rows
                    if any(row.get(column) == identifier for column in IDENTIFIER_COLUMNS)
                ]
                if not matches:
                    errors.append(f"{qa_id}: identifiant source introuvable dans les CSV cités: {identifier}.")
                else:
                    matched_rows.extend(matches)
            for path, row in matched_rows:
                csv_status = row.get("verification_status")
                if csv_status and csv_status != "collected_unverified":
                    errors.append(
                        f"{qa_id}: le statut d’origine de {path.name} doit rester collected_unverified "
                        f"(valeur trouvée: {csv_status})."
                    )
        elif not isinstance(source.get("selection"), dict):
            errors.append(f"{qa_id}: indiquer des identifiants de lignes ou une sélection CSV vérifiable.")

        urls: list[str] = []
        for key in ("source_url", "source_urls"):
            value = source.get(key)
            if value is None:
                continue
            values = [value] if isinstance(value, str) else value
            if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
                errors.append(f"{qa_id}: source.{key} doit contenir une URL ou une liste d’URL.")
                continue
            urls.extend(values)
        for url in urls:
            if urlparse(url).scheme not in {"http", "https"} or not urlparse(url).netloc:
                errors.append(f"{qa_id}: URL source invalide: {url}.")
            elif identifiers and not any(
                row.get(column) == url
                for _, row in matched_rows
                for column in URL_COLUMNS
            ):
                errors.append(f"{qa_id}: URL non associée aux lignes source citées: {url}.")

        selection = source.get("selection")
        if isinstance(selection, dict):
            filters = selection.get("filters")
            if not isinstance(filters, dict) or not filters:
                errors.append(f"{qa_id}: source.selection.filters doit être renseigné.")
            else:
                selected_rows = [
                    row
                    for _, row in source_rows
                    if all(row.get(column) == str(value) for column, value in filters.items())
                ]
                if not selected_rows:
                    errors.append(f"{qa_id}: la sélection source ne correspond à aucune ligne CSV.")
                for row in selected_rows:
                    csv_status = row.get("verification_status")
                    if csv_status and csv_status != "collected_unverified":
                        errors.append(
                            f"{qa_id}: le statut d’origine de la sélection doit rester collected_unverified "
                            f"(valeur trouvée: {csv_status})."
                        )
                for field in selection.get("expected_empty_fields", []):
                    if any(row.get(field, "").strip() for row in selected_rows):
                        errors.append(f"{qa_id}: {field} n’est pas vide dans toutes les lignes sélectionnées.")
                if selection.get("expect_no_published_amounts"):
                    if any(
                        row.get("fee_status") == "published"
                        and any(row.get(field, "").strip() for field in ("tuition_fee", "registration_fee"))
                        for row in selected_rows
                    ):
                        errors.append(f"{qa_id}: la sélection contient un tarif ISB publié.")
        elif selection is not None:
            errors.append(f"{qa_id}: source.selection doit être un objet vérifiable.")

        evidence_fields: list[str] = []
        for key in ("evidence_field", "evidence_fields", "expected_empty_fields"):
            value = source.get(key)
            if isinstance(value, str):
                evidence_fields.append(value)
            elif isinstance(value, list):
                evidence_fields.extend(field for field in value if isinstance(field, str))
        if evidence_fields and matched_rows:
            available_fields = set().union(*(row.keys() for _, row in matched_rows))
            for field in evidence_fields:
                if field not in available_fields:
                    errors.append(f"{qa_id}: champ de preuve absent des CSV cités: {field}.")
        for field in source.get("expected_empty_fields", []):
            if matched_rows and any(row.get(field, "").strip() for _, row in matched_rows):
                errors.append(f"{qa_id}: le champ de preuve {field} n’est pas vide dans chaque ligne citée.")

    return errors


def main() -> int:
    errors = validate()
    if errors:
        print(f"Échec de validation : {len(errors)} erreur(s).")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Validation réussie : {QA_PATH.relative_to(ROOT)}")
    with QA_PATH.open("r", encoding="utf-8-sig") as handle:
        count = sum(1 for line in handle if line.strip())
    print(f"{count} entrées JSONL valides; identifiants, champs, sources, statuts et doublons contrôlés.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
