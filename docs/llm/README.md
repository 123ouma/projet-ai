# Données de référence QA pour les LLM

Ce dossier contient des questions et réponses de référence construites pour SmartCampus IIT / ISB à partir des CSV traités par SA-18. Les informations utilisées ont été confirmées par Islem, responsable de la collecte. Cette confirmation n’est pas une vérification officielle indépendante.

## Fichiers

- [`qa_reference.jsonl`](./qa_reference.jsonl) — 40 exemples, un objet JSON valide par ligne.
- [`qa_reference.md`](./qa_reference.md) — description, limites et inventaire des sources utilisées.
- `scripts/validate_qa_dataset.py` — contrôle JSONL, champs requis, doublons, statuts et références aux CSV.

## Schéma JSONL

Chaque ligne comprend :

- `id` : identifiant stable `QA###`.
- `category` : catégorie fonctionnelle.
- `question` : question principale en français.
- `answer` : réponse limitée aux données réellement disponibles, avec avertissements si nécessaire.
- `source` : chemins de CSV, identifiant(s) source et URL(s) pertinentes.
- `verification_status` : statut de vérification des faits.
- `keywords` : mots-clés.
- `alternate_questions` : formulations alternatives avec leur langue (`fr`, `tn` ou `arabizi`).

## Statut de vérification

Les 40 réponses portent `verification_status: teammate_confirmed` et identifient Islem comme source de confirmation. Elles conservent aussi `source_verification_status: collected_unverified` : aucune ligne CSV n’a été requalifiée et aucune source officielle n’a été vérifiée séparément. La présence d’une URL institutionnelle ne constitue pas une preuve de vérification indépendante.

Les montants IIT restent accompagnés de leur période CSV (« 9 mois »), sans supposer si le montant est mensuel ou total. Les fichiers ne renseignent pas les documents d’admission, les matières ISB ni les montants de scolarité ISB; le dataset le précise au lieu de compléter ces informations par déduction.

Les fichiers CSV traités ont servi de base; les données sources n’ont pas été modifiées.

## Revalidation

Depuis la racine du repository, exécuter le validateur complet :

```powershell
python scripts\validate_qa_dataset.py
```

Le validateur vérifie le JSONL, l’unicité des identifiants et questions, les champs obligatoires, les variantes françaises/tunisiennes/Arabizi, les statuts de confirmation et les références aux lignes et URL des CSV. Le référentiel précise les questions sans réponse dans les données. En cas d’information manquante, le LLM doit le dire et renvoyer vers l’établissement au lieu d’inventer une réponse.
