import csv
from pathlib import Path

base = Path("data/proposition_finale")

def lire(nom):
    with (base / nom).open(encoding="utf-8-sig", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        sep = csv.Sniffer().sniff(sample, delimiters=",;").delimiter
        return list(csv.DictReader(f, delimiter=sep))

formations = lire("formations.csv")
admissions = lire("admissions.csv")
programmes = lire("programmes.csv")
tarifs = lire("tarifs.csv")

ids = {f["formation_id"] for f in formations}

print("Formations :", len(formations))
print("Admissions :", len(admissions))
print("Programmes :", len(programmes))
print("Tarifs :", len(tarifs))

for nom, rows in [
    ("admissions", admissions),
    ("programmes", programmes),
    ("tarifs", tarifs)
]:
    erreurs = sum(
        r["formation_id"] not in ids
        for r in rows
    )
    print(nom, "- relations invalides :", erreurs)

manquants = sum(
    not a["required_level"].strip()
    for a in admissions
)

print("Niveaux d'admission manquants :", manquants)
