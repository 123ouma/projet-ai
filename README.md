# SmartCampus AI

Plateforme agentique d'orientation universitaire (IIT / ISB).

## Stack
- Frontend : Next.js
- Backend : à confirmer (SA-4 / SA-7)
- Base de données : PostgreSQL (SA-16)

## Prérequis
- Git
- Python 3.11+
- Node.js 22+
- Docker Desktop

## Installation
git clone https://github.com/123ouma/projet-ai.git
cd projet-ai
cp .env.example .env      (Windows : copy .env.example .env)

## Structure
- backend/  : API (SA-7)
- frontend/ : interface Next.js (SA-8)
- docs/     : architecture et documentation

## Règles Git
- main : version stable
- develop : intégration
- Une branche par ticket : feature/SA-xx-description
- Commits : "SA-xx: message"
- Ne jamais pousser le fichier .env