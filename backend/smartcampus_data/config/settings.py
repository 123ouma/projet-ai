"""Global settings for the SmartCampus data collector."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
EXPORTS_DIR = DATA_DIR / "exports"
CACHE_DIR = PROCESSED_DIR / ".scrape_cache"

ESTABLISHMENT_IDS = ("IIT", "ISB", "ISA", "2I2S")

# Short, identifiable User-Agent. Some official servers reject verbose UA strings.
USER_AGENT = "SmartCampusDataCollector/1.0"

REQUEST_TIMEOUT = 20
MAX_RETRIES = 2
RETRY_BACKOFF_FACTOR = 0.8
REQUEST_DELAY_SECONDS = 1.2
MAX_PDF_BYTES = 20 * 1024 * 1024
MAX_PAGES_PER_SITE = 30
MAX_PDFS_PER_SITE = 10
MAX_CRAWL_DEPTH = 2

DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
LIST_SEPARATOR = " | "
RAG_CHUNK_CHARS = 1800
RAG_CHUNK_OVERLAP = 200
MAX_RAG_CHUNKS_PER_DOCUMENT = 40

CSV_SCHEMAS: dict[str, list[str]] = {
    "etablissements.csv": [
        "etablissement_id",
        "name",
        "short_name",
        "country",
        "city",
        "website_url",
        "official_name_source_url",
        "contact_email",
        "contact_phone",
        "campus_location",
        "collection_date",
        "document_language",
        "verification_status",
    ],
    "formations.csv": [
        "formation_id",
        "etablissement_id",
        "formation_name",
        "degree_type",
        "field",
        "speciality",
        "description",
        "duration_years",
        "language",
        "study_mode",
        "diploma_awarded",
        "career_opportunities",
        "further_studies",
        "career_field",
        "bridges",
        "recommended_profile",
        "interest_tags",
        "interest_tags_origin",
        "prerequisite_skills",
        "source_url",
        "source_title",
        "source_type",
        "collection_date",
        "last_verified_at",
        "academic_year",
        "verification_status",
        "document_language",
    ],
    "admissions.csv": [
        "admission_id",
        "formation_id",
        "etablissement_id",
        "required_baccalaureate",
        "minimum_grade",
        "required_level",
        "admission_method",
        "required_documents",
        "registration_period",
        "special_conditions",
        "admission_year",
        "source_url",
        "source_title",
        "collection_date",
        "document_language",
        "verification_status",
    ],
    "programmes.csv": [
        "programme_id",
        "formation_id",
        "etablissement_id",
        "subjects",
        "modules",
        "semester_count",
        "internships",
        "projects",
        "specializations",
        "skills_acquired",
        "source_url",
        "source_title",
        "collection_date",
        "document_language",
        "verification_status",
    ],
    "tarifs.csv": [
        "tarif_id",
        "formation_id",
        "etablissement_id",
        "fee_type",
        "fee_scope",
        "tuition_fee",
        "registration_fee",
        "other_fees",
        "fee_currency",
        "fee_period",
        "fee_academic_year",
        "payment_terms",
        "campus_location",
        "contact_email",
        "contact_phone",
        "fee_status",
        "source_url",
        "source_title",
        "collection_date",
        "document_language",
        "verification_status",
    ],
    "sources.csv": [
        "source_id",
        "etablissement_id",
        "formation_id",
        "source_url",
        "source_title",
        "source_type",
        "attribute",
        "value_excerpt",
        "raw_path",
        "value_origin",
        "document_language",
        "collection_date",
        "last_verified_at",
        "http_status",
        "verification_status",
        "evidence_excerpt",
    ],
    "documents.csv": [
        "document_id",
        "etablissement_id",
        "formation_id",
        "document_type",
        "title",
        "url",
        "parent_url",
        "raw_path",
        "metadata_path",
        "sha256",
        "byte_size",
        "http_status",
        "content_type",
        "language",
        "text_chars",
        "page_count",
        "collection_date",
        "parse_status",
        "error",
    ],
}

REQUIRED_FORMATION_FIELDS = (
    "formation_id",
    "etablissement_id",
    "formation_name",
    "source_url",
)

CORE_COMPLETENESS_FIELDS = (
    "degree_type",
    "description",
    "duration_years",
    "language",
    "source_url",
)
