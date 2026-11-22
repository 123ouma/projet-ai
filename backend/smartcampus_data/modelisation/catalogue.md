# SA-12 — Modélisation du catalogue académique

## 1. Source des données

Le modèle est construit à partir des 7 CSV produits par SA-18 (`data/processed/`) :

| CSV | Rôle dans le modèle |
|---|---|
| `etablissements.csv` | `establishments` |
| `formations.csv` | `formations`, alimente `degree_levels` |
| `admissions.csv` | `admission_requirements` |
| `programmes.csv` | `academic_programs` |
| `tarifs.csv` | `tuition_fees` |
| `sources.csv` | `sources` (voir SA-14) |
| `documents.csv` | `documents` (voir SA-14) |

Constat relevé sur les données réellement collectées : 4 établissements, 22 formations, 22 admissions, 22 programmes, 42 lignes de tarifs, 7 libellés distincts de `degree_type`, et 3 libellés non vides d'`academic_year` (`2026/2027`, `2025-2026`, `2026`) ; la cellule vide n'est pas une valeur et reste `NULL`.

## 2. Décisions de modélisation

1. **Identifiants stables** : `formation_id` et `etablissement_id` sont conservés tels quels (clés primaires `TEXT`). Les clés Techniques supplémentaires sont des `SERIAL`.
2. **Niveaux de diplôme** : `degree_type` est un libellé répété → table de référence `degree_levels` (code + libellé officiel). Aucune valeur n'est inventée : seuls les 7 libellés observés sont insérés.
3. **Années universitaires** : les trois formats observés sont conservés dans `academic_years.label` (libellé exact publié) avec `start_year` et `end_year` dérivés mécaniquement. `2026` donne `start_year = 2026`, `end_year = NULL` (aucune fin n'est supposée).
4. **Normalisation 3NF** : les tables filles ne duplication pas `etablissement_id` ; l'établissement est obtenu par `formations → establishments`. La colonne présente dans les CSV sert uniquement au contrôle de cohérence pendant l'import.
5. **Valeurs manquantes** : toute cellule vide du CSV devient `NULL` en base. Aucune valeur par défaut de type « inconnu » n'est créée pour un fait non publié.
6. **Tarifs** : une ligne par `(formation, type, portée, année)` ; `tuition_fee` et `registration_fee` ne sont jamais fusionnés, et `fee_currency` est obligatoire dès qu'un montant est publié.
7. **Statut de vérification** : `collected_unverified` par défaut, conformément à SA-18. La présence d'un nom sur une page officielle ne constitue pas une vérification.

## 3. Entités et cardinalités

| Relation | Cardinalité | Justification |
|---|---|---|
| `establishments` → `formations` | 1:N | Un établissement propose plusieurs formations ; une formation appartient à un seul établissement. |
| `degree_levels` → `formations` | 1:N (optionnel) | Plusieurs formations partagent un niveau ; le niveau peut être inconnu. |
| `academic_years` → `formations` | 1:N (optionnel) | Année déclarée sur la page de formation, si publiée. |
| `formations` → `admission_requirements` | 1:1 | Une fiche d'admission par formation dans le catalogue collecté. |
| `academic_years` → `admission_requirements` | 1:N (optionnel) | Une année peut concerner plusieurs formations. |
| `formations` → `academic_programs` | 1:1 | Un programme académique par formation collectée. |
| `formations` → `tuition_fees` | 1:N | Plusieurs lignes (national/international, scolarité/inscription, informations pratiques). |
| `academic_years` → `tuition_fees` | 1:N (optionnel) | Les tarifs sont datés de l'année universitaire publiée. |

## 4. Vérification de cohérence effectuée

- Aucun `formation_id` dupliqué, aucun doublon `(etablissement_id, formation_name)`.
- Aucune formation orpheline : tous les `etablissement_id` existent dans `etablissements.csv`.
- Toutes les lignes `admissions`, `programmes` et `tarifs` référencent un `formation_id` présent.
- Aucun tarif publié sans devise.
- Les 22 formations ont toutes une description et un `degree_type` renseignés à l'issue de SA-18.

Ces contrôles sont rejoués après import par `scripts/verify_database.py`.

## 5. Tables

La définition complète des colonnes, types, clés et contraintes est dans [`MLD.md`](MLD.md) ; le diagramme est dans [`diagramme_erd.mmd`](diagramme_erd.mmd).
