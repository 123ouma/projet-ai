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
| SA-36 | Connexion au service LLM d'Oumayma (Qwen3.5-9B, SA-34) : client HTTP, clé `X-API-Key`, gestion des erreurs 502/503, routes `/assistant` (Souhaila) | `app/services/llm/`, `app/api/v1/assistant.py` |
| SA-37 | Dialogue multi-tours : l'historique de la session (mémoire SA-26) est envoyé au LLM (champ `history`), profil cumulé (budget, en ligne) — route `/assistant/chat/{session_id}` (Souhaila) | `app/services/llm/conversation.py`, `app/api/v1/assistant.py` |
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
| POST | `/assistant/understand` (intent, budget_dt, online) | SA-36 |
| GET | `/assistant/health` (service LLM joignable ? mode mock ?) | SA-36 |
| POST | `/assistant/chat/{session_id}` (avec historique + profil cumulé) | SA-37 |

## Service LLM (SA-36)

Le backend appelle le service LLM séparé d'Oumayma (`POST /v1/understand`, en-tête `X-API-Key`).
Le LLM **comprend** la demande (intent, budget_dt, online) ; il ne donne pas encore de réponse
factuelle sur les formations (ce sera le RAG).

Variables dans `.env` :
```
LLM_API_URL=http://127.0.0.1:8100            # avec Docker : http://host.docker.internal:8100
LLM_API_KEY=<même clé que le service LLM>
LLM_TIMEOUT_SECONDS=120
```

Tester sans GPU : lancer le service LLM avec `LLM_MOCK_MODE=true` (réponses `"mock": true`,
jamais de vraies prédictions), puis :
```bash
curl -X POST http://localhost:8000/api/v1/assistant/understand \
  -H "Content-Type: application/json" \
  -d '{"message":"Faskhouli demande préinscription mte3i.","language":"arabizi"}'
```
Langues : `fr`, `en`, `arabizi`, `tn` (pas de détection automatique).
Erreurs : `503` si le LLM est injoignable ou trop lent, `502` si clé refusée ou réponse invalide.
Remplacer Qwen par une version fine-tunée (QLoRA) se fait côté service LLM, sans changer ces routes.

## Historique des conversations (SA-37)

`POST /api/v1/assistant/chat/{session_id}` (session_id = UUID de la session visiteur) :
1. récupère les messages précédents avec `memory.context_for_llm(session_id)` (SA-26, 20 messages / 8000 caractères max) ;
2. les envoie au LLM dans le champ optionnel `history` : `[{"role": "user"|"assistant", "content": "..."}]` ;
3. enregistre le message de l'étudiant et la réponse du LLM (JSON intent/budget_dt/online) dans la mémoire ;
4. renvoie la compréhension du message + un **profil cumulé** : un budget donné au 1er message est conservé
   si le message suivant ne le répète pas.

Si le LLM échoue (502/503), rien n'est enregistré. `/assistant/understand` (SA-36, sans historique) reste inchangé :
sans historique, la requête envoyée au service LLM est identique à SA-36.
Le service LLM doit lire `history` pour en tenir compte (extension du service d'Oumayma) ; un service
qui ne le connaît pas l'ignore sans erreur.
Nouvelle conversation : `DELETE /api/v1/conversations/{session_id}`.

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
