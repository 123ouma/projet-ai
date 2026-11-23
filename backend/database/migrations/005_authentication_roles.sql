-- SA-28 : comptes, rôles projet, sessions Bearer révocables.
-- Les seules valeurs de rôle viennent de la modélisation SA-13.

CREATE TABLE IF NOT EXISTS roles (
    role_code  TEXT PRIMARY KEY,
    label      TEXT NOT NULL UNIQUE,
    scope      TEXT NOT NULL CHECK (scope IN ('global', 'establishment')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
    user_id           BIGSERIAL PRIMARY KEY,
    email             TEXT NOT NULL UNIQUE
                      CHECK (email = lower(email) AND length(email) BETWEEN 3 AND 254),
    password_hash     TEXT NOT NULL CHECK (length(password_hash) > 0),
    full_name         VARCHAR(120),
    is_active         BOOLEAN NOT NULL DEFAULT true,
    email_verified_at TIMESTAMPTZ,
    last_login_at     TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS user_roles (
    user_role_id            BIGSERIAL PRIMARY KEY,
    user_id                 BIGINT NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
    role_code               TEXT NOT NULL REFERENCES roles (role_code) ON DELETE RESTRICT,
    scope_etablissement_id  TEXT REFERENCES etablissements (code) ON DELETE RESTRICT,
    assigned_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    assigned_by             BIGINT REFERENCES users (user_id) ON DELETE SET NULL,
    CONSTRAINT user_roles_natural_key
        UNIQUE NULLS NOT DISTINCT (user_id, role_code, scope_etablissement_id),
    CONSTRAINT user_roles_scope_required_chk CHECK (
        role_code NOT IN ('responsable_iit', 'responsable_isb',
                          'responsable_isa', 'responsable_2i2s')
        OR scope_etablissement_id IS NOT NULL
    ),
    CONSTRAINT user_roles_scope_chk CHECK (
        (role_code = 'responsable_iit' AND scope_etablissement_id = 'IIT') OR
        (role_code = 'responsable_isb' AND scope_etablissement_id = 'ISB') OR
        (role_code = 'responsable_isa' AND scope_etablissement_id = 'ISA') OR
        (role_code = 'responsable_2i2s' AND scope_etablissement_id = '2I2S') OR
        (role_code NOT IN ('responsable_iit', 'responsable_isb',
                           'responsable_isa', 'responsable_2i2s')
         AND scope_etablissement_id IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS ix_user_roles_user ON user_roles (user_id);
CREATE INDEX IF NOT EXISTS ix_user_roles_role ON user_roles (role_code);

CREATE TABLE IF NOT EXISTS user_auth_sessions (
    session_id  UUID PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
    token_hash  CHAR(64) NOT NULL UNIQUE CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL,
    revoked_at  TIMESTAMPTZ,
    CONSTRAINT user_auth_sessions_expiry_chk CHECK (expires_at > created_at)
);

CREATE INDEX IF NOT EXISTS ix_user_auth_sessions_user ON user_auth_sessions (user_id);
CREATE INDEX IF NOT EXISTS ix_user_auth_sessions_expires ON user_auth_sessions (expires_at);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger
        WHERE tgname = 'trg_users_updated_at'
          AND tgrelid = 'users'::regclass
          AND NOT tgisinternal
    ) THEN
        EXECUTE 'CREATE TRIGGER trg_users_updated_at BEFORE UPDATE ON users
            FOR EACH ROW EXECUTE FUNCTION set_updated_at()';
    END IF;
END;
$$;

INSERT INTO roles (role_code, label, scope) VALUES
    ('candidat', 'Candidat', 'global'),
    ('responsable_iit', 'Responsable IIT', 'establishment'),
    ('responsable_isb', 'Responsable ISB', 'establishment'),
    ('responsable_isa', 'Responsable ISA', 'establishment'),
    ('responsable_2i2s', 'Responsable 2I2S', 'establishment'),
    ('responsable_entretien', 'Responsable entretien', 'global'),
    ('direction', 'Direction', 'global'),
    ('administrateur', 'Administrateur', 'global')
ON CONFLICT (role_code) DO NOTHING;

ALTER TABLE visitor_sessions
    ADD CONSTRAINT visitor_sessions_linked_user_fk
    FOREIGN KEY (linked_user_id) REFERENCES users (user_id) ON DELETE SET NULL;
