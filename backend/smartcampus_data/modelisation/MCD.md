# MCD — Modèle Conceptuel de Données (SmartCampus AI)

Version : 1.0 — périmètre SA-12, SA-13, SA-14.
Sources : 7 CSV réellement produits par SA-18 dans `data/processed/`.
Convention de cardinalités : `(min, max)` lu dans le sens **entité de droite → entité de gauche**.

---

## 1. Vue d'ensemble

Le modèle couvre trois domaines :

| Domaine | Ticket | Entités |
|---|---|---|
| Catalogue académique | SA-12 | ÉTABLISSEMENT, NIVEAU_DIPLÔME, ANNÉE_UNIVERSITAIRE, FORMATION, EXIGENCE_ADMISSION, PROGRAMME_ACADÉMIQUE, TARIF |
| Utilisateurs & candidatures | SA-13 | UTILISATEUR, RÔLE, PROFIL_CANDIDAT, CANDIDATURE, HISTORIQUE_STATUT |
| Documents & synchronisation | SA-14 | SOURCE, DOCUMENT, VERSION_DOCUMENT, HISTORIQUE_SYNCHRO |

Les trois domaines sont reliés par deux ponts :
- `FORMATION ← CANDIDATURE` (un dossier vise une formation réelle du catalogue) ;
- `FORMATION ← DOCUMENT` via `LIER` (une brochure peut décrire plusieurs formations, et une formation peut être décrite par plusieurs documents).

---

## 2. Entités et propriétés conceptuelles

### 2.1 Domaine catalogue (SA-12)

**ÉTABLISSEMENT**
`id` (identifiant stable issu de SA-18 : `IIT`, `ISB`, `ISA`, `2I2S`), `nom`, `nom_court`, `pays`, `ville`, `site_web`, `url_source_nom_officiel`, `courriel_contact`, `téléphone_contact`, `campus`, `date_collecte`, `langue_document`, `statut_vérification`.

**NIVEAU_DIPLÔME**
`code` (clé technique dérivée du libellé), `libellé` (libellé exact publié). Les 7 libellés observés : `Licence`, `Cycle ingénieur`, `Mastère`, `Diplôme national d'architecte`, `Cycle préparatoire`, `Master of Science`, `Master`.

**ANNÉE_UNIVERSITAIRE**
`libellé` (clé naturelle : `2026/2027`, `2025-2026`, `2026`), `année_début`, `année_fin` (nullable). `2026` → `année_fin = NULL` : aucune fin n'est déduite.

**FORMATION**
`id`, `nom`, `domaine`, `spécialité`, `description`, `durée_années`, `langue`, `mode_étude`, `diplôme_décerné`, `débouchés`, `poursuite_études`, `domaine_carrière`, `passerelles`, `profil_recommandé`, `tags_intérêt`, `origine_tags`, `compétences_préalables`, `url_source`, `titre_source`, `type_source`, `date_collecte`, `dernière_vérification`, `statut_vérification`, `langue_document`.

**EXIGENCE_ADMISSION**
`id`, `baccalauréat_requis`, `note_minimale`, `niveau_requis`, `mode_admission`, `documents_requis`, `période_inscription`, `conditions_particulières`, `url_source`, `date_collecte`, `statut_vérification`.

**PROGRAMME_ACADÉMIQUE**
`id`, `matières`, `modules`, `nombre_semestres`, `stages`, `projets`, `spécialisations`, `compétences_acquises`, `url_source`, `date_collecte`, `statut_vérification`.

**TARIF**
`id`, `type_frais`, `portée` (`national` / `international`), `frais_scolarité`, `frais_inscription`, `autres_frais`, `devise`, `période`, `modalités_paiement`, `campus`, `courriel_contact`, `téléphone_contact`, `statut_frais`, `url_source`, `date_collecte`, `statut_vérification`.

### 2.2 Domaine utilisateurs (SA-13)

**UTILISATEUR**
`id`, `courriel`, `hash_mot_de_passe` (jamais de mot de passe en clair), `nom_complet`, `actif`, `courriel_vérifié_le`, `dernière_connexion_le`.

**RÔLE**
`code` (`candidat`, `responsable_iit`, `responsable_isb`, `responsable_isa`, `responsable_2i2s`, `responsable_entretien`, `direction`, `administrateur`), `libellé`, `portée` (globale / établissement).

**PROFIL_CANDIDAT**
`id`, `type_bac`, `année_bac`, `note_bac`, `résultats`, `intérêts`, `matières_préférées`, `objectifs_professionnels`, `contraintes`, `notes`.

**CANDIDATURE**
`id`, `statut`, `consentement_donné`, `date_consentement`, `date_soumission`, `motivation`, `dernière_modification_par`.

**HISTORIQUE_STATUT**
`id`, `statut_avant`, `statut_après`, `modifié_par`, `modifié_le`, `motif`.

### 2.3 Domaine documents (SA-14)

**SOURCE**
`id`, `url`, `titre`, `type` (`html` / `pdf`), `attribut`, `extrait_valeur`, `chemin_brut`, `origine_valeur`, `langue`, `date_collecte`, `dernière_vérification`, `statut_http`, `statut_vérification`, `extrait_preuve`.

**DOCUMENT**
`id`, `type`, `titre`, `url`, `url_parente`, `chemin_local`, `chemin_métadonnées`, `sha256`, `taille_octets`, `statut_http`, `type_contenu`, `langue`, `caractères_texte`, `nombre_pages`, `date_collecte`, `dernière_vérification`, `statut_sync`, `dernier_message_erreur`, `statut_vérification`, `année_universitaire`, `statut_indexation_rag`.

**VERSION_DOCUMENT**
`id`, `numéro`, `sha256`, `chemin_local`, `taille_octets`, `collectée_le`, `est_courante`.

**HISTORIQUE_SYNCHRO**
`id`, `type_sync`, `statut`, `début`, `fin`, `statut_http`, `message_erreur`, `éléments_traités`, `éléments_créés`, `éléments_modifiés`, `éléments_en_échec`, `déclenché_par`.

---

## 3. Associations et cardinalités

| Association | Entités | Cardinalité | Lecture |
|---|---|---|---|
| PROPOSER | ÉTABLISSEMENT — FORMATION | ÉTAB `(1,N)` — FORM `(1,1)` | Un établissement propose au moins une formation ; une formation appartient à un seul établissement. |
| CLASSER | NIVEAU_DIPLÔME — FORMATION | NIV `(0,N)` — FORM `(0,1)` | Un niveau de diplôme peut concerner plusieurs formations ; le niveau d'une formation peut être absent. |
| RATTACHER_ANNÉE | ANNÉE_UNIVERSITAIRE — FORMATION | ANN `(0,N)` — FORM `(0,1)` | Une année peut décrire plusieurs formations ; une formation peut ne pas publier d'année. |
| EXIGER | FORMATION — EXIGENCE_ADMISSION | FORM `(1,1)` — EXIG `(0,1)` | Une fiche d'admission appartient à une seule formation ; une formation collectée a au plus une fiche. |
| DATER_ADMISSION | ANNÉE_UNIVERSITAIRE — EXIGENCE_ADMISSION | ANN `(0,N)` — EXIG `(0,1)` | Les exigences sont datées de l'année publiée si elle existe. |
| COMPOSER | FORMATION — PROGRAMME_ACADÉMIQUE | FORM `(1,1)` — PROG `(0,1)` | Un programme appartient à une seule formation ; au plus un programme par formation. |
| TARIFIER | FORMATION — TARIF | FORM `(1,N)` — TAR `(1,1)` | Une formation peut avoir plusieurs lignes de frais ; chaque ligne concerne une seule formation. |
| DATER_TARIF | ANNÉE_UNIVERSITAIRE — TARIF | ANN `(0,N)` — TAR `(0,1)` | Un tarif est daté si l'année est publiée. |
| AVOIR_RÔLE | UTILISATEUR — RÔLE | USR `(1,N)` — RÔLE `(0,N)` | Un utilisateur a au moins un rôle ; un rôle peut être attribué à plusieurs utilisateurs. Association porteuse : `date_attribution`, `établissement_limite`, `attribué_par`. |
| DÉTENIR | UTILISATEUR — PROFIL_CANDIDAT | USR `(1,1)` — PROF `(0,1)` | Un profil appartient à un seul utilisateur ; un utilisateur a au plus un profil candidat. |
| POSTULER | UTILISATEUR — FORMATION | USR `(0,N)` — FORM `(0,N)` | Association porteuse transformée en entité CANDIDATURE : `statut`, `consentement`, `date_soumission`, `motivation`, `année`. Un utilisateur ne postule qu'une fois par formation et par année. |
| CONCERNER | CANDIDATURE — UTILISATEUR | CAN `(0,N)` — USR `(1,1)` | Une candidature appartient à un seul candidat. |
| VISER | CANDIDATURE — FORMATION | CAN `(0,N)` — FORM `(1,1)` | Une candidature vise une seule formation existante du catalogue. |
| TRACER | CANDIDATURE — HISTORIQUE_STATUT | CAN `(1,1)` — HIST `(0,N)` | Un historique appartient à une seule candidature ; chaque candidature accumule les transitions. |
| PROVENIR_DE | SOURCE — FORMATION | SRC `(0,N)` — FORM `(0,1)` | Une source peut documenter une formation ; une formation a plusieurs sources. |
| DÉCRIRE | SOURCE — DOCUMENT | SRC `(0,1)` — DOC `(0,N)` | Une source pointe au plus un document local ; un document peut avoir plusieurs sources. |
| LIER | DOCUMENT — FORMATION | DOC `(0,N)` — FORM `(0,N)` | Association many-to-many : un document peut couvrir plusieurs formations. |
| VERSIONNER | DOCUMENT — VERSION_DOCUMENT | DOC `(1,N)` — VER `(1,1)` | Chaque document a au moins une version ; une version appartient à un seul document. Une seule version est courante. |
| SYNCHRONISER_SOURCE | SOURCE — HISTORIQUE_SYNCHRO | SRC `(0,N)` — SYN `(0,1)` | Un historique porte sur zéro ou une source. |
| SYNCHRONISER_DOCUMENT | DOCUMENT — HISTORIQUE_SYNCHRO | DOC `(0,N)` — SYN `(0,1)` | Un historique porte sur zéro ou un document. Au moins l'un des deux doit être renseigné (contrainte d'intégrité). |

---

## 4. Règles de gestion conceptuelles

1. **RG-CAT-01** — Une formation orpheline (sans établissement) est interdite.
2. **RG-CAT-02** — Un tarif publié (`fee_status = published`) doit obligatoirement avoir une devise.
3. **RG-CAT-03** — Aucun libellé de niveau ni d'année n'est créé par défaut : seules les valeurs publiées sont insérées.
4. **RG-CAT-04** — Toute cellule CSV vide devient `NULL` ; aucune valeur de substitution (« inconnu », `0`, `"N/A"`) n'est autorisée.
5. **RG-USR-01** — Le stockage d'un mot de passe en clair est interdit : seul `hash_mot_de_passe` existe.
6. **RG-USR-02** — Un responsable d'établissement doit avoir l'établissement correspondant (`responsable_iit → IIT`, etc.).
7. **RG-USR-03** — Une candidature soumise doit être consentie et datée.
8. **RG-USR-04** — Tout changement de statut est tracé dans l'historique, sans transition vers le même statut.
9. **RG-DOC-01** — Un document est identifié de façon unique par son `sha256` et son URL source ; son chemin local reste traçable.
10. **RG-DOC-02** — Une seule version courante par document.
11. **RG-DOC-03** — `statut_indexation_rag` est un état futur : le présent ticket n'ajoute ni embedding ni chatbot et ne marque aucun document comme `indexed`.
12. **RG-DOC-04** — Un échec de synchronisation doit toujours porter un message d'erreur.

---

## 5. Diagramme

Le diagramme Mermaid ERD correspondant à ce MCD est dans [`diagramme_erd.mmd`](diagramme_erd.mmd). Le passage au relationnel est détaillé dans [`MLD.md`](MLD.md), [`users_candidatures.md`](users_candidatures.md) et [`documents_sync.md`](documents_sync.md).
