"""SmartCampus AI — étape 3, préparation prudente de CSV à valider.

Prérequis: placer smartcampus_verification_partielle.zip à côté de ce script.
Exécuter depuis la racine du projet: python finaliser_nettoyage.py
Aucun fichier dans data/processed/ n'est modifié.
"""
from pathlib import Path
import csv
import io
import zipfile

RACINE = Path(__file__).resolve().parent
ORIGINAUX = RACINE / "data" / "processed"
ARCHIVE = RACINE / "smartcampus_verification_partielle.zip"
DEST = RACINE / "data" / "proposition_finale"
FICHIERS = ["formations", "admissions", "programmes", "tarifs"]


def lire_csv(chemin, delimiteur=","):
    with chemin.open("r", encoding="utf-8-sig", newline="") as f:
        lecteur = csv.DictReader(f, delimiter=delimiteur)
        if not lecteur.fieldnames:
            raise ValueError(f"En-tête manquant: {chemin}")
        return lecteur.fieldnames, list(lecteur)


def lire_dans_zip(archive, nom):
    with archive.open("verification_smartcampus/" + nom) as f:
        lecteur = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig", newline=""), delimiter=";")
        return lecteur.fieldnames, list(lecteur)


def ecrire_csv(chemin, champs, lignes):
    with chemin.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=champs, delimiter=",", extrasaction="ignore")
        w.writeheader()
        w.writerows(lignes)


def main():
    if not ARCHIVE.is_file():
        raise SystemExit(f"Archive manquante : {ARCHIVE}\nTélécharge le ZIP et place-le à côté de ce script.")
    if not ORIGINAUX.is_dir():
        raise SystemExit(f"Dossier CSV introuvable : {ORIGINAUX}")

    DEST.mkdir(parents=True, exist_ok=True)
    compte = {"CONFIRME_SITE": 0, "VALEUR_INVALIDE": 0,
              "DEPLACER_VERS_REQUIRED_LEVEL": 0, "NORMALISATION_A_VALIDER": 0}
    suivis = []

    with zipfile.ZipFile(ARCHIVE) as archive:
        _, rapport = lire_dans_zip(archive, "rapport_verification_officielle.csv")
        par_fichier = {}
        for item in rapport:
            par_fichier.setdefault(item["fichier"], []).append(item)

        for nom in FICHIERS:
            champs, originaux = lire_csv(ORIGINAUX / f"{nom}.csv")
            champs_corriges, corriges = lire_dans_zip(archive, f"{nom}_corrige_partiellement.csv")
            if champs != champs_corriges:
                raise ValueError(f"Colonnes différentes dans {nom}.csv : arrêt de sécurité")
            id_col = {"formations": "formation_id", "admissions": "admission_id",
                      "programmes": "programme_id", "tarifs": "tarif_id"}[nom]
            orig_ids = [r[id_col] for r in originaux]
            corr_par_id = {r[id_col]: r for r in corriges}
            if len(orig_ids) != len(set(orig_ids)) or set(orig_ids) != set(corr_par_id):
                raise ValueError(f"Identifiants incompatibles pour {nom}.csv : arrêt de sécurité")
            sortie = [dict(r) for r in originaux]
            sortie_par_id = {r[id_col]: r for r in sortie}

            for probleme in par_fichier.get(f"{nom}.csv", []):
                ligne_id = probleme["ligne_id"]
                champ = probleme["champ"]
                decision = probleme["decision"]
                r = sortie_par_id.get(ligne_id)
                if r is None or champ not in champs:
                    raise ValueError(f"Référence inconnue: {nom}/{ligne_id}/{champ}")
                # Ne toucher qu'aux données restées identiques aux données auditées.
                if r[champ] != probleme["valeur_actuelle"]:
                    raise ValueError(f"Valeur modifiée depuis l'audit: {nom}/{ligne_id}/{champ}")
                compte[decision] = compte.get(decision, 0) + 1
                nouvelle = r[champ]
                statut = ""
                if decision == "CONFIRME_SITE":
                    nouvelle = probleme["nouvelle_valeur_verifiee"]
                    statut = "correction issue du rapport de vérification ; contrôler la source"
                elif decision == "VALEUR_INVALIDE":
                    nouvelle = ""
                    statut = "ancienne valeur incorrecte écartée"
                elif decision == "DEPLACER_VERS_REQUIRED_LEVEL":
                    nouvelle = ""
                    # Le prérequis est une autre donnée: pas de recopie automatique
                    # vers required_level si une valeur s'y trouve déjà.
                    statut = "bac effacé ; prérequis de niveau à contrôler séparément"
                elif decision == "NORMALISATION_A_VALIDER":
                    nouvelle = ""
                    statut = "valeur douteuse écartée ; proposition à confirmer"
                else:
                    raise ValueError(f"Décision inconnue: {decision}")
                r[champ] = nouvelle
                suivis.append({
                    "fichier": nom + ".csv", "ligne_id": ligne_id, "champ": champ,
                    "ancienne_valeur": probleme["valeur_actuelle"],
                    "valeur_dans_proposition": nouvelle,
                    "proposition_a_verifier": probleme["nouvelle_valeur_verifiee"] if decision == "NORMALISATION_A_VALIDER" else "",
                    "decision_rapport": decision, "commentaire": statut,
                    "source_url": probleme["source_url"],
                })

            # Champs importants des tarifs: les données restent indicatives.
            if nom == "tarifs":
                for r in sortie:
                    # Ne pas attribuer 'published' à un chiffre sans preuve.
                    correspondant = corr_par_id[r[id_col]]
                    if r.get("fee_status") == "published" and correspondant.get("fee_status", "").startswith("indicative_"):
                        r["fee_status"] = correspondant["fee_status"]

            ecrire_csv(DEST / f"{nom}.csv", champs, sortie)
            print(f"{nom}.csv : {len(sortie)} lignes conservées")

    # Ces trois CSV n'ont pas fait l'objet de cet audit: copie, PAS validation.
    for nom in ("etablissements", "documents", "sources"):
        source = ORIGINAUX / f"{nom}.csv"
        if source.is_file():
            (DEST / f"{nom}.csv").write_bytes(source.read_bytes())

    champs_suivi = ["fichier", "ligne_id", "champ", "ancienne_valeur",
                    "valeur_dans_proposition", "proposition_a_verifier",
                    "decision_rapport", "commentaire", "source_url"]
    ecrire_csv(DEST / "corrections_et_points_a_verifier.csv", champs_suivi, suivis)
    print("\nRécapitulatif de l'audit :", compte)
    print("Proposition de données :", DEST)
    print("IMPORTANT : proposition non validée intégralement. N'importe pas encore dans PostgreSQL.")
    print("Contrôle manuel nécessaire, y compris les données non signalées par l'audit.")


if __name__ == "__main__":
    main()
