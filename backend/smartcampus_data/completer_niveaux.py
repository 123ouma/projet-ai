import csv
from pathlib import Path

base = Path("data/proposition_finale")
path = base / "admissions.csv"
formations_path = base / "formations.csv"

def lire_csv(p):
    with p.open("r", encoding="utf-8-sig", newline="") as f:
        delimiteur = csv.Sniffer().sniff(
            f.read(4096), delimiters=",;"
        ).delimiter
        f.seek(0)
        lecteur = csv.DictReader(f, delimiter=delimiteur)
        return list(lecteur), lecteur.fieldnames, delimiteur

admissions, colonnes, sep = lire_csv(path)
formations, _, _ = lire_csv(formations_path)

noms = {
    f["formation_id"]: f["formation_name"].lower()
    for f in formations
}

compteur = 0

for ligne in admissions:
    if ligne["required_level"].strip():
        continue

    identifiant = ligne["formation_id"]
    nom = noms.get(identifiant, "")

    if (
        "licence" in nom
        or "licence" in identifiant.lower()
        or "cycle-preparatoire" in identifiant.lower()
    ):
        ligne["required_level"] = "Baccalauréat"
        compteur += 1
        print("Complété :", identifiant)

with path.open("w", encoding="utf-8-sig", newline="") as f:
    ecrivain = csv.DictWriter(
        f, fieldnames=colonnes, delimiter=sep
    )
    ecrivain.writeheader()
    ecrivain.writerows(admissions)

print("Niveaux complétés :", compteur)
