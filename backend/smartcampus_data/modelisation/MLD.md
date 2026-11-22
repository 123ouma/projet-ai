# MLD — Modèle Logique de Données (SmartCampus AI)

Version : 1.0 — PostgreSQL 17.
Convention : `PK` clé primaire, `FK` clé étrangère, `U` unicité, `CHK` contrainte de vérification, `IX` index.
`␀` signifie `NULL` autorisé. `∅` signifie `NOT NULL`.

> Ce document est la référence unique des types et contraintes. Les migrations `database/migrations/00*.sql` doivent lui correspondre exactement.

---

## 1. Domaine catalogue — SA-12

### `establishments` — Établissements
| Colonne | Type | Contraintes | Origine CSV |
|---|---|---|---|
| `etablissement_id` | `TEXT` | PK, `∅` | `etablissements.etablissement_id` |
| `name` | `TEXT` | `∅` | `name` |
| `short_name` | `TEXT` | ␀ | `short_name` |
| `country` | `TEXT` | ␀ | `country` |
| `city` | `TEXT` | ␀ | `city` |
| `website_url` | `TEXT` | ␀ | `website_url` |
| `official_name_source_url` | `TEXT` | ␀ | `official_name_source_url` |
| `contact_email` | `TEXT` | ␀ | `contact_email` |
| `contact_phone` | `TEXT` | ␀ | `contact_phone` |
| `campus_location` | `TEXT` | ␀ | `campus_location` |
| `collection_date` | `TIMESTAMPTZ` | ␀ | `collection_date` |
| `document_language` | `TEXT` | ␀ | `document_language` |
| `verification_status` | `TEXT` | `∅`, CHK domaine, défaut `collected_unverified` | `verification_status` |
| `created_at` | `TIMESTAMPTZ` | `∅`, défaut `now()` | technique |
| `updated_at` | `TIMESTAMPTZ` | `∅`, défaut `now()` | technique |

### `degree_levels` — Niveaux de diplôme (référence)
| Colonne | Type | Contraintes | Origine |
|---|---|---|---|
| `code` | `TEXT` | PK, `∅` | slug déterministe du libellé observé |
| `label` | `TEXT` | `∅`, U | `formations.degree_type` (7 valeurs distinctes) |
| `created_at` | `TIMESTAMPTZ` | `∅`, défaut `now()` | technique |

Le `code` est une **clé technique dérivée** du libellé officiel, jamais une donnée inventée : `Cycle ingénieur → cycle-ingenieur`, etc. Aucune insertion d'un libellé non observé.

### `academic_years` — Années universitaires (référence)
| Colonne | Type | Contraintes | Origine |
|---|---|---|---|
| `label` | `TEXT` | PK, `∅` | `academic_year`, `admission_year`, `fee_academic_year` |
| `start_year` | `INTEGER` | `∅`, CHK `1900..2200` | dérivé mécaniquement du libellé |
| `end_year` | `INTEGER` | ␀, CHK `1900..2200`, `> start_year` | dérivé ; `NULL` pour `2026` |
| `created_at` | `TIMESTAMPTZ` | `∅`, défaut `now()` | technique |

Règles de dérivation : `AAAA/BBBB → start=AAAA, end=BBBB` ; `AAAA-BBBB → start=AAAA, end=BBBB` ; `AAAA → start=AAAA, end=NULL`.

### `formations` — Formations
| Colonne | Type | Contraintes | Origine CSV |
|---|---|---|---|
| `formation_id` | `TEXT` | PK, `∅` | `formation_id` |
| `etablissement_id` | `TEXT` | `∅`, FK → `establishments`, IX | `etablissement_id` |
| `degree_level_code` | `TEXT` | ␀, FK → `degree_levels`, IX | `degree_type` |
| `academic_year_label` | `TEXT` | ␀, FK → `academic_years`, IX | `academic_year` |
| `formation_name` | `TEXT` | `∅` | `formation_name` |
| `field` | `TEXT` | ␀ | `field` |
| `speciality` | `TEXT` | ␀ | `speciality` |
| `description` | `TEXT` | ␀ | `description` |
| `duration_years` | `NUMERIC(4,1)` | ␀, CHK `> 0` | `duration_years` (`2`, `3`, `6`, vide) |
| `language` | `TEXT` | ␀ | `language` (`fr`, `fr\|en`) |
| `study_mode` | `TEXT` | ␀ | `study_mode` |
| `diploma_awarded` | `TEXT` | ␀ | `diploma_awarded` |
| `career_opportunities` | `TEXT` | ␀ | `career_opportunities` |
| `further_studies` | `TEXT` | ␀ | `further_studies` |
| `career_field` | `TEXT` | ␀ | `career_field` |
| `bridges` | `TEXT` | ␀ | `bridges` |
| `recommended_profile` | `TEXT` | ␀ | `recommended_profile` |
| `interest_tags` | `TEXT` | ␀ | `interest_tags` (liste séparée par ` \| `, conservée telle quelle) |
| `interest_tags_origin` | `TEXT` | ␀ | `interest_tags_origin` |
| `prerequisite_skills` | `TEXT` | ␀ | `prerequisite_skills` |
| `source_url` | `TEXT` | ␀ | `source_url` |
| `source_title` | `TEXT` | ␀ | `source_title` |
| `source_type` | `TEXT` | ␀ | `source_type` |
| `collection_date` | `TIMESTAMPTZ` | ␀ | `collection_date` |
| `last_verified_at` | `TIMESTAMPTZ` | ␀ | `last_verified_at` |
| `verification_status` | `TEXT` | `∅`, CHK, défaut `collected_unverified` | `verification_status` |
| `document_language` | `TEXT` | ␀ | `document_language` |
| `created_at` | `TIMESTAMPTZ` | `∅`, défaut `now()` | technique |
| `updated_at` | `TIMESTAMPTZ` | `∅`, défaut `now()` | technique |
| **U** | | `UNIQUE (etablissement_id, formation_name)` | contrôle anti-doublon |

> `interest_tags` est une dénormalisation **volontaire et documentée** : les tags sont des métadonnées dérivées par règles fixes, jamais utilisées comme clé de jointure. Le format d'origine (` \| `) est conservé pour rester fidèle à SA-18.

### `admission_requirements` — Conditions d'admission
| Colonne | Type | Contraintes | Origine CSV |
|---|---|---|---|
| `admission_id` | `TEXT` | PK, `∅` | `admission_id` |
| `formation_id` | `TEXT` | `∅`, FK → `formations`, **U**, IX | `formation_id` |
| `academic_year_label` | `TEXT` | ␀, FK → `academic_years`, IX | `admission_year` |
| `required_baccalaureate` | `TEXT` | ␀ | `required_baccalaureate` |
| `minimum_grade` | `NUMERIC(5,2)` | ␀, CHK `0..20` | `minimum_grade` (vide dans 22/22 cas → `NULL`) |
| `required_level` | `TEXT` | ␀ | `required_level` |
| `admission_method` | `TEXT` | ␀ | `admission_method` |
| `required_documents` | `TEXT` | ␀ | `required_documents` |
| `registration_period` | `TEXT` | ␀ | `registration_period` |
| `special_conditions` | `TEXT` | ␀ | `special_conditions` |
| `source_url` | `TEXT` | ␀ | `source_url` |
| `source_title` | `TEXT` | ␀ | `source_title` |
| `collection_date` | `TIMESTAMPTZ` | ␀ | `collection_date` |
| `document_language` | `TEXT` | ␀ | `document_language` |
| `verification_status` | `TEXT` | `∅`, CHK, défaut `collected_unverified` | `verification_status` |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | `∅`, défaut `now()` | technique |

> La colonne `etablissement_id` du CSV sert uniquement au contrôle de cohérence pendant l'import ; elle n'est **pas** dupliquée en base (3NF).

### `academic_programs` — Programmes académiques
| Colonne | Type | Contraintes | Origine CSV |
|---|---|---|---|
| `programme_id` | `TEXT` | PK, `∅` | `programme_id` |
| `formation_id` | `TEXT` | `∅`, FK → `formations`, **U**, IX | `formation_id` |
| `subjects` | `TEXT` | ␀ | `subjects` |
| `modules` | `TEXT` | ␀ | `modules` |
| `semester_count` | `INTEGER` | ␀, CHK `1..12` | `semester_count` (`2`, vide) |
| `internships` | `TEXT` | ␀ | `internships` |
| `projects` | `TEXT` | ␀ | `projects` |
| `specializations` | `TEXT` | ␀ | `specializations` |
| `skills_acquired` | `TEXT` | ␀ | `skills_acquired` |
| `source_url` | `TEXT` | ␀ | `source_url` |
| `source_title` | `TEXT` | ␀ | `source_title` |
| `collection_date` | `TIMESTAMPTZ` | ␀ | `collection_date` |
| `document_language` | `TEXT` | ␀ | `document_language` |
| `verification_status` | `TEXT` | `∅`, CHK, défaut `collected_unverified` | `verification_status` |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | `∅`, défaut `now()` | technique |

### `tuition_fees` — Frais de scolarité
| Colonne | Type | Contraintes | Origine CSV |
|---|---|---|---|
| `tarif_id` | `TEXT` | PK, `∅` | `tarif_id` |
| `formation_id` | `TEXT` | `∅`, FK → `formations`, IX | `formation_id` |
| `academic_year_label` | `TEXT` | ␀, FK → `academic_years`, IX | `fee_academic_year` |
| `fee_type` | `TEXT` | `∅`, CHK `tuition / registration / practical_information / not_published / other` | `fee_type` |
| `fee_scope` | `TEXT` | ␀, CHK `national / international` | `fee_scope` |
| `tuition_fee` | `NUMERIC(12,2)` | ␀, CHK `>= 0` | `tuition_fee` |
| `registration_fee` | `NUMERIC(12,2)` | ␀, CHK `>= 0` | `registration_fee` |
| `other_fees` | `TEXT` | ␀ | `other_fees` |
| `fee_currency` | `TEXT` | ␀, CHK `length BETWEEN 2 AND 3` (`DT`, `EUR` observés) | `fee_currency` |
| `fee_period` | `TEXT` | ␀ | `fee_period` |
| `payment_terms` | `TEXT` | ␀ | `payment_terms` |
| `campus_location` | `TEXT` | ␀ | `campus_location` |
| `contact_email` | `TEXT` | ␀ | `contact_email` |
| `contact_phone` | `TEXT` | ␀ | `contact_phone` |
| `fee_status` | `TEXT` | `∅`, CHK `published / not_published` | `fee_status` |
| `source_url` | `TEXT` | ␀ | `source_url` |
| `source_title` | `TEXT` | ␀ | `source_title` |
| `collection_date` | `TIMESTAMPTZ` | ␀ | `collection_date` |
| `document_language` | `TEXT` | ␀ | `document_language` |
| `verification_status` | `TEXT` | `∅`, CHK, défaut `collected_unverified` | `verification_status` |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | `∅`, défaut `now()` | technique |
| **U** | | `UNIQUE NULLS NOT DISTINCT (formation_id, fee_type, fee_scope, academic_year_label)` | 0 doublon observé |
| **CHK** | | `fee_status <> 'published' OR (fee_currency IS NOT NULL AND (tuition_fee IS NOT NULL OR registration_fee IS NOT NULL OR other_fees IS NOT NULL))` | RG-CAT-02 |

---

## 2. Domaine utilisateurs — SA-13

### `roles`
| Colonne | Type | Contraintes |
|---|---|---|
| `role_code` | `TEXT` | PK, `∅` |
| `label` | `TEXT` | `∅`, U |
| `scope` | `TEXT` | `∅`, CHK `global / establishment` |
| `created_at` | `TIMESTAMPTZ` | `∅`, défaut `now()` |

8 rôles : `candidat`, `responsable_iit`, `responsable_isb`, `responsable_isa`, `responsable_2i2s`, `responsable_entretien`, `direction`, `administrateur`.

### `users`
| Colonne | Type | Contraintes |
|---|---|---|
| `user_id` | `BIGSERIAL` | PK |
| `email` | `TEXT` | `∅`, U, CHK `email = lower(email)` et format minimal `@` |
| `password_hash` | `TEXT` | `∅`, CHK `<> ''` — **aucun mot de passe en clair** |
| `full_name` | `TEXT` | ␀ |
| `is_active` | `BOOLEAN` | `∅`, défaut `true` |
| `email_verified_at` | `TIMESTAMPTZ` | ␀ |
| `last_login_at` | `TIMESTAMPTZ` | ␀ |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | `∅`, défaut `now()` |

### `user_roles`
| Colonne | Type | Contraintes |
|---|---|---|
| `user_role_id` | `BIGSERIAL` | PK technique |
| `user_id` | `BIGINT` | `∅`, FK → `users` `ON DELETE CASCADE` |
| `role_code` | `TEXT` | `∅`, FK → `roles` |
| `scope_etablissement_id` | `TEXT` | ␀, FK → `establishments`, IX |
| `assigned_at` | `TIMESTAMPTZ` | `∅`, défaut `now()` |
| `assigned_by` | `BIGINT` | ␀, FK → `users` |
| **U** | | `UNIQUE NULLS NOT DISTINCT (user_id, role_code, scope_etablissement_id)` — clé naturelle, y compris quand la portée est `NULL`. |
| **CHK** | | (1) Un rôle `responsable_<étab>` exige un établissement non `NULL` ; (2) il doit correspondre exactement à IIT/ISB/ISA/2I2S ; aucun autre rôle ne peut en porter un. |

> PostgreSQL 17 accepte `UNIQUE NULLS NOT DISTINCT` mais pas `PRIMARY KEY (...) NULLS NOT DISTINCT` : la clé primaire est donc technique (`user_role_id`) et l'unicité métier est portée par la contrainte `UNIQUE`.

### `candidate_profiles`
| Colonne | Type | Contraintes |
|---|---|---|
| `profile_id` | `BIGSERIAL` | PK |
| `user_id` | `BIGINT` | `∅`, U, FK → `users` `ON DELETE CASCADE` |
| `baccalaureate_type` | `TEXT` | ␀ |
| `baccalaureate_year` | `INTEGER` | ␀, CHK `1950..2100` |
| `baccalaureate_grade` | `NUMERIC(5,2)` | ␀, CHK `0..20` |
| `results_summary` | `TEXT` | ␀ |
| `interests` | `TEXT[]` | `∅`, défaut `{}`, CHK `cardinality <= 50` |
| `preferred_subjects` | `TEXT[]` | `∅`, défaut `{}`, CHK `cardinality <= 50` |
| `career_objectives` | `TEXT` | ␀ |
| `constraints_text` | `TEXT` | ␀ |
| `additional_notes` | `TEXT` | ␀ |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | `∅`, défaut `now()` |

### `candidatures`
| Colonne | Type | Contraintes |
|---|---|---|
| `candidature_id` | `BIGSERIAL` | PK |
| `candidate_user_id` | `BIGINT` | `∅`, FK → `users`, IX |
| `formation_id` | `TEXT` | `∅`, FK → `formations`, IX |
| `academic_year_label` | `TEXT` | ␀, FK → `academic_years`, IX |
| `status` | `TEXT` | `∅`, CHK `draft / submitted / under_review / interview_scheduled / accepted / rejected / withdrawn`, défaut `draft` |
| `consent_given` | `BOOLEAN` | `∅`, défaut `false` |
| `consent_given_at` | `TIMESTAMPTZ` | ␀ |
| `submitted_at` | `TIMESTAMPTZ` | ␀ |
| `motivation` | `TEXT` | ␀ |
| `last_changed_by` | `BIGINT` | ␀, FK → `users` |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | `∅`, défaut `now()` |
| **U** | | `UNIQUE NULLS NOT DISTINCT (candidate_user_id, formation_id, academic_year_label)` |
| **CHK** | | `status = 'draft' OR (submitted_at IS NOT NULL AND consent_given)` |
| **CHK** | | `consent_given = false OR consent_given_at IS NOT NULL` |

### `candidature_status_history`
| Colonne | Type | Contraintes |
|---|---|---|
| `history_id` | `BIGSERIAL` | PK |
| `candidature_id` | `BIGINT` | `∅`, FK → `candidatures` `ON DELETE CASCADE`, IX |
| `from_status` | `TEXT` | ␀, CHK domaine |
| `to_status` | `TEXT` | `∅`, CHK domaine |
| `changed_by` | `BIGINT` | ␀, FK → `users` |
| `changed_at` | `TIMESTAMPTZ` | `∅`, défaut `now()` |
| `reason` | `TEXT` | ␀ |
| **CHK** | | `from_status IS NULL OR from_status <> to_status` |

L'historique est alimenté **automatiquement par triggers** : insertion de la transition initiale à la création d'une candidature, puis une ligne à chaque changement de `status`. L'application ne doit pas insérer directement dans cette table.

---

## 3. Domaine documents — SA-14

### `sources`
| Colonne | Type | Contraintes | Origine CSV |
|---|---|---|---|
| `source_id` | `TEXT` | PK, `∅` | `source_id` |
| `etablissement_id` | `TEXT` | ␀, FK → `establishments`, IX | `etablissement_id` |
| `formation_id` | `TEXT` | ␀, FK → `formations`, IX | `formation_id` |
| `source_url` | `TEXT` | `∅` | `source_url` |
| `source_title` | `TEXT` | ␀ | `source_title` |
| `source_type` | `TEXT` | `∅`, CHK `html / pdf / api / other` | `source_type` |
| `attribute` | `TEXT` | ␀ | `attribute` |
| `value_excerpt` | `TEXT` | ␀ | `value_excerpt` |
| `raw_path` | `TEXT` | ␀ | `raw_path` |
| `value_origin` | `TEXT` | ␀, CHK domaine des 5 origines | `value_origin` |
| `document_language` | `TEXT` | ␀ | `document_language` |
| `collection_date` | `TIMESTAMPTZ` | ␀ | `collection_date` |
| `last_verified_at` | `TIMESTAMPTZ` | ␀ | `last_verified_at` |
| `http_status` | `INTEGER` | ␀, CHK `100..599` | `http_status` |
| `verification_status` | `TEXT` | `∅`, CHK, défaut `collected_unverified` | `verification_status` |
| `evidence_excerpt` | `TEXT` | ␀ | `evidence_excerpt` |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | `∅`, défaut `now()` | technique |

### `documents`
| Colonne | Type | Contraintes | Origine CSV |
|---|---|---|---|
| `document_id` | `TEXT` | PK, `∅` | `document_id` |
| `etablissement_id` | `TEXT` | ␀, FK → `establishments`, IX | `etablissement_id` |
| `document_type` | `TEXT` | `∅`, CHK `html / pdf / doc / docx / xlsx / other` | `document_type` |
| `title` | `TEXT` | ␀ | `title` |
| `url` | `TEXT` | `∅` | `url` |
| `parent_url` | `TEXT` | ␀ | `parent_url` |
| `raw_path` | `TEXT` | `∅` — chemin local traçable | `raw_path` |
| `metadata_path` | `TEXT` | ␀ | `metadata_path` |
| `sha256` | `TEXT` | `∅`, CHK `^[0-9a-f]{64}$` | `sha256` |
| `byte_size` | `BIGINT` | ␀, CHK `>= 0` | `byte_size` |
| `http_status` | `INTEGER` | ␀, CHK `100..599` | `http_status` |
| `content_type` | `TEXT` | ␀ | `content_type` |
| `language` | `TEXT` | ␀ | `language` |
| `text_chars` | `INTEGER` | ␀, CHK `>= 0` | `text_chars` |
| `page_count` | `INTEGER` | ␀, CHK `>= 0` | `page_count` |
| `collection_date` | `TIMESTAMPTZ` | `∅` | `collection_date` |
| `last_verified_at` | `TIMESTAMPTZ` | ␀ | non présent dans SA-18 → `NULL` |
| `sync_status` | `TEXT` | `∅`, CHK `pending / collected / synced / failed / stale`, défaut `collected` | état déduit de la collecte réelle |
| `last_error_message` | `TEXT` | ␀ | `error` (vide partout → `NULL`) |
| `verification_status` | `TEXT` | ␀, CHK | non présent dans `documents.csv` → `NULL` (aucune valeur supposée) |
| `academic_year_label` | `TEXT` | ␀, FK → `academic_years` | non présent dans SA-18 → `NULL` |
| `rag_index_status` | `TEXT` | `∅`, CHK `not_indexed / eligible / indexed / excluded`, défaut `not_indexed` | état futur, aucun document marqué `indexed` |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | `∅`, défaut `now()` | technique |
| **U** | | `UNIQUE (etablissement_id, url)` | anti-doublon |

### `document_formations`
| Colonne | Type | Contraintes |
|---|---|---|
| `document_id` | `TEXT` | PK (composite), FK → `documents` `ON DELETE CASCADE` |
| `formation_id` | `TEXT` | PK (composite), FK → `formations` `ON DELETE CASCADE` |
| `created_at` | `TIMESTAMPTZ` | `∅`, défaut `now()` |

### `sync_history`
| Colonne | Type | Contraintes |
|---|---|---|
| `sync_id` | `BIGSERIAL` | PK |
| `source_id` | `TEXT` | ␀, FK → `sources` |
| `document_id` | `TEXT` | ␀, FK → `documents` |
| `sync_type` | `TEXT` | `∅`, CHK `full / incremental / verification / retry` |
| `sync_status` | `TEXT` | `∅`, CHK `started / success / failed / partial` |
| `started_at` | `TIMESTAMPTZ` | `∅`, défaut `now()` |
| `finished_at` | `TIMESTAMPTZ` | ␀ |
| `http_status` | `INTEGER` | ␀, CHK `100..599` |
| `error_message` | `TEXT` | ␀ |
| `items_processed` / `items_created` / `items_updated` / `items_failed` | `INTEGER` | ␀, CHK `>= 0` |
| `triggered_by` | `TEXT` | ␀ |
| **CHK** | | `source_id IS NOT NULL OR document_id IS NOT NULL` |
| **CHK** | | `finished_at IS NULL OR finished_at >= started_at` |
| **CHK** | | `sync_status <> 'failed' OR error_message IS NOT NULL` |

### `document_versions`
| Colonne | Type | Contraintes |
|---|---|---|
| `version_id` | `BIGSERIAL` | PK |
| `document_id` | `TEXT` | `∅`, FK → `documents` `ON DELETE CASCADE` |
| `version_number` | `INTEGER` | `∅`, CHK `> 0` |
| `sha256` | `TEXT` | `∅`, CHK `^[0-9a-f]{64}$` |
| `raw_path` | `TEXT` | `∅` |
| `byte_size` | `BIGINT` | ␀, CHK `>= 0` |
| `collected_at` | `TIMESTAMPTZ` | `∅`, défaut `now()` |
| `change_detected_at` | `TIMESTAMPTZ` | ␀ |
| `is_current` | `BOOLEAN` | `∅`, défaut `false` |
| **U** | | `UNIQUE (document_id, version_number)` |
| **U partiel** | | `UNIQUE (document_id) WHERE is_current` — une seule version courante |

---

## 4. Récapitulatif des cardinalités physiques

| FK | Cardinalité | Action sur suppression |
|---|---|---|
| `formations.etablissement_id → establishments` | N:1 obligatoire | `RESTRICT` |
| `formations.degree_level_code → degree_levels` | N:1 optionnelle | `RESTRICT` |
| `formations.academic_year_label → academic_years` | N:1 optionnelle | `RESTRICT` |
| `admission_requirements.formation_id → formations` | 1:1 obligatoire | `CASCADE` |
| `academic_programs.formation_id → formations` | 1:1 obligatoire | `CASCADE` |
| `tuition_fees.formation_id → formations` | N:1 obligatoire | `CASCADE` |
| `user_roles.user_id → users` | N:1 obligatoire | `CASCADE` |
| `user_roles.scope_etablissement_id → establishments` | N:1 optionnelle | `RESTRICT` |
| `candidate_profiles.user_id → users` | 1:1 obligatoire | `CASCADE` |
| `candidatures.candidate_user_id → users` | N:1 obligatoire | `RESTRICT` |
| `candidatures.formation_id → formations` | N:1 obligatoire | `RESTRICT` |
| `candidature_status_history.candidature_id → candidatures` | N:1 obligatoire | `CASCADE` |
| `sources.formation_id → formations` | N:1 optionnelle | `RESTRICT` |
| `documents.etablissement_id → establishments` | N:1 optionnelle | `RESTRICT` |
| `document_formations` (2 FK) | N:N | `CASCADE` |
| `sync_history` (2 FK) | N:1 optionnelle | `RESTRICT` |
| `document_versions.document_id → documents` | N:1 obligatoire | `CASCADE` |

Aucune suppression en cascade n'est déclenchée par les scripts d'import : ils utilisent uniquement `INSERT ... ON CONFLICT`.

---

## 5. Domaines de valeurs communs

| Domaine | Valeurs autorisées |
|---|---|
| `verification_status` | `collected_unverified`, `verified`, `derived_not_official_fact`, `needs_review` |
| `value_origin` | `official`, `official_raw_document`, `derived_from_official_text_fixed_rules`, `derived_not_official_fact`, `user_provided` |
| `candidature status` | `draft`, `submitted`, `under_review`, `interview_scheduled`, `accepted`, `rejected`, `withdrawn` |

Ces domaines sont vérifiés par des contraintes `CHECK` dans les migrations. Toute valeur absente du CSV reste `NULL` ; le défaut `collected_unverified` n'est appliqué que lorsque la colonne n'est pas fournie, ce qui ne se produit pas pour les 7 CSV de SA-18.
