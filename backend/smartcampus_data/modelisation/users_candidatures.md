# SA-13 — Modélisation des utilisateurs et candidatures

Version : 1.0 — complément de [`MLD.md`](MLD.md) section 2.
Périmètre : `users`, `roles`, `user_roles`, `candidate_profiles`, `candidatures`, `candidature_status_history`.

---

## 1. Périmètre et hypothèses

SA-18 ne collecte **aucune donnée personnelle** : aucun candidat réel n'est importé. Ce modèle fournit uniquement les structures permettant d'enregistrer ultérieurement des comptes et des dossiers. Les éventuels comptes de démonstration sont **fictifs** et utilisent le domaine réservé `.invalid` (voir `database/seed/demo_data.sql`).

Aucun mot de passe n'est stocké en clair : la seule colonne est `users.password_hash`, prévue pour un hash Argon2id/bcrypt/argon2 calculé côté application. Le seed utilise une chaîne explicite `demo-only-not-a-real-password-hash` qui n'est **pas** un secret réutilisable.

---

## 2. Rôles prévus

| `role_code` | `label` | `scope` | Responsabilité |
|---|---|---|---|
| `candidat` | Candidat | `global` | Déposer et suivre sa candidature. |
| `responsable_iit` | Responsable IIT | `establishment` | Suivi des candidatures IIT. |
| `responsable_isb` | Responsable ISB | `establishment` | Suivi des candidatures ISB. |
| `responsable_isa` | Responsable ISA | `establishment` | Suivi des candidatures ISA. |
| `responsable_2i2s` | Responsable 2I2S | `establishment` | Suivi des candidatures 2I2S. |
| `responsable_entretien` | Responsable entretien | `global` | Planification et suivi des entretiens. |
| `direction` | Direction | `global` | Vue agrégée et décisions finales. |
| `administrateur` | Administrateur | `global` | Administration technique de la plateforme. |

Les quatre rôles d'établissement couvrent bien **IIT, ISB, ISA et 2I2S**, comme demandé.

### Règle de portée (contrainte SQL)

`user_roles.scope_etablissement_id` ne peut être renseigné que pour un rôle de responsable d'établissement, et doit alors correspondre exactement :

| `role_code` | `scope_etablissement_id` obligatoire |
|---|---|
| `responsable_iit` | `IIT` |
| `responsable_isb` | `ISB` |
| `responsable_isa` | `ISA` |
| `responsable_2i2s` | `2I2S` |
| tous les autres | `NULL` |

Un responsable IIT ne peut donc pas être rattaché à ISB par erreur. Cette règle est appliquée par un `CHECK` et par une FK vers `establishments`, pas seulement par le code applicatif.

---

## 3. Relations et cardinalités

| Relation | Cardinalité | Règle |
|---|---|---|
| `users` → `user_roles` → `roles` | N:N | Un utilisateur a au moins un rôle ; un rôle peut être attribué à plusieurs utilisateurs. |
| `user_roles` → `establishments` | N:1 optionnelle | Portée d'un responsable d'établissement. |
| `users` → `candidate_profiles` | 1:0..1 | Un profil candidat appartient à un seul utilisateur ; un utilisateur a au plus un profil. |
| `users` → `candidatures` | 1:N | Un candidat peut déposer plusieurs dossiers. |
| `formations` → `candidatures` | 1:N | Plusieurs candidats peuvent viser une même formation du catalogue. |
| `academic_years` → `candidatures` | 1:N optionnelle | Une candidature vise une année universitaire connue, si renseignée. |
| `candidatures` → `candidature_status_history` | 1:0..N | Chaque transition est tracée. |
| `users` → `candidature_status_history` | 1:0..N | L'acteur du changement est identifiable. |

---

## 4. Contraintes d'unicité

| Table | Contrainte | Objectif |
|---|---|---|
| `users` | `UNIQUE (email)` + `CHECK (email = lower(email))` | Un seul compte par adresse, sans ambiguïté de casse. |
| `user_roles` | `UNIQUE NULLS NOT DISTINCT (user_id, role_code, scope_etablissement_id)` (PK technique `user_role_id`) | Interdit d'attribuer deux fois le même rôle avec la même portée, y compris `NULL`. |
| `candidate_profiles` | `UNIQUE (user_id)` | Un seul profil par candidat. |
| `candidatures` | `UNIQUE NULLS NOT DISTINCT (candidate_user_id, formation_id, academic_year_label)` | Un candidat ne postule qu'une fois pour une formation donnée et une année donnée, y compris quand l'année est `NULL`. |

`NULLS NOT DISTINCT` est disponible en PostgreSQL 15+ ; le projet vise PostgreSQL 17.

---

## 5. Timestamps

Toutes les tables SA-13 portent `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`. Les tables évolutives portent également `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`, maintenu par un trigger `BEFORE UPDATE` partagé. Les champs métier horodatés sont :

- `users.email_verified_at`, `users.last_login_at` ;
- `user_roles.assigned_at` ;
- `candidatures.consent_given_at`, `candidatures.submitted_at` ;
- `candidature_status_history.changed_at`.

Tous les types sont `TIMESTAMPTZ` :aucune heure locale ambiguë n'est stockée.

---

## 6. Règles d'intégrité et cycle de vie

### 6.1 Cycle de statut

```
draft → submitted → under_review → interview_scheduled → accepted
                                   ↘ rejected
draft → withdrawn
submitted → withdrawn (retrait possible avant décision)
```

Les statuts autorisés sont : `draft`, `submitted`, `under_review`, `interview_scheduled`, `accepted`, `rejected`, `withdrawn`. Un `CHECK` sur `candidatures.status` et sur les deux colonnes de statut de l'historique garantit le domaine.

### 6.2 Contraintes vérifiées par la base

1. **Consentement** : une candidature `draft` peut ne pas être consentie ; dès que `status <> 'draft'`, `consent_given = true` **et** `submitted_at IS NOT NULL`.
2. **Cohérence du consentement** : `consent_given = true` implique `consent_given_at IS NOT NULL`.
3. **Traçabilité** : un trigger `AFTER INSERT` crée la première entrée d'historique (`from_status = NULL`, `to_status = 'draft'` ou le statut initial). Un trigger `AFTER UPDATE OF status` crée une entrée pour chaque transition réelle (`WHEN OLD.status IS DISTINCT FROM NEW.status`).
4. **Pas de transition vide** : `CHECK (from_status IS NULL OR from_status <> to_status)`.
5. **Notes** : `baccalaureate_grade` et `minimum_grade` sont sur l'échelle `0..20` ; `baccalaureate_year` est borné `1950..2100`.
6. **Listes** : `interests` et `preferred_subjects` sont des `TEXT[]` avec au plus 50 éléments, afin d'éviter des tableaux démesurés. Aucune valeur n'est imposée.
7. **Références** : une candidature ne peut viser qu'une `formation_id` existante, et un responsable d'établissement qu'un établissement existant.

### 6.3 Suppressions

- `ON DELETE CASCADE` : `user_roles`, `candidate_profiles`, `candidature_status_history` (données dépendantes du parent).
- `ON DELETE RESTRICT` : `candidatures.candidate_user_id`, `candidatures.formation_id`, `user_roles.scope_etablissement_id` (un dossier ou un rattachement ne doit pas disparaître silencieusement).
- Les scripts d'import n'effectuent **aucune suppression**.

---

## 7. Comptes fictifs

Le seed insère :

| Email | Rôle | Usage |
|---|---|---|
| `candidat.demo@example.invalid` | `candidat` | Profil candidat de démonstration, sans donnée personnelle réelle. |
| `resp.iit.demo@example.invalid` | `responsable_iit` (IIT) | Vérification de la contrainte de portée. |
| `resp.isb.demo@example.invalid` | `responsable_isb` (ISB) | Idem. |
| `resp.isa.demo@example.invalid` | `responsable_isa` (ISA) | Idem. |
| `resp.2i2s.demo@example.invalid` | `responsable_2i2s` (2I2S) | Idem. |
| `direction.demo@example.invalid` | `direction` | Vérification du rôle global. |
| `admin.demo@example.invalid` | `administrateur` | Vérification du rôle global. |

Ces comptes sont `INSERT ... ON CONFLICT DO NOTHING` : le seed est relançable et n'écrase aucun compte existant. Le mot de passe n'est jamais fourni ; seule une valeur de marqueur non secret est stockée dans `password_hash`.

---

## 8. Vérification documentée

Les tests `tests/test_database.py` vérifient, sur une base PostgreSQL réelle :

- insertion d'un utilisateur fictif puis rejet d'un email en doublon ;
- rejet d'un `password_hash` vide ;
- attribution d'un `responsable_iit` sans portée `IIT` (échec attendu) ;
- création d'une candidature `draft` puis passage à `submitted` sans consentement (échec attendu) ;
- génération automatique d'au moins deux lignes d'historique après deux changements de statut ;
- rejet d'une candidature vers un `formation_id` inexistant (FK).

Le détail des types et contraintes est dans [`MLD.md`](MLD.md) §2 ; le diagramme dans [`diagramme_erd.mmd`](diagramme_erd.mmd).
