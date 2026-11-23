-- SA-20 / SA-21 : catalogue académique (établissements, formations, programmes,
-- tarifs, conditions d'admission).
-- NB : à aligner avec la modélisation du catalogue (SA-12) et les tables de SA-17 (Islem).
-- Si SA-17 crée déjà ces tables, garder une seule version et supprimer le doublon.

CREATE TABLE etablissements (
    id         SMALLSERIAL PRIMARY KEY,
    code       VARCHAR(10)  NOT NULL UNIQUE,          -- IIT, ISB, ISA, 2i2s
    nom        TEXT         NOT NULL,
    ville      TEXT,
    site_web   TEXT,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE formations (
    id                  SERIAL PRIMARY KEY,
    etablissement_id    SMALLINT     NOT NULL REFERENCES etablissements(id) ON DELETE RESTRICT,
    code                VARCHAR(30)  NOT NULL,
    intitule            TEXT         NOT NULL,
    niveau              VARCHAR(20)  NOT NULL
        CHECK (niveau IN ('preparatoire', 'licence', 'ingenieur', 'master', 'autre')),
    domaine             TEXT,
    duree_annees        SMALLINT     NOT NULL CHECK (duree_annees BETWEEN 1 AND 6),
    langue_enseignement TEXT         NOT NULL DEFAULT 'français',
    description         TEXT,
    actif               BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (etablissement_id, code)
);
CREATE INDEX idx_formations_niveau ON formations (niveau) WHERE actif;
CREATE TRIGGER trg_formations_updated BEFORE UPDATE ON formations
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Programme d'études : modules par année et semestre
CREATE TABLE programme_modules (
    id             SERIAL PRIMARY KEY,
    formation_id   INTEGER      NOT NULL REFERENCES formations(id) ON DELETE CASCADE,
    annee          SMALLINT     NOT NULL CHECK (annee BETWEEN 1 AND 6),
    semestre       SMALLINT     NOT NULL CHECK (semestre IN (1, 2)),
    intitule       TEXT         NOT NULL,
    credits        NUMERIC(4,1) CHECK (credits >= 0),
    volume_horaire INTEGER      CHECK (volume_horaire >= 0),
    ordre          SMALLINT     NOT NULL DEFAULT 0
);
CREATE INDEX idx_programme_formation ON programme_modules (formation_id, annee, semestre, ordre);

-- Tarifs par année universitaire (montants en dinars, 3 décimales = millimes)
CREATE TABLE tarifs (
    id                  SERIAL PRIMARY KEY,
    formation_id        INTEGER       NOT NULL REFERENCES formations(id) ON DELETE CASCADE,
    annee_universitaire VARCHAR(9)    NOT NULL CHECK (annee_universitaire ~ '^\d{4}-\d{4}$'),
    frais_inscription   NUMERIC(10,3) NOT NULL DEFAULT 0 CHECK (frais_inscription >= 0),
    frais_scolarite     NUMERIC(10,3) NOT NULL CHECK (frais_scolarite >= 0),
    devise              CHAR(3)       NOT NULL DEFAULT 'TND',
    modalites_paiement  TEXT,
    remarques           TEXT,
    updated_at          TIMESTAMPTZ   NOT NULL DEFAULT now(),
    UNIQUE (formation_id, annee_universitaire)
);
CREATE TRIGGER trg_tarifs_updated BEFORE UPDATE ON tarifs
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Conditions d'admission : une fiche par formation
CREATE TABLE conditions_admission (
    formation_id        INTEGER      PRIMARY KEY REFERENCES formations(id) ON DELETE CASCADE,
    diplome_requis      TEXT         NOT NULL,
    niveau_acces        TEXT,                         -- ex. « 1re année », « 3e année »
    moyenne_minimale    NUMERIC(4,2) CHECK (moyenne_minimale BETWEEN 0 AND 20),
    test_anglais_requis BOOLEAN      NOT NULL DEFAULT FALSE,  -- QCM ISB
    entretien_requis    BOOLEAN      NOT NULL DEFAULT TRUE,
    pieces_requises     TEXT[]       NOT NULL DEFAULT '{}',
    description         TEXT,
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_conditions_updated BEFORE UPDATE ON conditions_admission
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
