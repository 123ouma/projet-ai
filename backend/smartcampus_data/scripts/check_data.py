#!/usr/bin/env python3
"""Quick integrity check for the processed SmartCampus CSV files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import PROCESSED_DIR
from processors.validator import read_csv_tables, validate_tables


def main() -> int:
    parser = argparse.ArgumentParser(description="Contrôle rapide des CSV traités.")
    parser.add_argument("--data-dir", type=Path, default=PROCESSED_DIR)
    parser.add_argument("--strict", action="store_true", help="Code de sortie 1 en présence d'erreurs.")
    args = parser.parse_args()

    tables = read_csv_tables(args.data_dir)
    report = validate_tables(tables)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    for error in report["errors"][:50]:
        print(f"ERREUR [{error['code']}] {error['message']}")
    for warning in report["warnings"][:50]:
        print(f"AVERTISSEMENT [{warning['code']}] {warning['message']}")
    return 1 if args.strict and report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
