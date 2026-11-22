-- SA-14 — Documents, sources et synchronisation (PostgreSQL 17)
-- Dépend de 001_catalogue.sql (establishments, formations, academic_years).
-- Aucun embedding, aucun vecteur, aucun chatbot : uniquement la traçabilité
-- et un champ d'état rag_index_status laissé à 'not_indexed'.
-- Aucune table ni donnée existante n'est supprimée.

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. Sources officielles
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sources (
    source_id           TEXT PRIMARY KEY,
    etablissement_id    TEXT
        CONSTRAINT sources_etablissement_fk
        REFERENCES establishments (etablissement_id) ON DELETE RESTRICT,
    formation_id        TEXT
        CONSTRAINT sources_formation_fk
        REFERENCES formations (formation_id) ON DELETE RESTRICT,
    source_url          TEXT NOT NULL,
    source_title        TEXT,
    source_type         TEXT NOT NULL
        CONSTRAINT sources_type_chk CHECK (source_type IN ('html', 'pdf', 'api', 'other')),
    attribute           TEXT,
    value_excerpt       TEXT,
    raw_path            TEXT,
    value_origin        TEXT
        CONSTRAINT sources_value_origin_chk
        CHECK (value_origin IN ('official', 'official_raw_document',
                                'derived_from_official_text_fixed_rules',
                                'derived_not_official_fact', 'user_provided')),
    document_language   TEXT,
    collection_date     TIMESTAMPTZ,
    last_verified_at    TIMESTAMPTZ,
    http_status         INTEGER
        CONSTRAINT sources_http_status_chk CHECK (http_status BETWEEN 100 AND 599),
    verification_status TEXT NOT NULL DEFAULT 'collected_unverified'
        CONSTRAINT sources_verification_status_chk
        CHECK (verification_status IN
               ('collected_unverified', 'verified', 'derived_not_official_fact', 'needs_review')),
    evidence_excerpt    TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE sources IS '329 provenances collectées par SA-18 (URL officielle + extrait + origine).';

-- ---------------------------------------------------------------------------
-- 2. Documents collectés
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS documents (
    document_id          TEXT PRIMARY KEY,
    etablissement_id     TEXT
        CONSTRAINT documents_etablissement_fk
        REFERENCES establishments (etablissement_id) ON DELETE RESTRICT,
    document_type        TEXT NOT NULL
        CONSTRAINT documents_type_chk
        CHECK (document_type IN ('html', 'pdf', 'doc', 'docx', 'xlsx', 'other')),
    title                TEXT,
    url                  TEXT NOT NULL,
    parent_url           TEXT,
    raw_path             TEXT NOT NULL,
    metadata_path        TEXT,
    sha256               TEXT NOT NULL
        CONSTRAINT documents_sha256_chk CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    byte_size            BIGINT
        CONSTRAINT documents_byte_size_chk CHECK (byte_size >= 0),
    http_status          INTEGER
        CONSTRAINT documents_http_status_chk CHECK (http_status BETWEEN 100 AND 599),
    content_type         TEXT,
    language             TEXT,
    text_chars           INTEGER
        CONSTRAINT documents_text_chars_chk CHECK (text_chars >= 0),
    page_count           INTEGER
        CONSTRAINT documents_page_count_chk CHECK (page_count >= 0),
    collection_date      TIMESTAMPTZ NOT NULL,
    last_verified_at     TIMESTAMPTZ,
    sync_status          TEXT NOT NULL DEFAULT 'collected'
        CONSTRAINT documents_sync_status_chk
        CHECK (sync_status IN ('pending', 'collected', 'synced', 'failed', 'stale')),
    last_error_message   TEXT,
    verification_status  TEXT
        CONSTRAINT documents_verification_status_chk
        CHECK (verification_status IN
               ('collected_unverified', 'verified', 'derived_not_official_fact', 'needs_review')),
    academic_year_label  TEXT
        CONSTRAINT documents_academic_year_fk
        REFERENCES academic_years (label) ON DELETE RESTRICT,
    rag_index_status     TEXT NOT NULL DEFAULT 'not_indexed'
        CONSTRAINT documents_rag_index_status_chk
        CHECK (rag_index_status IN ('not_indexed', 'eligible', 'indexed', 'excluded')),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT documents_natural_key UNIQUE (etablissement_id, url),
    CONSTRAINT documents_failed_has_error_chk CHECK (
        sync_status <> 'failed' OR last_error_message IS NOT NULL
    )
);

COMMENT ON COLUMN documents.rag_index_status IS 'État futur. Ce ticket n''écrit jamais indexed et ne stocke aucun embedding.';

-- ---------------------------------------------------------------------------
-- 3. Association documents ↔ formations
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS document_formations (
    document_id  TEXT NOT NULL
        CONSTRAINT document_formations_document_fk
        REFERENCES documents (document_id) ON DELETE CASCADE,
    formation_id TEXT NOT NULL
        CONSTRAINT document_formations_formation_fk
        REFERENCES formations (formation_id) ON DELETE CASCADE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (document_id, formation_id)
);

-- ---------------------------------------------------------------------------
-- 4. Historique des synchronisations
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sync_history (
    sync_id          BIGSERIAL PRIMARY KEY,
    source_id        TEXT
        CONSTRAINT sync_history_source_fk
        REFERENCES sources (source_id) ON DELETE RESTRICT,
    document_id      TEXT
        CONSTRAINT sync_history_document_fk
        REFERENCES documents (document_id) ON DELETE RESTRICT,
    sync_type        TEXT NOT NULL
        CONSTRAINT sync_history_type_chk
        CHECK (sync_type IN ('full', 'incremental', 'verification', 'retry')),
    sync_status      TEXT NOT NULL
        CONSTRAINT sync_history_status_chk
        CHECK (sync_status IN ('started', 'success', 'failed', 'partial')),
    started_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at      TIMESTAMPTZ,
    http_status      INTEGER
        CONSTRAINT sync_history_http_status_chk CHECK (http_status BETWEEN 100 AND 599),
    error_message    TEXT,
    items_processed  INTEGER
        CONSTRAINT sync_history_items_processed_chk CHECK (items_processed >= 0),
    items_created    INTEGER
        CONSTRAINT sync_history_items_created_chk CHECK (items_created >= 0),
    items_updated    INTEGER
        CONSTRAINT sync_history_items_updated_chk CHECK (items_updated >= 0),
    items_failed     INTEGER
        CONSTRAINT sync_history_items_failed_chk CHECK (items_failed >= 0),
    triggered_by     TEXT,
    CONSTRAINT sync_history_has_target_chk CHECK (
        source_id IS NOT NULL OR document_id IS NOT NULL
    ),
    CONSTRAINT sync_history_finished_chk CHECK (
        finished_at IS NULL OR finished_at >= started_at
    ),
    CONSTRAINT sync_history_failed_has_error_chk CHECK (
        sync_status <> 'failed' OR error_message IS NOT NULL
    )
);

-- ---------------------------------------------------------------------------
-- 5. Versions de documents
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS document_versions (
    version_id          BIGSERIAL PRIMARY KEY,
    document_id         TEXT NOT NULL
        CONSTRAINT document_versions_document_fk
        REFERENCES documents (document_id) ON DELETE CASCADE,
    version_number      INTEGER NOT NULL
        CONSTRAINT document_versions_number_chk CHECK (version_number > 0),
    sha256              TEXT NOT NULL
        CONSTRAINT document_versions_sha256_chk CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    raw_path            TEXT NOT NULL,
    byte_size           BIGINT
        CONSTRAINT document_versions_byte_size_chk CHECK (byte_size >= 0),
    collected_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    change_detected_at  TIMESTAMPTZ,
    is_current          BOOLEAN NOT NULL DEFAULT false,
    CONSTRAINT document_versions_number_unique UNIQUE (document_id, version_number)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_document_versions_current
    ON document_versions (document_id) WHERE is_current;

-- ---------------------------------------------------------------------------
-- Index utiles
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS ix_sources_etablissement ON sources (etablissement_id);
CREATE INDEX IF NOT EXISTS ix_sources_formation ON sources (formation_id);
CREATE INDEX IF NOT EXISTS ix_sources_url ON sources (source_url);
CREATE INDEX IF NOT EXISTS ix_sources_verification ON sources (verification_status);
CREATE INDEX IF NOT EXISTS ix_documents_etablissement ON documents (etablissement_id);
CREATE INDEX IF NOT EXISTS ix_documents_sync_status ON documents (sync_status);
CREATE INDEX IF NOT EXISTS ix_documents_collection_date ON documents (collection_date);
CREATE INDEX IF NOT EXISTS ix_document_formations_formation ON document_formations (formation_id);
CREATE INDEX IF NOT EXISTS ix_sync_history_source ON sync_history (source_id);
CREATE INDEX IF NOT EXISTS ix_sync_history_document ON sync_history (document_id);
CREATE INDEX IF NOT EXISTS ix_document_versions_document ON document_versions (document_id);

-- ---------------------------------------------------------------------------
-- Triggers updated_at
-- ---------------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_sources_updated_at ON sources;
CREATE TRIGGER trg_sources_updated_at BEFORE UPDATE ON sources
    FOR EACH ROW EXECUTE FUNCTION sc_set_updated_at();

DROP TRIGGER IF EXISTS trg_documents_updated_at ON documents;
CREATE TRIGGER trg_documents_updated_at BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION sc_set_updated_at();

COMMIT;
