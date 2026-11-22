# SmartCampus AI — Conception des API et règles d'accès (SA-5)

Références : docs/les_acteurs__et_processus_metiers.pdf (SA-3), docs/socle_technique_SA4.pdf (SA-4), modelisation/MLD.md (Islem, SA-12/13/14).
Backend : FastAPI. Établissements du NAU : IIT, ISB, ISA, 2i2s.

## 1. Conventions
- Toutes les URL commencent par `/api/`
- Format des données : JSON
- Authentification : mécanisme de session à confirmer avec SA-28 (Fares)
- Les noms des ressources suivent les tables d'Islem (`formations`, `candidatures`, `users`, `candidate_profiles`)
- Codes de réponse :
  - 200 OK / 201 Créé
  - 400 Données invalides (champ obligatoire manquant, consentement absent)
  - 401 Non connecté
  - 403 Accès interdit
  - 404 Introuvable
  - 409 Action impossible dans l'état actuel du dossier

## 2. Acteurs et rôles

| Rôle | Description |
|---|---|
| anonyme | Candidat non connecté : chat d'orientation et consultation des formations |
| candidat | Candidat connecté : préinscription, QCM d'anglais (ISB), réponse aux rendez-vous |
| responsable_nau | Met à jour les formations, consulte les candidatures par établissement, renseigne ses disponibilités et les décisions, valide l'inscription définitive |

Les agents (chatbot, planification, communication) sont des modules internes du backend.
La planification, les emails et les rappels sont exécutés par un worker Python à partir
des tâches enregistrées dans PostgreSQL. Ils n'exposent aucune route publique.

> À confirmer avec Islem : le modèle de données prévoit-il des rôles limités par établissement ?

## 3. Endpoints

### 3.1 Authentification
| Méthode | URL | Description | Accès |
|---|---|---|---|
| POST | /api/auth/register | Créer un compte candidat | anonyme |
| POST | /api/auth/login | Se connecter | tous |
| POST | /api/auth/logout | Se déconnecter | connecté |
| GET | /api/auth/me | Mon compte et mon rôle | connecté |

### 3.2 Formations (catalogue)
| Méthode | URL | Description | Accès |
|---|---|---|---|
| GET | /api/formations?etablissement=IIT | Liste des formations (filtre IIT / ISB / ISA / 2i2s) | tous |
| GET | /api/formations/{id} | Détail : programme, conditions, durée, tarifs si disponibles | tous |
| GET | /api/formations/comparer?ids=1,2,3 | Comparer plusieurs formations | tous |
| POST | /api/formations | Ajouter une formation | responsable_nau |
| PUT | /api/formations/{id} | Mettre à jour une formation | responsable_nau |
| DELETE | /api/formations/{id} | Supprimer une formation | responsable_nau |

Une information absente (tarif, condition) est renvoyée `null` : elle ne vaut ni 0 ni « sans condition ».

### 3.3 Chat d'orientation
| Méthode | URL | Description | Accès |
|---|---|---|---|
| POST | /api/chat/sessions | Démarrer une conversation | anonyme, candidat |
| POST | /api/chat/sessions/{id}/messages | Envoyer un message (texte ou audio) | propriétaire de la session |
| GET | /api/chat/sessions/{id}/messages | Historique de la conversation | propriétaire de la session |

À la connexion, la session et le profil collecté sont rattachés au compte du candidat.
La réponse du chatbot inclut les sources utilisées. Si une information n'est pas disponible
ou reste à vérifier, la réponse le signale.

### 3.4 Candidatures (préinscription)
| Méthode | URL | Description | Accès |
|---|---|---|---|
| GET | /api/candidatures/prerempli | Formulaire prérempli à partir de la conversation | candidat |
| POST | /api/candidatures | Soumettre la préinscription (champs obligatoires + consentement) | candidat |
| GET | /api/candidatures/me | Ma candidature et son état | candidat |
| GET | /api/candidatures?etablissement=ISB | Candidatures classées par établissement | responsable_nau |
| GET | /api/candidatures/{id} | Détail d'un dossier | responsable_nau |

Les valeurs proposées par le chatbot ne sont confirmées qu'après validation par le candidat.

### 3.5 QCM d'anglais (ISB uniquement)
| Méthode | URL | Description | Accès |
|---|---|---|---|
| GET | /api/qcm-anglais | Obtenir le QCM | candidat ISB |
| POST | /api/qcm-anglais/reponses | Envoyer les réponses | candidat ISB |
| GET | /api/candidatures/{id}/qcm | Résultat du QCM | responsable_nau |
| PUT | /api/candidatures/{id}/verification-isb | Valider le dossier ISB avant planification | responsable_nau |

### 3.6 Disponibilités et rendez-vous
| Méthode | URL | Description | Accès |
|---|---|---|---|
| POST | /api/disponibilites | Ajouter un créneau disponible | responsable_nau |
| GET | /api/disponibilites | Voir ses disponibilités | responsable_nau |
| DELETE | /api/disponibilites/{id} | Supprimer un créneau | responsable_nau |
| GET | /api/rendez-vous | Rendez-vous et leur état | responsable_nau |
| GET | /api/rendez-vous/me | Mon rendez-vous | candidat |
| POST | /api/rendez-vous/{id}/reponse | Répondre : `accepter` / `indisponible` / `renoncer` | candidat (le sien) |

Le candidat ouvre le lien reçu par email et répond depuis la plateforme après identification.

### 3.7 Décision et inscription
| Méthode | URL | Description | Accès |
|---|---|---|---|
| PUT | /api/candidatures/{id}/decision | Décision après entretien : `acceptee` / `refusee` | responsable_nau |
| POST | /api/candidatures/{id}/inscription-definitive | Valider l'inscription définitive | responsable_nau |

## 4. États

Candidature :
`soumise` → (ISB : `qcm_passe` → `verifiee_isb`) → `entretien_planifie` → `acceptee` / `refusee` → `inscrite`

Rendez-vous :
`propose` → `confirme` | `reprogramme` | `annule`

## 5. Règles d'accès et règles métier
1. L'orientation et la consultation des formations sont accessibles sans compte.
2. Une authentification est obligatoire pour la préinscription, le QCM et la réponse aux rendez-vous.
3. Soumission refusée (400) si un champ obligatoire manque ou si le consentement n'est pas donné.
4. Les candidatures sont classées par établissement.
5. Le QCM d'anglais est réservé aux candidatures ISB (403 sinon).
6. Un dossier ISB doit être vérifié par le responsable avant la planification (409 sinon).
7. Si le candidat est indisponible, l'agent de planification propose un nouveau créneau.
8. Sans réponse deux jours après l'envoi réussi de la proposition, un rappel est envoyé une seule fois. L'absence de réponse n'est pas une confirmation.
9. Un rendez-vous est confirmé uniquement après acceptation du candidat.
10. L'annulation d'un rendez-vous ne supprime pas la candidature.
11. La décision d'admission est humaine : seul `responsable_nau` peut la renseigner.
12. L'inscription définitive n'est possible que si la candidature est acceptée (409 sinon).
13. Un candidat n'accède qu'à ses propres données.
14. Le navigateur n'accède jamais directement à PostgreSQL, au stockage privé ni aux clés du LLM.

## 6. Matrice des droits

| Ressource | anonyme | candidat | responsable_nau |
|---|---|---|---|
| Formations (lecture, comparaison) | ✅ | ✅ | ✅ |
| Formations (modification) | ❌ | ❌ | ✅ |
| Chat d'orientation | ✅ | ✅ | ❌ |
| Candidatures | ❌ | la sienne | toutes (par établissement) |
| QCM d'anglais | ❌ | si ISB | résultats |
| Disponibilités | ❌ | ❌ | ✅ |
| Rendez-vous | ❌ | le sien (répondre) | consulter |
| Décision / inscription définitive | ❌ | ❌ | ✅ |
