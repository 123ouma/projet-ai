#!/usr/bin/env python3
"""CLI entry point for SA-18 — official SmartCampus data collection."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml

from config.settings import CACHE_DIR, CONFIG_DIR, ESTABLISHMENT_IDS, EXPORTS_DIR, PROCESSED_DIR
from processors.exporter import export_all, write_excel
from processors.validator import TABLE_NAMES, validate_dataset, validate_tables
from scrapers.base_scraper import BaseScraper
from scrapers.i2s_scraper import I2SScraper
from scrapers.isa_scraper import ISAScraper
from scrapers.isb_scraper import ISBScraper
from scrapers.iit_scraper import IITScraper

SCRAPERS: dict[str, type[BaseScraper]] = {
    "IIT": IITScraper,
    "ISB": ISBScraper,
    "ISA": ISAScraper,
    "2I2S": I2SScraper,
}


def load_sources() -> tuple[dict, dict[str, dict]]:
    config_path = CONFIG_DIR / "sources.yaml"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    return data.get("defaults", {}), data.get("establishments", {})


def cache_path(establishment_id: str) -> Path:
    return CACHE_DIR / f"{establishment_id}.json"


def save_cache(result: dict) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = cache_path(result["establishment_id"])
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_caches(only: list[str] | None = None) -> tuple[dict[str, list[dict]], list[dict], list[str]]:
    keys = only or list(ESTABLISHMENT_IDS)
    tables: dict[str, list[dict]] = {name: [] for name in TABLE_NAMES}
    rag_documents: list[dict] = []
    loaded: list[str] = []
    for key in keys:
        path = cache_path(key)
        if not path.exists():
            continue
        result = json.loads(path.read_text(encoding="utf-8"))
        for name in TABLE_NAMES:
            tables[name].extend(result.get("tables", {}).get(name, []))
        rag_documents.extend(result.get("rag_documents", []))
        loaded.append(key)
    return tables, rag_documents, loaded


def print_plan(plan: dict) -> None:
    print(f"\n=== Mode dry-run — {plan['establishment']} ===")
    print(f"robots.txt consulté : {'oui' if plan['robots_available'] else 'non/non disponible'}")
    for note in plan.get("robots_notes", []):
        print(f"  - {note}")
    print(f"Pages prévues ({len(plan['planned_pages'])}) :")
    for url in plan["planned_pages"]:
        print(f"  - {url}")
    print(f"PDF publics repérés ({len(plan['planned_pdfs'])}) :")
    for url in plan["planned_pdfs"]:
        print(f"  - {url}")
    print(f"Erreurs HTTP : {len(plan['http_errors'])}")
    for error in plan["http_errors"][:10]:
        print(f"  - {error['url']} : {error['error']}")
    print("Aucune collecte complète ni écriture de fichiers de données effectuée.")


def print_stats(result: dict) -> None:
    stats = result["stats"]
    print(f"\n=== Résumé — {result['establishment_id']} ===")
    print(f"Pages HTML analysées : {stats['pages_analyzed']}")
    print(f"Documents récupérés : {stats['documents_retrieved']} (dont {stats['pdf_retrieved']} PDF)")
    print(f"Formations identifiées : {stats['formations_identified']}")
    missing = stats.get("missing_fields", {})
    total_missing = sum(len(fields) for fields in missing.values())
    print(f"Champs manquants détectés : {total_missing}")
    for formation_id, fields in missing.items():
        if fields:
            print(f"  - {formation_id} : {', '.join(fields)}")
    print(f"Erreurs HTTP : {len(stats['http_errors'])}")
    for error in stats["http_errors"][:10]:
        print(f"  - {error['url']} : {error['error']}")
    print(f"Erreurs de parsing : {len(stats['parsing_errors'])}")
    for error in stats["parsing_errors"][:10]:
        print(f"  - {error['url']} : {error['error']}")
    if not stats["formations_identified"]:
        print("Aucune formation confirmée : le site peut être inaccessible ou ne pas exposer de catalogue public exploitable.")


def print_paths(exports: dict, report_paths: tuple[Path, Path]) -> None:
    print("\nFichiers générés :")
    for path in exports["csv_paths"].values():
        print(f"  - {path}")
    print(f"  - {exports['excel_path']}")
    print(f"  - {exports['rag_path']} ({exports['rag_chunks']} chunks)")
    print(f"  - {report_paths[0]}")
    print(f"  - {report_paths[1]}")


def run_collect(keys: list[str], dry_run: bool) -> int:
    defaults, establishments = load_sources()
    if dry_run:
        for key in keys:
            scraper = SCRAPERS[key](establishments[key], defaults, dry_run=True)
            try:
                print_plan(scraper.plan())
            except Exception as exc:  # noqa: BLE001
                print(f"Échec du dry-run pour {key} : {exc}", file=sys.stderr)
        return 0

    results: list[dict] = []
    for key in keys:
        print(f"\nCollecte de {key} — {establishments[key]['name']}")
        scraper = SCRAPERS[key](establishments[key], defaults)
        try:
            result = scraper.run()
        except Exception as exc:  # noqa: BLE001
            print(f"ÉCHEC de collecte pour {key} : {exc}", file=sys.stderr)
            traceback.print_exc(limit=2)
            continue
        print_stats(result)
        results.append(result)
        if result["stats"]["formations_identified"]:
            print(f"Cache écrit : {save_cache(result)}")

    if not results:
        print("Aucune collecte réussie ; aucun fichier de données n'a été régénéré.", file=sys.stderr)
        return 1

    tables, rag_documents, loaded = load_caches()
    print(f"\nCaches utilisés pour l'export global : {', '.join(loaded) or 'aucun'}")
    exports = export_all(tables, rag_documents)
    report = validate_dataset()
    write_excel(tables)
    print_paths(exports, (EXPORTS_DIR / "validation_report.json", EXPORTS_DIR / "validation_report.md"))
    print(
        f"\nValidation : {'PASS' if report['passed'] else 'FAIL'} — "
        f"{report['summary']['errors']} erreur(s), {report['summary']['warnings']} avertissement(s)."
    )
    return 0 if all(result["stats"]["formations_identified"] for result in results) else 2


def run_export() -> int:
    tables, rag_documents, loaded = load_caches()
    if not loaded:
        print("Aucun cache de collecte trouvé. Lancez d'abord une collecte réelle.", file=sys.stderr)
        return 1
    print(f"Export depuis les caches : {', '.join(loaded)}")
    exports = export_all(tables, rag_documents)
    report = validate_dataset()
    write_excel(tables)
    print_paths(exports, (EXPORTS_DIR / "validation_report.json", EXPORTS_DIR / "validation_report.md"))
    print(f"Validation : {'PASS' if report['passed'] else 'FAIL'}")
    return 0


def run_validate() -> int:
    report = validate_dataset()
    print(f"Validation : {'PASS' if report['passed'] else 'FAIL'}")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"Rapport JSON : {EXPORTS_DIR / 'validation_report.json'}")
    print(f"Rapport Markdown : {EXPORTS_DIR / 'validation_report.md'}")
    return 0 if report["passed"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SA-18 — collecte et préparation des données officielles SmartCampus.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--establishment", choices=ESTABLISHMENT_IDS, help="Collecter un établissement.")
    group.add_argument("--all", action="store_true", help="Collecter les quatre établissements.")
    group.add_argument("--validate", action="store_true", help="Valider les CSV présents dans data/processed.")
    group.add_argument("--export", action="store_true", help="Régénérer CSV, Excel et JSONL depuis les caches de collecte.")
    parser.add_argument("--dry-run", action="store_true", help="Vérifier les URLs et afficher les pages prévues sans collecter.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.dry_run and (args.validate or args.export):
        print("--dry-run ne peut être combiné qu'avec --establishment ou --all.", file=sys.stderr)
        return 2
    if args.validate:
        return run_validate()
    if args.export:
        return run_export()
    keys = list(ESTABLISHMENT_IDS) if args.all else [args.establishment]
    return run_collect(keys, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
