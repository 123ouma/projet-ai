-- DONNÉES DE DÉMONSTRATION — FICTIVES.
-- Formations, montants et conditions inventés pour tester les API.
-- À remplacer par les données réelles collectées dans SA-18 (Islem).
-- Idempotent : peut être relancé sans créer de doublons.

INSERT INTO etablissements (code, nom, ville) VALUES
    ('IIT',  'Institut International de Technologie', 'Sfax'),
    ('ISB',  'Établissement ISB (nom à compléter)',   'Sfax'),
    ('ISA',  'Établissement ISA (nom à compléter)',   'Sfax'),
    ('2i2s', 'Établissement 2i2s (nom à compléter)',  'Sfax')
ON CONFLICT (code) DO NOTHING;

INSERT INTO formations (etablissement_id, code, intitule, niveau, domaine, duree_annees, description)
SELECT e.id, v.code, v.intitule, v.niveau, v.domaine, v.duree, v.descr
FROM (VALUES
    ('IIT', 'DEMO-ING-GL', '[DÉMO] Cycle ingénieur en génie logiciel', 'ingenieur', 'Informatique', 3,
        'Formation fictive pour les tests.'),
    ('IIT', 'DEMO-LIC-INFO', '[DÉMO] Licence en informatique', 'licence', 'Informatique', 3,
        'Formation fictive pour les tests.'),
    ('ISB', 'DEMO-LIC-BA', '[DÉMO] Bachelor in Business Administration', 'licence', 'Gestion', 3,
        'Formation fictive pour les tests, enseignée en anglais.')
) AS v(etab, code, intitule, niveau, domaine, duree, descr)
JOIN etablissements e ON e.code = v.etab
ON CONFLICT (etablissement_id, code) DO NOTHING;

UPDATE formations SET langue_enseignement = 'anglais' WHERE code = 'DEMO-LIC-BA';

INSERT INTO programme_modules (formation_id, annee, semestre, intitule, credits, ordre)
SELECT f.id, v.annee, v.semestre, v.intitule, v.credits, v.ordre
FROM (VALUES
    ('DEMO-ING-GL', 1, 1, 'Algorithmique avancée', 5.0, 1),
    ('DEMO-ING-GL', 1, 1, 'Bases de données', 5.0, 2),
    ('DEMO-ING-GL', 1, 2, 'Génie logiciel', 6.0, 1),
    ('DEMO-LIC-BA', 1, 1, 'Principles of Management', 6.0, 1)
) AS v(code, annee, semestre, intitule, credits, ordre)
JOIN formations f ON f.code = v.code
WHERE NOT EXISTS (SELECT 1 FROM programme_modules p WHERE p.formation_id = f.id);

INSERT INTO tarifs (formation_id, annee_universitaire, frais_inscription, frais_scolarite, modalites_paiement)
SELECT f.id, '2026-2027', v.inscr, v.scol, 'Paiement en 3 tranches (exemple fictif)'
FROM (VALUES
    ('DEMO-ING-GL', 500.000, 7000.000),
    ('DEMO-LIC-INFO', 500.000, 5500.000),
    ('DEMO-LIC-BA', 500.000, 6000.000)
) AS v(code, inscr, scol)
JOIN formations f ON f.code = v.code
ON CONFLICT (formation_id, annee_universitaire) DO NOTHING;

INSERT INTO conditions_admission (formation_id, diplome_requis, niveau_acces, test_anglais_requis, pieces_requises)
SELECT f.id, v.diplome, v.niveau, v.anglais, v.pieces
FROM (VALUES
    ('DEMO-ING-GL', 'Licence ou cycle préparatoire', '1re année', FALSE,
        ARRAY['Copie du diplôme', 'Relevés de notes', 'Copie de la CIN']),
    ('DEMO-LIC-INFO', 'Baccalauréat', '1re année', FALSE,
        ARRAY['Copie du baccalauréat', 'Relevé de notes du bac', 'Copie de la CIN']),
    ('DEMO-LIC-BA', 'Baccalauréat', '1re année', TRUE,
        ARRAY['Copie du baccalauréat', 'Relevé de notes du bac', 'Copie de la CIN'])
) AS v(code, diplome, niveau, anglais, pieces)
JOIN formations f ON f.code = v.code
ON CONFLICT (formation_id) DO NOTHING;
