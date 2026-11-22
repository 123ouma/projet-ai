-- SA-13 — Utilisateurs et candidatures (PostgreSQL 17)
-- Migration idempotente. Dépend de 001_catalogue.sql (formations, academic_years,
-- establishments). Aucun mot de passe en clair : seule la colonne password_hash existe.
-- Aucune table ni donnée existante n'est supprimée.

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. Rôles
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS roles (
    role_code  TEXT PRIMARY KEY,
    label      TEXT NOT NULL UNIQUE,
    scope      TEXT NOT NULL
        CONSTRAINT roles_scope_chk CHECK (scope IN ('global', 'establishment')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE roles IS '8 rôles : candidat, 4 responsables d''établissement, entretien, direction, administrateur.';

-- ---------------------------------------------------------------------------
-- 2. Utilisateurs
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    user_id           BIGSERIAL PRIMARY KEY,
    email             TEXT NOT NULL UNIQUE
        CONSTRAINT users_email_shape_chk CHECK (email LIKE '%@%' AND email = lower(email)),
    password_hash     TEXT NOT NULL
        CONSTRAINT users_password_hash_not_empty_chk CHECK (length(password_hash) > 0),
    full_name         TEXT,
    is_active         BOOLEAN NOT NULL DEFAULT true,
    email_verified_at TIMESTAMPTZ,
    last_login_at     TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON COLUMN users.password_hash IS 'Hash Argon2id/bcrypt produit par l''application. Aucun mot de passe en clair.';

-- ---------------------------------------------------------------------------
-- 3. Association utilisateurs ↔ rôles
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_roles (
    user_role_id             BIGSERIAL PRIMARY KEY,
    user_id                  BIGINT NOT NULL
        CONSTRAINT user_roles_user_fk
        REFERENCES users (user_id) ON DELETE CASCADE,
    role_code                TEXT NOT NULL
        CONSTRAINT user_roles_role_fk
        REFERENCES roles (role_code) ON DELETE RESTRICT,
    scope_etablissement_id   TEXT
        CONSTRAINT user_roles_etablissement_fk
        REFERENCES establishments (etablissement_id) ON DELETE RESTRICT,
    assigned_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    assigned_by              BIGINT
        CONSTRAINT user_roles_assigned_by_fk
        REFERENCES users (user_id) ON DELETE SET NULL,
    CONSTRAINT user_roles_natural_key
        UNIQUE NULLS NOT DISTINCT (user_id, role_code, scope_etablissement_id),
    -- Sans ce check, role_code = 'responsable_iit' ET scope = NULL rendrait
    -- l'expression ci-dessous NULL, donc le CHECK serait considéré comme vrai.
    CONSTRAINT user_roles_scope_required_chk CHECK (
        role_code NOT IN ('responsable_iit', 'responsable_isb',
                          'responsable_isa', 'responsable_2i2s')
        OR scope_etablissement_id IS NOT NULL
    ),
    CONSTRAINT user_roles_scope_chk CHECK (
        (role_code = 'responsable_iit'  AND scope_etablissement_id = 'IIT')  OR
        (role_code = 'responsable_isb'  AND scope_etablissement_id = 'ISB')  OR
        (role_code = 'responsable_isa'  AND scope_etablissement_id = 'ISA')  OR
        (role_code = 'responsable_2i2s' AND scope_etablissement_id = '2I2S') OR
        (role_code NOT IN ('responsable_iit', 'responsable_isb',
                           'responsable_isa', 'responsable_2i2s')
         AND scope_etablissement_id IS NULL)
    )
);

-- ---------------------------------------------------------------------------
-- 4. Profils candidats
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS candidate_profiles (
    profile_id            BIGSERIAL PRIMARY KEY,
    user_id               BIGINT NOT NULL UNIQUE
        CONSTRAINT candidate_profiles_user_fk
        REFERENCES users (user_id) ON DELETE CASCADE,
    baccalaureate_type    TEXT,
    baccalaureate_year    INTEGER
        CONSTRAINT candidate_profiles_bac_year_chk CHECK (baccalaureate_year BETWEEN 1950 AND 2100),
    baccalaureate_grade   NUMERIC(5,2)
        CONSTRAINT candidate_profiles_bac_grade_chk CHECK (baccalaureate_grade BETWEEN 0 AND 20),
    results_summary       TEXT,
    interests             TEXT[] NOT NULL DEFAULT '{}'
        CONSTRAINT candidate_profiles_interests_chk CHECK (cardinality(interests) <= 50),
    preferred_subjects    TEXT[] NOT NULL DEFAULT '{}'
        CONSTRAINT candidate_profiles_subjects_chk CHECK (cardinality(preferred_subjects) <= 50),
    career_objectives     TEXT,
    constraints_text      TEXT,
    additional_notes      TEXT,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- 5. Candidatures
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS candidatures (
    candidature_id        BIGSERIAL PRIMARY KEY,
    candidate_user_id     BIGINT NOT NULL
        CONSTRAINT candidatures_user_fk
        REFERENCES users (user_id) ON DELETE RESTRICT,
    formation_id          TEXT NOT NULL
        CONSTRAINT candidatures_formation_fk
        REFERENCES formations (formation_id) ON DELETE RESTRICT,
    academic_year_label   TEXT
        CONSTRAINT candidatures_academic_year_fk
        REFERENCES academic_years (label) ON DELETE RESTRICT,
    status                TEXT NOT NULL DEFAULT 'draft'
        CONSTRAINT candidatures_status_chk
        CHECK (status IN ('draft', 'submitted', 'under_review', 'interview_scheduled',
                          'accepted', 'rejected', 'withdrawn')),
    consent_given         BOOLEAN NOT NULL DEFAULT false,
    consent_given_at      TIMESTAMPTZ,
    submitted_at          TIMESTAMPTZ,
    motivation            TEXT,
    last_changed_by       BIGINT
        CONSTRAINT candidatures_last_changed_by_fk
        REFERENCES users (user_id) ON DELETE SET NULL,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT candidatures_natural_key
        UNIQUE NULLS NOT DISTINCT (candidate_user_id, formation_id, academic_year_label),
    CONSTRAINT candidatures_submitted_chk CHECK (
        status = 'draft' OR (submitted_at IS NOT NULL AND consent_given)
    ),
    CONSTRAINT candidatures_consent_chk CHECK (
        consent_given = false OR consent_given_at IS NOT NULL
    )
);

-- ---------------------------------------------------------------------------
-- 6. Historique des statuts (alimenté par triggers)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS candidature_status_history (
    history_id     BIGSERIAL PRIMARY KEY,
    candidature_id BIGINT NOT NULL
        CONSTRAINT candidature_status_history_candidature_fk
        REFERENCES candidatures (candidature_id) ON DELETE CASCADE,
    from_status    TEXT
        CONSTRAINT candidature_status_history_from_chk
        CHECK (from_status IN ('draft', 'submitted', 'under_review', 'interview_scheduled',
                               'accepted', 'rejected', 'withdrawn')),
    to_status      TEXT NOT NULL
        CONSTRAINT candidature_status_history_to_chk
        CHECK (to_status IN ('draft', 'submitted', 'under_review', 'interview_scheduled',
                             'accepted', 'rejected', 'withdrawn')),
    changed_by     BIGINT
        CONSTRAINT candidature_status_history_changed_by_fk
        REFERENCES users (user_id) ON DELETE SET NULL,
    changed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    reason         TEXT,
    CONSTRAINT candidature_status_history_no_self_transition_chk
        CHECK (from_status IS NULL OR from_status <> to_status)
);

COMMENT ON TABLE candidature_status_history IS 'Alimenté automatiquement : ne pas insérer directement.';

-- ---------------------------------------------------------------------------
-- Index utiles
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS ix_user_roles_role ON user_roles (role_code);
CREATE INDEX IF NOT EXISTS ix_user_roles_scope ON user_roles (scope_etablissement_id);
CREATE INDEX IF NOT EXISTS ix_candidatures_candidate ON candidatures (candidate_user_id);
CREATE INDEX IF NOT EXISTS ix_candidatures_formation ON candidatures (formation_id);
CREATE INDEX IF NOT EXISTS ix_candidatures_year ON candidatures (academic_year_label);
CREATE INDEX IF NOT EXISTS ix_candidatures_status ON candidatures (status);
CREATE INDEX IF NOT EXISTS ix_candidature_status_history_candidature
    ON candidature_status_history (candidature_id, changed_at);

-- ---------------------------------------------------------------------------
-- Triggers
-- ---------------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_users_updated_at ON users;
CREATE TRIGGER trg_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION sc_set_updated_at();

DROP TRIGGER IF EXISTS trg_candidate_profiles_updated_at ON candidate_profiles;
CREATE TRIGGER trg_candidate_profiles_updated_at BEFORE UPDATE ON candidate_profiles
    FOR EACH ROW EXECUTE FUNCTION sc_set_updated_at();

DROP TRIGGER IF EXISTS trg_candidatures_updated_at ON candidatures;
CREATE TRIGGER trg_candidatures_updated_at BEFORE UPDATE ON candidatures
    FOR EACH ROW EXECUTE FUNCTION sc_set_updated_at();

CREATE OR REPLACE FUNCTION sc_record_candidature_status() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO candidature_status_history
            (candidature_id, from_status, to_status, changed_by, changed_at)
        VALUES (NEW.candidature_id, NULL, NEW.status, NEW.last_changed_by,
                COALESCE(NEW.created_at, now()));
        RETURN NEW;
    END IF;

    IF TG_OP = 'UPDATE' THEN
        INSERT INTO candidature_status_history
            (candidature_id, from_status, to_status, changed_by, changed_at)
        VALUES (NEW.candidature_id, OLD.status, NEW.status, NEW.last_changed_by, now());
        RETURN NEW;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_candidatures_insert_status ON candidatures;
CREATE TRIGGER trg_candidatures_insert_status
    AFTER INSERT ON candidatures
    FOR EACH ROW EXECUTE FUNCTION sc_record_candidature_status();

DROP TRIGGER IF EXISTS trg_candidatures_update_status ON candidatures;
CREATE TRIGGER trg_candidatures_update_status
    AFTER UPDATE OF status ON candidatures
    FOR EACH ROW
    WHEN (OLD.status IS DISTINCT FROM NEW.status)
    EXECUTE FUNCTION sc_record_candidature_status();

COMMIT;
