-- SA-26 : mémoire temporaire des conversations.
-- Messages récents d'une session de chat, supprimés après expiration (inactivité).
-- session_id = identifiant de session visiteur (SA-25, Fares). La clé étrangère vers la
-- table des sessions sera ajoutée quand celle-ci existera.

CREATE TABLE conversation_memory (
    id         BIGSERIAL   PRIMARY KEY,
    session_id UUID        NOT NULL,
    role       VARCHAR(10) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content    TEXT        NOT NULL CHECK (length(content) > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_memory_session ON conversation_memory (session_id, id);
CREATE INDEX idx_memory_expires ON conversation_memory (expires_at);
