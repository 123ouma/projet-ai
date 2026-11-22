-- SA-12 — Catalogue académique (PostgreSQL 17)
-- Migration idempotente. La transaction est portée par ce fichier : le script
-- Python l'exécute avec autocommit=True afin que BEGIN/COMMIT soient effectifs.
-- Aucune table ni donnée existante n'est supprimée.

BEGIN;

-- ---------------------------------------------------------------------------
-- Fonction partagée : maintien de updated_at
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION sc_set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------------
-- 1. Établissements
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS establishments (
    etablissement_id          TEXT PRIMARY KEY,
    name                      TEXT NOT NULL,
    short_name                TEXT,
    country                   TEXT,
    city                      TEXT,
    website_url               TEXT,
    official_name_source_url  TEXT,
    contact_email             TEXT,
    contact_phone             TEXT,
    campus_location           TEXT,
    collection_date           TIMESTAMPTZ,
    document_language         TEXT,
    verification_status       TEXT NOT NULL DEFAULT 'collected_unverified'
        CONSTRAINT establishments_verification_status_chk
        CHECK (verification_status IN
               ('collected_unverified', 'verified', 'derived_not_official_fact', 'needs_review')),
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE establishments IS 'Établissements officiels IIT, ISB, ISA et 2I2S (SA-18).';

-- ---------------------------------------------------------------------------
-- 2. Niveaux de diplôme (table de référence)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS degree_levels (
    code       TEXT PRIMARY KEY,
    label      TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE degree_levels IS 'Les 7 libellés de degree_type réellement observés dans formations.csv.';

-- ---------------------------------------------------------------------------
-- 3. Années universitaires (table de référence)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS academic_years (
    label      TEXT PRIMARY KEY,
    start_year INTEGER NOT NULL
        CONSTRAINT academic_years_start_chk CHECK (start_year BETWEEN 1900 AND 2200),
    end_year   INTEGER
        CONSTRAINT academic_years_end_chk CHECK (end_year BETWEEN 1900 AND 2200),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT academic_years_order_chk CHECK (end_year IS NULL OR end_year > start_year)
);

COMMENT ON COLUMN academic_years.end_year IS 'NULL quand seule une année simple est publiée (ex. 2026).';

-- ---------------------------------------------------------------------------
-- 4. Formations
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS formations (
    formation_id           TEXT PRIMARY KEY,
    etablissement_id       TEXT NOT NULL
        CONSTRAINT formations_etablissement_fk
        REFERENCES establishments (etablissement_id) ON DELETE RESTRICT,
    degree_level_code      TEXT
        CONSTRAINT formations_degree_level_fk
        REFERENCES degree_levels (code) ON DELETE RESTRICT,
    academic_year_label    TEXT
        CONSTRAINT formations_academic_year_fk
        REFERENCES academic_years (label) ON DELETE RESTRICT,
    formation_name         TEXT NOT NULL,
    field                  TEXT,
    speciality             TEXT,
    description            TEXT,
    duration_years         NUMERIC(4,1)
        CONSTRAINT formations_duration_chk CHECK (duration_years > 0),
    language               TEXT,
    study_mode             TEXT,
    diploma_awarded        TEXT,
    career_opportunities   TEXT,
    further_studies        TEXT,
    career_field           TEXT,
    bridges                TEXT,
    recommended_profile    TEXT,
    interest_tags          TEXT,
    interest_tags_origin   TEXT,
    prerequisite_skills    TEXT,
    source_url             TEXT,
    source_title           TEXT,
    source_type            TEXT,
    collection_date        TIMESTAMPTZ,
    last_verified_at       TIMESTAMPTZ,
    verification_status    TEXT NOT NULL DEFAULT 'collected_unverified'
        CONSTRAINT formations_verification_status_chk
        CHECK (verification_status IN
               ('collected_unverified', 'verified', 'derived_not_official_fact', 'needs_review')),
    document_language      TEXT,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT formations_natural_key UNIQUE (etablissement_id, formation_name)
);

COMMENT ON COLUMN formations.interest_tags IS 'Liste dérivée par règles fixes, conservée au format SA-18 (séparateur " | ").';

-- ---------------------------------------------------------------------------
-- 5. Conditions d'admission (1:1 avec formations)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS admission_requirements (
    admission_id            TEXT PRIMARY KEY,
    formation_id            TEXT NOT NULL UNIQUE
        CONSTRAINT admission_requirements_formation_fk
        REFERENCES formations (formation_id) ON DELETE CASCADE,
    academic_year_label     TEXT
        CONSTRAINT admission_requirements_academic_year_fk
        REFERENCES academic_years (label) ON DELETE RESTRICT,
    required_baccalaureate  TEXT,
    minimum_grade           NUMERIC(5,2)
        CONSTRAINT admission_requirements_min_grade_chk
        CHECK (minimum_grade BETWEEN 0 AND 20),
    required_level          TEXT,
    admission_method        TEXT,
    required_documents      TEXT,
    registration_period     TEXT,
    special_conditions      TEXT,
    source_url              TEXT,
    source_title            TEXT,
    collection_date         TIMESTAMPTZ,
    document_language       TEXT,
    verification_status     TEXT NOT NULL DEFAULT 'collected_unverified'
        CONSTRAINT admission_requirements_verification_status_chk
        CHECK (verification_status IN
               ('collected_unverified', 'verified', 'derived_not_official_fact', 'needs_review')),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- 6. Programmes académiques (1:1 avec formations)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS academic_programs (
    programme_id         TEXT PRIMARY KEY,
    formation_id         TEXT NOT NULL UNIQUE
        CONSTRAINT academic_programs_formation_fk
        REFERENCES formations (formation_id) ON DELETE CASCADE,
    subjects             TEXT,
    modules              TEXT,
    semester_count       INTEGER
        CONSTRAINT academic_programs_semester_chk CHECK (semester_count BETWEEN 1 AND 12),
    internships          TEXT,
    projects             TEXT,
    specializations      TEXT,
    skills_acquired      TEXT,
    source_url           TEXT,
    source_title         TEXT,
    collection_date      TIMESTAMPTZ,
    document_language    TEXT,
    verification_status  TEXT NOT NULL DEFAULT 'collected_unverified'
        CONSTRAINT academic_programs_verification_status_chk
        CHECK (verification_status IN
               ('collected_unverified', 'verified', 'derived_not_official_fact', 'needs_review')),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- 7. Frais de scolarité (N:1 avec formations)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tuition_fees (
    tarif_id             TEXT PRIMARY KEY,
    formation_id         TEXT NOT NULL
        CONSTRAINT tuition_fees_formation_fk
        REFERENCES formations (formation_id) ON DELETE CASCADE,
    academic_year_label  TEXT
        CONSTRAINT tuition_fees_academic_year_fk
        REFERENCES academic_years (label) ON DELETE RESTRICT,
    fee_type             TEXT NOT NULL
        CONSTRAINT tuition_fees_type_chk
        CHECK (fee_type IN ('tuition', 'registration', 'practical_information', 'not_published', 'other')),
    fee_scope            TEXT
        CONSTRAINT tuition_fees_scope_chk CHECK (fee_scope IN ('national', 'international')),
    tuition_fee          NUMERIC(12,2)
        CONSTRAINT tuition_fees_tuition_chk CHECK (tuition_fee >= 0),
    registration_fee     NUMERIC(12,2)
        CONSTRAINT tuition_fees_registration_chk CHECK (registration_fee >= 0),
    other_fees           TEXT,
    fee_currency         TEXT
        -- 2 à 3 caractères : les sources publient "DT" (dinar tunisien) et "EUR".
        CONSTRAINT tuition_fees_currency_chk CHECK (length(fee_currency) BETWEEN 2 AND 3),
    fee_period           TEXT,
    payment_terms        TEXT,
    campus_location      TEXT,
    contact_email        TEXT,
    contact_phone        TEXT,
    fee_status           TEXT NOT NULL
        CONSTRAINT tuition_fees_status_chk CHECK (fee_status IN ('published', 'not_published')),
    source_url           TEXT,
    source_title         TEXT,
    collection_date      TIMESTAMPTZ,
    document_language    TEXT,
    verification_status  TEXT NOT NULL DEFAULT 'collected_unverified'
        CONSTRAINT tuition_fees_verification_status_chk
        CHECK (verification_status IN
               ('collected_unverified', 'verified', 'derived_not_official_fact', 'needs_review')),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT tuition_fees_natural_key
        UNIQUE NULLS NOT DISTINCT (formation_id, fee_type, fee_scope, academic_year_label),
    CONSTRAINT tuition_fees_published_chk CHECK (
        fee_status <> 'published'
        OR (fee_currency IS NOT NULL
            AND (tuition_fee IS NOT NULL OR registration_fee IS NOT NULL OR other_fees IS NOT NULL))
    )
);

-- ---------------------------------------------------------------------------
-- Index utiles
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS ix_formations_etablissement ON formations (etablissement_id);
CREATE INDEX IF NOT EXISTS ix_formations_degree_level ON formations (degree_level_code);
CREATE INDEX IF NOT EXISTS ix_formations_academic_year ON formations (academic_year_label);
CREATE INDEX IF NOT EXISTS ix_admission_requirements_year ON admission_requirements (academic_year_label);
CREATE INDEX IF NOT EXISTS ix_academic_programs_formation ON academic_programs (formation_id);
CREATE INDEX IF NOT EXISTS ix_tuition_fees_formation ON tuition_fees (formation_id);
CREATE INDEX IF NOT EXISTS ix_tuition_fees_year ON tuition_fees (academic_year_label);
CREATE INDEX IF NOT EXISTS ix_tuition_fees_status ON tuition_fees (fee_status);

-- ---------------------------------------------------------------------------
-- Triggers updated_at (idempotents)
-- ---------------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_establishments_updated_at ON establishments;
CREATE TRIGGER trg_establishments_updated_at BEFORE UPDATE ON establishments
    FOR EACH ROW EXECUTE FUNCTION sc_set_updated_at();

DROP TRIGGER IF EXISTS trg_formations_updated_at ON formations;
CREATE TRIGGER trg_formations_updated_at BEFORE UPDATE ON formations
    FOR EACH ROW EXECUTE FUNCTION sc_set_updated_at();

DROP TRIGGER IF EXISTS trg_admission_requirements_updated_at ON admission_requirements;
CREATE TRIGGER trg_admission_requirements_updated_at BEFORE UPDATE ON admission_requirements
    FOR EACH ROW EXECUTE FUNCTION sc_set_updated_at();

DROP TRIGGER IF EXISTS trg_academic_programs_updated_at ON academic_programs;
CREATE TRIGGER trg_academic_programs_updated_at BEFORE UPDATE ON academic_programs
    FOR EACH ROW EXECUTE FUNCTION sc_set_updated_at();

DROP TRIGGER IF EXISTS trg_tuition_fees_updated_at ON tuition_fees;
CREATE TRIGGER trg_tuition_fees_updated_at BEFORE UPDATE ON tuition_fees
    FOR EACH ROW EXECUTE FUNCTION sc_set_updated_at();

COMMIT;
