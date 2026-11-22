# SmartCampus_Data — SA-18

Collecte et préparation des **données officielles** des formations de quatre établissements tunisiens :

| ID | Établissement | Site officiel |
|---|---|---|
| IIT | Institut International de Technologie | https://iit.tn |
| ISB | International School of Business | https://isb.tn |
| ISA | International School of Architecture | https://isa.tn |
| 2I2S | École Internationale des Sciences de Santé | https://2i2s.tn |

Ce projet ne contient **ni frontend, ni backend web, ni chatbot**. Il produit des fichiers CSV, un classeur Excel, des broches/HTML bruts conservés, un export JSONL pour un futur système RAG et un rapport de validation. **Aucun embedding n'est généré ici.**

---

## 1. Installation

```bash
cd SmartCampus_Data
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

---

## 2. Commandes

```bash
# Vérifier les URLs et afficher les pages prévues, sans collecte
python main.py --establishment IIT --dry-run
python main.py --all --dry-run

# Collecte réelle, établissement par établissement
python main.py --establishment IIT
python main.py --establishment ISB
python main.py --establishment ISA
python main.py --establishment 2I2S

# Collecte des quatre établissements
python main.py --all

# Régénérer les fichiers de sortie depuis les caches de collecte
python main.py --export

# Validation seule
python main.py --validate

# Contrôle rapide des CSV
python scripts/check_data.py --strict

# Tests unitaires
python -m pytest -q
```

Chaque collecte affiche : l'établissement en cours, le nombre de pages analysées, le nombre de formations identifiées, le nombre de documents récupérés, les champs manquants, les erreurs HTTP/parsing et les chemins des fichiers générés.

---

## 3. Arborescence

```text
SmartCampus_Data/
├── config/
│   ├── settings.py
│   └── sources.yaml
├── data/
│   ├── raw/<IIT|ISB|ISA|2I2S>/{html,pdf,meta}/
│   ├── processed/
│   │   ├── .scrape_cache/
│   │   ├── etablissements.csv
│   │   ├── formations.csv
│   │   ├── admissions.csv
│   │   ├── programmes.csv
│   │   ├── tarifs.csv
│   │   ├── sources.csv
│   │   └── documents.csv
│   └── exports/
│       ├── SmartCampus_Data.xlsx
│       ├── rag_documents.jsonl
│       ├── validation_report.json
│       └── validation_report.md
├── scrapers/
├── processors/
├── scripts/
├── tests/
├── main.py
├── requirements.txt
├── .gitignore
└── README.md
```

---

## 4. Règles de collecte appliquées

- `robots.txt` est consulté avant chaque ressource ; une URL refusée n'est pas téléchargée.
- Seules les pages publiques et les brochures PDF **du domaine officiel configuré** sont demandées.
- Les catalogues et pages de détail sont découverts depuis `config/sources.yaml`, puis par exploration limitée des liens internes (`max_depth`, `max_pages`) et des sitemaps officiels. Le site entier n'est pas parcouru.
- User-Agent identifiable, timeout, retries limités, backoff et temporisation entre requêtes.
- Aucun CAPTCHA, contournement anti-bot, formulaire privé ou espace authentifié n'est utilisé.
- Les pages et PDF bruts sont conservés dans `data/raw/` avec un fichier `.json` de métadonnées (URL, statut HTTP, SHA-256, date, chemin local).
- Une information non publiée reste **vide/`null`**. Aucune valeur n'est inventée pour combler un champ manquant.
- Les faits officiels et les `interest_tags` dérivés sont séparés : ces derniers sont produits par une table de mots-clés déterministe et portent `interest_tags_origin = derived_from_official_text_fixed_rules`.
- Chaque valeur extraite est tracée dans `sources.csv` avec son URL, son attribut, un extrait de preuve et son origine (`official`, `official_raw_document` ou dérivée).
- `verification_status = collected_unverified` : la présence d'un nom sur une page officielle ne suffit pas à déclarer une formation vérifiée.

### Limites connues

- Certains sites publient certaines données uniquement dans des brochures téléchargeables après formulaire ou sur demande ; ces données restent manquantes si aucun PDF public direct n'est disponible.
- Les montants annoncés comme indicatifs ou « sur demande » ne sont pas convertis en montants numériques.
- Les sites peuvent changer de structure : les extracteurs sont basés sur des motifs de texte et des titres officiels, pas sur un modèle génératif.

---

## 5. Schémas produits

- `etablissements.csv` : identifiant, nom, site, contact et provenance.
- `formations.csv` : identifiant stable `formation_id`, descripteurs généraux, orientation et métadonnées RAG.
- `admissions.csv` : conditions d'admission, liées à `formation_id`.
- `programmes.csv` : modules, semestres, stages, projets, compétences.
- `tarifs.csv` : **une ligne par type/portée de frais** (`fee_type`, `fee_scope`, `fee_currency`, `fee_period`, `fee_status`). Les frais de scolarité, droits d'inscription et frais annuels/totaux ne sont pas confondus.
- `sources.csv` : traçabilité par attribut, avec preuve et origine de la valeur.
- `documents.csv` : chaque HTML/PDF récupéré, avec SHA-256, statut HTTP et chemin brut.
- `rag_documents.jsonl` : un objet JSON par chunk de texte officiel, avec URL, titre, établissement, formation si identifiable, langue et date de collecte. Aucun vecteur ni embedding.

---

## 6. Filet de sécurité qualité

`python main.py --validate` et `scripts/check_data.py --strict` contrôlent :

- présence des noms et identifiants de formations ;
- doublons d'identifiants et de noms ;
- cohérence des clés étrangères `formation_id` / `etablissement_id` ;
- validité syntaxique des URLs ;
- formats de dates et d'années ;
- numericité des tarifs **uniquement lorsqu'une valeur est publiée** ;
- rapport des champs manquants et des formations incomplètes ;
- avertissement si un statut `verified` n'est pas soutenu par au moins deux sources.

Le rapport est écrit dans `data/exports/validation_report.json` et `validation_report.md`, et résumé dans l'onglet `validation_report` du classeur Excel.

---

## 7. Résultat de la collecte réelle (dernière exécution)

Collecte effectuée sur les quatre sites officiels publics, sans valeur inventée :

| Établissement | Pages HTML | Documents | PDF | Formations |
|---|---:|---:|---:|---:|
| IIT | 30 | 31 | 1 | 11 |
| ISB | 27 | 36 | 9 | 9 |
| ISA | 11 | 11 | 0 | 1 |
| 2I2S | 5 | 5 | 0 | 1 |
| **Total** | **73** | **83** | **10** | **22** |

Fichiers produits : 7 CSV, classeur Excel (8 onglets), 189 chunks RAG, 83 fichiers bruts avec métadonnées.

**Validation : PASS — 0 erreur, 21 avertissements.** Les avertissements signalent des formations incomplètes : certains descripteurs ne sont pas publiés par les sites (durée, modules, débouchés, tarifs). Ces cellules restent volontairement vides.

Problèmes rencontrés et tracés :

- `https://isa.tn/architecture/` répond **HTTP 404** ; le lien est signalé dans le rapport et aucune donnée n'est déduite de cette URL.
- `isa.tn` rejette les User-Agent verbeux (403) : un User-Agent court et identifiable est utilisé.
- Les avertissements `fontTools` émis lors de l'extraction de certains PDF sont non bloquants ; le texte lisible a été extrait.
- Tous les enregistrements portent `verification_status = collected_unverified` : une vérification humaine reste nécessaire avant utilisation décisionnelle.

NB : les dates de collecte sont des horodatages ISO 8601 (`AAAA-MM-JJH:MM:SSZ`) ; le validateur les accepte. Les CSV sont encodés en UTF-8 avec BOM pour Excel, et le validateur les relit en `utf-8-sig`.


---

## 8. Modélisation relationnelle et base PostgreSQL (SA-12 à SA-17)

### Livrables ajoutés

- `modelisation/MCD.md`, `MLD.md`, `catalogue.md`, `users_candidatures.md`, `documents_sync.md`, `diagramme_erd.mmd`
- `database/migrations/001_catalogue.sql`, `002_users_candidatures.sql`, `003_documents_sync.sql`
- `database/seed/demo_data.sql`, `database/queries/verification.sql`
- `scripts/create_database.py`, `scripts/import_csv.py`, `scripts/verify_database.py`
- `tests/test_database.py`, `tests/test_import.py`, `tests/conftest.py`
- `.env.example`, `database/db.py`, dépendances `psycopg[binary]` et `python-dotenv`

**18 tables** couvrent le catalogue (7), les utilisateurs/candidatures (5), les documents/synchronisation (5), plus `academic_years` (référence commune). Les 8 rôles incluent les responsables IIT, ISB, ISA et 2I2S. Aucune donnée personnelle réelle ni aucun mot de passe en clair : seul `password_hash` existe, et le seed n'utilise que des comptes `.invalid`.

### Procédure reproductible

```powershell
copy .env.example .env
# renseigner DATABASE_URL, DATABASE_URL_ADMIN et DATABASE_URL_TEST dans .env
python scripts/create_database.py
python scripts/import_csv.py
python scripts/verify_database.py
python -m pytest -q
```

Le seed fictif est appliqué séparément via `database/seed/demo_data.sql`. Les migrations et l'import sont idempotents (`CREATE TABLE IF NOT EXISTS`, `INSERT ... ON CONFLICT`) : aucune table ni donnée existante n'est supprimée. La cellule vide d'un CSV reste `NULL` en base.

### Validation réellement exécutée

Validation effectuée sur un cluster PostgreSQL 17.10 **isolé et temporaire** (port 55432, répertoire sous `%TEMP%`), sans toucher à l'instance PostgreSQL de l'utilisateur :

| Opération | Résultat |
|---|---|
| Migrations 001 → 003 | 3/3 appliquées, puis réappliquées avec succès (idempotence) |
| Import CSV (2 passages) | 639 lignes traitées, volumes identiques après le 2e passage |
| Seed fictif (2 passages) | 8 rôles, 7 comptes, 1 candidature, 1 entrée d'historique, sans doublon |
| `scripts/verify_database.py` | **PASS — 36/36 contrôles** |
| `python -m pytest -q` | **37 tests réussis** |
| `python scripts/check_data.py --strict` | 0 erreur, 21 avertissements SA-18 connus |
| `python -m compileall` | OK |
| `psql -f database/queries/verification.sql` | OK, toutes les vérifications à 0 |

Volumes importés : 4 établissements, 7 niveaux de diplôme, 3 années universitaires non vides, 22 formations, 22 admissions, 22 programmes, 42 tarifs, 329 sources, 83 documents, 22 liaisons document-formation, 83 versions. Les 61 documents sans `formation_id` restent rattachés à leur établissement uniquement ; `sync_history` reste vide aucun événement de synchronisation réel n'existe dans SA-18. Aucun embedding ni document `indexed` n'a été créé.

Le cluster temporaire a été arrêté et son répertoire supprimé après validation. Pour utiliser votre propre instance PostgreSQL, copiez `.env.example` vers `.env` et renseignez-y vos identifiants : aucun secret n'est écrit dans le code.
#   p r e p a r e _ s m a r t c a m p u s _ g i t h u b  
 