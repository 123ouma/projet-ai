# SmartCampus AI — Backend

Backend FastAPI + PostgreSQL du projet SmartCampus AI (orientation et préinscription NAU).
Structure conforme au document d'architecture SA-4 (§8).

## Tickets couverts dans cette contribution (Marwen)

| Ticket | Contenu | Fichiers principaux |
|---|---|---|
| SA-7  | Initialisation du backend : app FastAPI, config `.env`, CORS, `/health`, gestion des conflits (409), Dockerfile | `app/main.py`, `app/core/` |
| SA-16 | PostgreSQL : connexion SQLAlchemy, exécuteur de migrations SQL, docker-compose avec healthcheck | `app/core/database.py`, `app/db/migrate.py`, `database/migrations/001_init.sql`, `docker-compose.yml` |
| SA-20 | API des formations et des programmes (liste filtrée et paginée, détail, création, modification, archivage, programme par année/semestre) | `app/api/v1/formations.py` |
| SA-21 | API des tarifs et des conditions d'admission, consultation par budget, comparaison de 2 à 4 formations | `app/api/v1/admissions.py` |
| SA-26 | Mémoire temporaire des conversations : expiration après inactivité, fenêtre de contexte bornée pour le LLM, purge | `app/services/memory/`, `app/api/v1/conversations.py` |

## Démarrage

### Avec Docker (recommandé)
```bash
cd backend
cp .env.example .env          # puis changer POSTGRES_PASSWORD et ADMIN_API_TOKEN
docker compose up --build
docker compose exec backend python -m app.db.migrate --seed   # données de démo (facultatif)
```
Documentation interactive : http://localhost:8000/docs

### Sans Docker
```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows : .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env           # adapter DATABASE_URL
python -m app.db.migrate --seed
uvicorn app.main:app --reload
```

### Tests
```bash
cd backend
pytest                                  # tests unitaires (sans base)
TEST_DATABASE_URL=... pytest            # + tests d'intégration API sur une base de test
```

## Endpoints (préfixe `/api/v1`)

Consultation publique ; les routes d'écriture exigent l'en-tête `X-Admin-Token`
(**provisoire**, remplacé par le rôle « responsable NAU » de SA-28).

| Méthode | Route | Ticket |
|---|---|---|
| GET | `/etablissements` | SA-20 |
| GET | `/formations?etablissement=&niveau=&domaine=&q=&limit=&offset=` | SA-20 |
| GET | `/formations/{id}` (avec programme) | SA-20 |
| POST / PATCH / DELETE* | `/formations`, `/formations/{id}` (*archivage) | SA-20 |
| GET / PUT | `/formations/{id}/programme` | SA-20 |
| GET | `/tarifs?annee=&etablissement=&niveau=&budget_max=` | SA-21 |
| GET | `/formations/{id}/tarifs?annee=` | SA-21 |
| PUT / DELETE | `/formations/{id}/tarifs/{2026-2027}` | SA-21 |
| GET / PUT | `/formations/{id}/conditions` | SA-21 |
| GET | `/formations/compare?ids=1,3&annee=` | SA-21 |
| POST | `/conversations/{session_id}/messages` | SA-26 |
| GET | `/conversations/{session_id}/messages` (historique) | SA-26 |
| GET | `/conversations/{session_id}/context` (fenêtre pour le LLM) | SA-26 |
| DELETE | `/conversations/{session_id}` | SA-26 |
| POST | `/visitor-sessions` | SA-25 |
| GET / DELETE | `/visitor-sessions/{session_id}` | SA-25 |

Les routes SA-25 créent un UUID côté serveur et placent le secret d'accès dans un cookie
`HttpOnly`, `SameSite=Lax` (et `Secure` en production). Seul son hash SHA-256 est stocké.
Toutes les routes SA-26 exigent ce cookie et vérifient que le `session_id` lui appartient.
La durée d'inactivité se configure avec `VISITOR_SESSION_TTL_MINUTES` (60 par défaut).
Terminer une session efface aussi sa mémoire SA-26. Le worker
`python -m app.workers.purge_memory` purge périodiquement les sessions terminées ou expirées.

## Migrations

Fichiers `database/migrations/NNN_nom.sql`, appliqués dans l'ordre et une seule fois
(table `schema_migrations`). Pour modifier le schéma : **ajouter** un nouveau fichier
(`004_...sql`), ne jamais modifier une migration déjà appliquée.

```bash
python -m app.db.migrate --status
```

## Points à coordonner avec l'équipe

- **Islem (SA-12 / SA-17)** : `002_catalogue.sql` crée les tables du catalogue pour débloquer
  SA-20/21. À fusionner avec votre modèle : une seule version des tables doit rester.
- **Islem (SA-18)** : `database/seeds/001_catalogue_demo.sql` contient des données **fictives** ;
  à remplacer par les données collectées.
- **Fares (SA-25 / SA-28 / SA-29)** : `session_id` de la mémoire = UUID de la session visiteur ;
  ajouter la clé étrangère et le contrôle de propriété. Remplacer `require_responsable`
  (`core/security.py`) par la vérification du rôle.
- **Souhaila (SA-36 / SA-37)** : utiliser `memory.context_for_llm(session_id)` pour l'historique
  envoyé au LLM (voir `services/memory/__init__.py`).
- **Worker** : lancer `python -m app.workers.purge_memory` périodiquement.
