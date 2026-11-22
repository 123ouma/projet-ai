-- Données de démonstration SA-13 — COMPTES FICTIFS UNIQUEMENT.
-- Aucune donnée personnelle réelle. Domaine réservé ".invalid".
-- password_hash contient un marqueur explicite NON secret : ce n'est pas un mot
-- de passe utilisable. L'application devra toujours générer un vrai hash.
-- Idempotent : ON CONFLICT DO NOTHING, aucune suppression.

BEGIN;

-- 8 rôles (dont les 4 responsables d'établissement IIT/ISB/ISA/2I2S)
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

-- Utilisateurs fictifs
INSERT INTO users (email, password_hash, full_name) VALUES
    ('candidat.demo@example.invalid', 'demo-only-not-a-real-password-hash', 'Candidat Démo'),
    ('resp.iit.demo@example.invalid', 'demo-only-not-a-real-password-hash', 'Responsable IIT Démo'),
    ('resp.isb.demo@example.invalid', 'demo-only-not-a-real-password-hash', 'Responsable ISB Démo'),
    ('resp.isa.demo@example.invalid', 'demo-only-not-a-real-password-hash', 'Responsable ISA Démo'),
    ('resp.2i2s.demo@example.invalid', 'demo-only-not-a-real-password-hash', 'Responsable 2I2S Démo'),
    ('direction.demo@example.invalid', 'demo-only-not-a-real-password-hash', 'Direction Démo'),
    ('admin.demo@example.invalid', 'demo-only-not-a-real-password-hash', 'Administrateur Démo')
ON CONFLICT (email) DO NOTHING;

-- Attributions de rôles, avec la portée obligatoire pour les responsables
INSERT INTO user_roles (user_id, role_code, scope_etablissement_id)
SELECT u.user_id, r.role_code, v.scope_etablissement_id
FROM (VALUES
    ('candidat.demo@example.invalid', 'candidat', NULL::text),
    ('resp.iit.demo@example.invalid', 'responsable_iit', 'IIT'),
    ('resp.isb.demo@example.invalid', 'responsable_isb', 'ISB'),
    ('resp.isa.demo@example.invalid', 'responsable_isa', 'ISA'),
    ('resp.2i2s.demo@example.invalid', 'responsable_2i2s', '2I2S'),
    ('direction.demo@example.invalid', 'direction', NULL::text),
    ('admin.demo@example.invalid', 'administrateur', NULL::text)
) AS v(email, role_code, scope_etablissement_id)
JOIN users u ON u.email = v.email
JOIN roles r ON r.role_code = v.role_code
ON CONFLICT (user_id, role_code, scope_etablissement_id) DO NOTHING;

-- Profil candidat fictif (valeurs génériques, aucune identité réelle)
INSERT INTO candidate_profiles (
    user_id, baccalaureate_type, baccalaureate_year, baccalaureate_grade,
    results_summary, interests, preferred_subjects, career_objectives, constraints_text
)
SELECT u.user_id, 'Baccalauréat général', 2025, 14.00,
       'Profil de démonstration sans donnée personnelle réelle.',
       ARRAY['informatique', 'données']::text[],
       ARRAY['mathématiques', 'informatique']::text[],
       'Objectif de démonstration.',
       'Aucune contrainte réelle déclarée.'
FROM users u
WHERE u.email = 'candidat.demo@example.invalid'
ON CONFLICT (user_id) DO NOTHING;

-- Une candidature fictive à l'état draft, sur une formation réellement collectée.
-- L'historique de statut est créé automatiquement par le trigger.
INSERT INTO candidatures (candidate_user_id, formation_id, status, motivation, last_changed_by)
SELECT u.user_id,
       (SELECT f.formation_id FROM formations f ORDER BY f.formation_id LIMIT 1),
       'draft',
       'Candidature de démonstration.',
       u.user_id
FROM users u
WHERE u.email = 'candidat.demo@example.invalid'
ON CONFLICT (candidate_user_id, formation_id, academic_year_label) DO NOTHING;

COMMIT;
