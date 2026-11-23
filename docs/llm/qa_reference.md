# Référentiel de questions/réponses SmartCampus IIT / ISB

Ce fichier décrit le jeu de données [qa_reference.jsonl](./qa_reference.jsonl), construit à partir des données préparées dans `backend/smartcampus_data/data/processed/` et confirmées par Islem, responsable de la collecte.

## Utilisation et précautions

- Le fichier contient **40 questions-réponses**.
- Chaque ligne JSONL donne un identifiant, une catégorie, une question, une réponse, des sources CSV traçables, les statuts de confirmation, des mots-clés et des formulations alternatives balisées en français (`fr`), tunisien (`tn`) et Arabizi (`arabizi`).
- `verification_status: teammate_confirmed` signifie qu’Islem a confirmé les informations collectées utilisées par la réponse. Il ne s’agit **pas** d’une vérification officielle indépendante : `source_verification_status` conserve `collected_unverified` et `verification_basis.independent_official_verification` vaut `false`.
- Les tarifs sont reproduits tels que présents dans le CSV. La période vaut « 9 mois », mais les données ne précisent pas si le montant est mensuel ou couvre toute la période. Ne pas calculer ni annoncer un total sans confirmation de l’établissement.
- Les informations ISB sont particulièrement incomplètes pour les modules, pièces de dossier et montants. Les réponses d’abstention signalent ces lacunes explicitement.
- Les années d’admission ISB recensées sont 2025-2026; elles ne confirment pas les conditions d’une rentrée ultérieure.

## Catégories couvertes

- Formations IIT et ISB
- Programmes, matières et compétences IIT
- Débouchés professionnels IIT
- Admission et préinscription
- Étapes de sélection et procédure d’admission IIT
- Cycle préparatoire et cycles ingénieur
- Tarifs IIT et absence de tarifs ISB dans les fichiers préparés
- Adresse des campus IIT et ISB
- Limites des données et informations non renseignées

## Sources de données exploitées

| Fichier | Utilisation |
|---|---|
| `backend/smartcampus_data/data/processed/formations.csv` | Noms, diplômes, descriptions, débouchés et durée des formations |
| `backend/smartcampus_data/data/processed/programmes.csv` | Modules et compétences de programme |
| `backend/smartcampus_data/data/processed/admissions.csv` | Niveaux, modalités, conditions et pièces de candidature |
| `backend/smartcampus_data/data/processed/tarifs.csv` | Montants collectés, devise, portée et période |
| `backend/smartcampus_data/data/processed/etablissements.csv` | Localisation des campus |

Chaque enregistrement JSONL donne le ou les identifiants de ligne des CSV concernés et les URL sources associées. Les CSV d’origine n’ont pas été modifiés. Le statut des sources reste `collected_unverified`; la confirmation d’Islem et la vérification officielle indépendante sont deux choses distinctes.

## Limites / questions non résolues par les données

- Quelles sont les matières détaillées des formations ISB ? Les champs `subjects` et `modules` associés sont vides.
- Quels documents faut-il fournir pour une préinscription IIT ou ISB ? Les 20 fiches d’admission IIT/ISB ne renseignent pas `required_documents`.
- Quels sont les tarifs actuels des formations ISB ? Les neuf lignes ISB de `tarifs.csv` sont `not_published` et ne contiennent aucun montant.
- Quelle est la périodicité exacte des montants IIT ? Les lignes indiquent une période de 9 mois sans expliquer si le montant est mensuel ou total.
- Quels sont les détails complets (durée, date limite, critères détaillés) de chaque admission ? Plusieurs champs correspondants sont vides.
- Les catalogues et conditions collectés sont-ils encore en vigueur ? La confirmation par le collecteur ne constitue pas une confirmation officielle indépendante ou une garantie de validité pour une nouvelle rentrée.

Pour ces sujets, l’assistant doit s’abstenir de déduire une réponse et inviter l’étudiant à confirmer auprès de l’établissement.
