-- Requêtes de vérification manuelle (lecture seule) — SmartCampus AI
-- À exécuter après les migrations, l'import CSV et le seed :
--   psql "$DATABASE_URL" -f database/queries/verification.sql
-- Le rapport automatisé équivalent est produit par scripts/verify_database.py.

\echo '== Version PostgreSQL =='
SELECT version();

\echo '== Tables du schéma public =='
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;

\echo '== Volumes (attendus : 4/7/3/22/22/22/42/329/83/22/83) =='
SELECT 'establishments' AS table_name, count(*) FROM establishments
UNION ALL SELECT 'degree_levels', count(*) FROM degree_levels
UNION ALL SELECT 'academic_years', count(*) FROM academic_years
UNION ALL SELECT 'formations', count(*) FROM formations
UNION ALL SELECT 'admission_requirements', count(*) FROM admission_requirements
UNION ALL SELECT 'academic_programs', count(*) FROM academic_programs
UNION ALL SELECT 'tuition_fees', count(*) FROM tuition_fees
UNION ALL SELECT 'sources', count(*) FROM sources
UNION ALL SELECT 'documents', count(*) FROM documents
UNION ALL SELECT 'document_formations', count(*) FROM document_formations
UNION ALL SELECT 'document_versions', count(*) FROM document_versions
ORDER BY table_name;

\echo '== Clés étrangères =='
SELECT tc.table_name, tc.constraint_name, kcu.column_name,
       ccu.table_name AS referenced_table, ccu.column_name AS referenced_column
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
JOIN information_schema.constraint_column_usage ccu
  ON tc.constraint_name = ccu.constraint_name AND tc.table_schema = ccu.table_schema
WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'
ORDER BY tc.table_name, kcu.column_name;

\echo '== Intégrité référentielle (toutes les valeurs doivent être 0) =='
SELECT
  (SELECT count(*) FROM formations f LEFT JOIN establishments e
     ON e.etablissement_id = f.etablissement_id WHERE e.etablissement_id IS NULL)
    AS formations_orphelines,
  (SELECT count(*) FROM admission_requirements a LEFT JOIN formations f
     ON f.formation_id = a.formation_id WHERE f.formation_id IS NULL)
    AS admissions_orphelines,
  (SELECT count(*) FROM tuition_fees t LEFT JOIN formations f
     ON f.formation_id = t.formation_id WHERE f.formation_id IS NULL)
    AS tarifs_orphelins,
  (SELECT count(*) FROM document_formations df
     LEFT JOIN documents d ON d.document_id = df.document_id
     LEFT JOIN formations f ON f.formation_id = df.formation_id
     WHERE d.document_id IS NULL OR f.formation_id IS NULL)
    AS liaisons_orphelines,
  (SELECT count(*) FROM documents WHERE raw_path IS NULL OR sha256 !~ '^[0-9a-f]{64}$')
    AS documents_invalides;

\echo '== Doublons (toutes les valeurs doivent être 0) =='
SELECT
  (SELECT count(*) FROM (SELECT formation_id FROM formations
     GROUP BY formation_id HAVING count(*) > 1) q) AS dup_formations,
  (SELECT count(*) FROM (SELECT etablissement_id, formation_name FROM formations
     GROUP BY 1,2 HAVING count(*) > 1) q) AS dup_noms,
  (SELECT count(*) FROM (SELECT formation_id, fee_type, fee_scope, academic_year_label
     FROM tuition_fees GROUP BY 1,2,3,4 HAVING count(*) > 1) q) AS dup_tarifs,
  (SELECT count(*) FROM (SELECT email FROM users GROUP BY email HAVING count(*) > 1) q)
    AS dup_emails;

\echo '== Règles métier (toutes les valeurs doivent être 0) =='
SELECT
  (SELECT count(*) FROM tuition_fees
     WHERE fee_status = 'published' AND fee_currency IS NULL) AS tarifs_publies_sans_devise,
  (SELECT count(*) FROM candidatures
     WHERE status <> 'draft' AND (submitted_at IS NULL OR consent_given = false))
    AS candidatures_soumisses_invalides,
  (SELECT count(*) FROM documents WHERE rag_index_status = 'indexed') AS documents_indexes,
  (SELECT count(*) FROM (SELECT document_id FROM document_versions WHERE is_current
     GROUP BY document_id HAVING count(*) > 1) q) AS versions_courantes_multiples;

\echo '== Traçabilité : statistiques par établissement =='
SELECT e.etablissement_id,
       (SELECT count(*) FROM formations f WHERE f.etablissement_id = e.etablissement_id) AS formations,
       (SELECT count(*) FROM sources s WHERE s.etablissement_id = e.etablissement_id) AS sources,
       (SELECT count(*) FROM documents d WHERE d.etablissement_id = e.etablissement_id) AS documents
FROM establishments e
ORDER BY e.etablissement_id;

\echo '== Rôles attribués (fictifs) =='
SELECT r.role_code, count(*) AS utilisateurs
FROM user_roles ur JOIN roles r ON r.role_code = ur.role_code
GROUP BY r.role_code ORDER BY r.role_code;

\echo '== Historique des statuts =='
SELECT c.candidature_id, h.from_status, h.to_status, h.changed_at
FROM candidature_status_history h
JOIN candidatures c ON c.candidature_id = h.candidature_id
ORDER BY h.changed_at;
