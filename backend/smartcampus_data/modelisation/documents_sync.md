# SA-14 — Modélisation des documents, sources et synchronisation

Version : 1.0 — complément de [`MLD.md`](MLD.md) section 3.
Périmètre : `sources`, `documents`, `document_formations`, `sync_history`, `document_versions`.

---

## 1. Objectif

Conserver la **traçabilité complète** de la collecte SA-18 sans altérer les fichiers existants : chaque fait du catalogue est associé à son URL officielle, chaque document téléchargé à son chemin local et à son empreinte SHA-256, et chaque évolution de contenu à une version horodatée. Le modèle prépare également l'avenir sans rien implémenter de plus : aucun embedding, aucun index vectoriel, aucun chatbot.

---

## 2. Correspondance avec les CSV SA-18

| Table PostgreSQL | CSV source | Observations réelles |
|---|---|---|
| `sources` | `sources.csv` (329 lignes) | `html` 315, `pdf` 14 ; `http_status = 200` pour 329/329 ; 3 origines de valeur observées. |
| `documents` | `documents.csv` (83 lignes) | `html` 73, `pdf` 10 ; 83/83 ont un `sha256` valide et un `raw_path` ; `parse_status = ok` pour 83/83. |
| `document_formations` | `documents.formation_id` | 22 documents portent un `formation_id` (22 formations distinctes) ; les 61 autres restent rattachés à l'établissement uniquement (aucune association inventée). |
| `document_versions` | `documents.sha256`, `raw_path`, `collection_date` | Une version `n°1` par document est dérivée des données collectées ; `is_current = true`. |
| `sync_history` | aucun CSV | Aucun événement de synchronisation réel n'existe dans SA-18 → la table reste **vide** après import. |

Le champ `error` de `documents.csv` est vide pour 83 documents : il est importé en `last_error_message = NULL`, pas en chaîne vide.

---

## 3. Champs demandés et où ils sont stockés

| Exigence | Table.colonne | Remarque |
|---|---|---|
| URL source | `sources.source_url`, `documents.url`, `documents.parent_url` | URL exacte publiée, jamais réécrite. |
| Type de source | `sources.source_type` | `html`, `pdf` (domaine étendu `api`, `other`). |
| Établissement | `sources.etablissement_id`, `documents.etablissement_id` | FK vers `establishments`. |
| Chemin du document local | `documents.raw_path`, `document_versions.raw_path` | Chemin relatif tel que produit par SA-18 (`data\raw\...`). |
| Date de collecte | `sources.collection_date`, `documents.collection_date`, `document_versions.collected_at` | `TIMESTAMPTZ`, format ISO 8601 `AAAA-MM-JJH:MM:SSZ`. |
| Dernière vérification | `sources.last_verified_at`, `documents.last_verified_at` | `NULL` si SA-18 ne l'a pas renseigné. |
| Hash SHA-256 | `documents.sha256`, `document_versions.sha256` | `CHECK` sur 64 caractères hexadécimaux minuscules. |
| Statut de synchronisation | `documents.sync_status`, `sync_history.sync_status` | `collected` par défaut pour un document réellement collecté. |
| Message d'erreur | `documents.last_error_message`, `sync_history.error_message` | `NULL` si aucune erreur ; obligatoire si `sync_status = failed`. |
| Année universitaire | `documents.academic_year_label`, FK vers `academic_years` | `NULL` : information absente de `documents.csv`. |
| Statut de vérification | `sources.verification_status`, `documents.verification_status` | Domaine contrôlé ; `NULL` pour `documents` si non collecté. |
| Documents liés aux formations | `document_formations` | Table de jonction N:N. |

---

## 4. Relations et cardinalités

| Relation | Cardinalité | Commentaire |
|---|---|---|
| `establishments` → `sources` | 1:0..N | Une source est publiée par un établissement. |
| `formations` → `sources` | 1:0..N | Une source peut documenter une formation. |
| `sources` → `documents` | 0..1:0..N | Une source pointe au plus un document local. |
| `establishments` → `documents` | 1:0..N | Un document est conservé dans le dossier d'un établissement. |
| `academic_years` → `documents` | 1:0..N optionnelle | L'année peut être inconnue. |
| `documents` ↔ `formations` | N:N via `document_formations` | Une brochure peut couvrir plusieurs formations. |
| `documents` → `document_versions` | 1:1..N | Au moins une version ; une seule courante (index unique partiel). |
| `sources` → `sync_history` | 1:0..N optionnelle | Un événement porte sur une source. |
| `documents` → `sync_history` | 1:0..N optionnelle | Un événement porte sur un document. |

Contrainte d'intégrité : `CHECK (source_id IS NOT NULL OR document_id IS NOT NULL)` sur `sync_history` — un événement de synchronisation sans cible n'a pas de sens.

---

## 5. empreinte, versions et synchronisation

### 5.1 Empreinte SHA-256

`documents.sha256` est obligatoire et validé par `CHECK (sha256 ~ '^[0-9a-f]{64}$')`. Les 83 valeurs importées proviennent directement du calcul effectué pendant SA-18 ; aucune valeur n'est recalculée ni remplacée pendant l'import.

### 5.2 Versions

À l'import, chaque document reçoit une `document_versions` unique, numérotée `1`, avec le `sha256`, le `raw_path`, la `taille` et la date de collecte du CSV. C'est une dérivation directe, pas une hypothèse : le document n'existe dans SA-18 que dans cet état.

Lors des synchronisations futures, une nouvelle version sera insérée uniquement si le SHA-256 diffère de la version courante ; l'ancienne version passera `is_current = false` et la nouvelle `is_current = true`. L'index unique partiel `UNIQUE (document_id) WHERE is_current` empêche deux versions courantes. La détection et la bascule ne sont pas implémentées dans ce ticket.

### 5.3 Historique de synchronisation

`sync_history` enregistre : type (`full`, `incremental`, `verification`, `retry`), statut (`started`, `success`, `failed`, `partial`), début/fin, statut HTTP, message d'erreur, compteurs (`items_processed`, `items_created`, `items_updated`, `items_failed`) et déclencheur.

Règles :
- `finished_at >= started_at` ;
- un statut `failed` exige `error_message IS NOT NULL` ;
- les compteurs ne peuvent pas être négatifs.

Aucune ligne n'est créée lors de l'import CSV : inventer un événement de synchronisation serait faux. Le script d'import est lui-même traçable via ses logs et son rapport JSON, hors base de données.

---

## 6. Compatibilité RAG (sans implémentation)

Le modèle ne contient **aucune** table d'embeddings et **aucun** vecteur. Il fournit uniquement les informations qu'un futur pipeline RAG utilisera :

1. `documents.raw_path` — le fichier source à chunker ;
2. `documents.sha256` et `document_versions` — l'identité exacte du contenu à indexer, et la détection de mise à jour ;
3. `documents.text_chars`, `documents.language`, `documents.document_type` — des métadonnées de filtrage ;
4. `document_formations` — le rattachement au catalogue pour enrichir les chunks ;
5. `sources.value_origin`, `sources.evidence_excerpt` — la preuve officielle d'un fait ;
6. `documents.rag_index_status` — état futur (`not_indexed` / `eligible` / `indexed` / `excluded`), avec défaut `not_indexed`.

Le présent code n'écrit jamais `indexed` : ce ticket ne construit ni pipeline d'embedding ni chatbot.

---

## 7. Import relançable

- `sources.source_id`, `documents.document_id` et `document_versions.version_id` sont les clés stables.
- L'import utilise `INSERT ... ON CONFLICT (PK) DO UPDATE` pour rafraîchir les colonnes collectées, puis `INSERT ... ON CONFLICT DO NOTHING` pour les associations `document_formations` et la version 1.
- La transaction par fichier est atomique : une erreur annule le fichier en cours sans laisser de données partielles.
- Les relations sont importées dans l'ordre : `establishments` → `degree_levels`/`academic_years` → `formations` → `admission_requirements`/`academic_programs`/`tuition_fees` → `sources` → `documents` → `document_formations` → `document_versions`.

Le détail des types et contraintes est dans [`MLD.md`](MLD.md) §3 ; le diagramme dans [`diagramme_erd.mmd`](diagramme_erd.mmd).
