-- SA-25 : sessions anonymes, liées à la mémoire SA-26 par le même UUID.
-- Le secret porteur n'est jamais stocké en clair : seule son empreinte SHA-256 est conservée.
-- linked_user_id reste nullable jusqu'à la création du modèle de compte (SA-29).

CREATE TABLE visitor_sessions (
    session_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    token_hash      CHAR(64) NOT NULL UNIQUE
                    CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ NOT NULL,
    ended_at        TIMESTAMPTZ,
    linked_user_id  BIGINT,
    CONSTRAINT visitor_sessions_expiry_chk CHECK (expires_at > created_at),
    CONSTRAINT visitor_sessions_ended_chk CHECK (ended_at IS NULL OR ended_at >= created_at)
);

CREATE INDEX idx_visitor_sessions_expires ON visitor_sessions (expires_at);

COMMENT ON TABLE visitor_sessions IS
    'SA-25 : session visiteur; token_hash est le hash SHA-256 du cookie porteur.';
COMMENT ON COLUMN visitor_sessions.linked_user_id IS
    'Réservé au rattachement SA-29; clé étrangère à ajouter avec le modèle utilisateur.';

-- Les anciens messages SA-26 peuvent précéder la création des sessions.
-- NOT VALID les préserve, tout en imposant la relation pour les nouvelles écritures.
ALTER TABLE conversation_memory
    ADD CONSTRAINT fk_conversation_memory_visitor_session
    FOREIGN KEY (session_id)
    REFERENCES visitor_sessions (session_id)
    ON DELETE CASCADE
    NOT VALID;
