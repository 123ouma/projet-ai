"""CSV, Excel and RAG-ready JSONL exporters."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd

from config.settings import CSV_SCHEMAS, EXPORTS_DIR, PROCESSED_DIR

TABLE_FILES = {name.removesuffix(".csv"): name for name in CSV_SCHEMAS}


def _clean_cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def write_csv_tables(tables: dict[str, list[dict]], processed_dir: Path = PROCESSED_DIR) -> dict[str, Path]:
    processed_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for table_name, filename in TABLE_FILES.items():
        columns = CSV_SCHEMAS[filename]
        path = processed_dir / filename
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            for row in tables.get(table_name, []):
                writer.writerow({column: _clean_cell(row.get(column)) for column in columns})
        written[table_name] = path
    return written


def write_excel(tables: dict[str, list[dict]], exports_dir: Path = EXPORTS_DIR) -> Path:
    exports_dir.mkdir(parents=True, exist_ok=True)
    path = exports_dir / "SmartCampus_Data.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for table_name, filename in TABLE_FILES.items():
            columns = CSV_SCHEMAS[filename]
            rows = tables.get(table_name, [])
            frame = pd.DataFrame(
                [{column: _clean_cell(row.get(column)) for column in columns} for row in rows],
                columns=columns,
            )
            frame.to_excel(writer, sheet_name=table_name[:31], index=False)
        report_path = exports_dir / "validation_report.json"
        if report_path.exists():
            report = json.loads(report_path.read_text(encoding="utf-8"))
            summary = report.get("summary", {})
            rows = [
                {"indicateur": key, "valeur": json.dumps(value, ensure_ascii=False)}
                for key, value in summary.items()
            ]
            pd.DataFrame(rows, columns=["indicateur", "valeur"]).to_excel(
                writer, sheet_name="validation_report", index=False
            )
    return path


def write_rag_jsonl(documents: list[dict], exports_dir: Path = EXPORTS_DIR) -> tuple[Path, int]:
    from config.settings import MAX_RAG_CHUNKS_PER_DOCUMENT, RAG_CHUNK_CHARS, RAG_CHUNK_OVERLAP

    exports_dir.mkdir(parents=True, exist_ok=True)
    path = exports_dir / "rag_documents.jsonl"
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for document in documents:
            text = document.get("text") or ""
            if not text.strip():
                continue
            chunks: list[str] = []
            start = 0
            while start < len(text) and len(chunks) < MAX_RAG_CHUNKS_PER_DOCUMENT:
                chunk = text[start : start + RAG_CHUNK_CHARS].strip()
                if chunk:
                    chunks.append(chunk)
                if start + RAG_CHUNK_CHARS >= len(text):
                    break
                start += RAG_CHUNK_CHARS - RAG_CHUNK_OVERLAP
            for index, chunk in enumerate(chunks):
                payload = {
                    "chunk_id": f"{document.get('document_id', 'doc')}-{index + 1:04d}",
                    "text": chunk,
                    "title": document.get("title", ""),
                    "url": document.get("url", ""),
                    "establishment_id": document.get("etablissement_id", ""),
                    "establishment": document.get("establishment_name", ""),
                    "formation_id": document.get("formation_id", ""),
                    "formation_name": document.get("formation_name", ""),
                    "source_type": document.get("document_type", ""),
                    "language": document.get("language", ""),
                    "collection_date": document.get("collection_date", ""),
                    "page_number": document.get("page_number"),
                    "raw_path": document.get("raw_path", ""),
                    "chunk_index": index + 1,
                    "chunk_count": len(chunks),
                }
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
                count += 1
    return path, count


def export_all(
    tables: dict[str, list[dict]],
    rag_documents: list[dict],
    processed_dir: Path = PROCESSED_DIR,
    exports_dir: Path = EXPORTS_DIR,
) -> dict:
    csv_paths = write_csv_tables(tables, processed_dir)
    excel_path = write_excel(tables, exports_dir)
    jsonl_path, chunk_count = write_rag_jsonl(rag_documents, exports_dir)
    return {
        "csv_paths": csv_paths,
        "excel_path": excel_path,
        "rag_path": jsonl_path,
        "rag_chunks": chunk_count,
    }
