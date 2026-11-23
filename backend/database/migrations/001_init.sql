-- SA-16 : initialisation de la base SmartCampus AI
-- Fonction commune : met à jour automatiquement la colonne updated_at.

CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
