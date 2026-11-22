import csv
import shutil
from pathlib import Path

path = Path("data/proposition_finale/admissions.csv")
backup = Path("data/proposition_finale/admissions_avant_complement.csv")

if not backup.exists():
    shutil.copy2(path, backup)

corrections = {
    "IIT-genie-des-procedes-iit":
        "Prépa MP/PC/PT ou licence admissible",

    "IIT-genie-mecanique-iit":
        "Prépa ou licence admissible",

    "IIT-genie-industriel-iit":
        "Prépa ou licence admissible",

    "IIT-ecole-d-architecture-privee-a-sfax-iit-isa":
        "Baccalauréat",

    "IIT-mastere-industrie-4-0-a-sfax-iit-tunisie":
        "Licence",

    "ISB-mastere-professionnel-en-comptabilite":
        "Licence",

    "ISB-mastere-droit-des-affaires-en-tunisie-isb-sfax":
        "Licence admissible",

    "ISB-mastere-marketing-digital-en-tunisie-international-school-of-business":
        "Licence admissible",

    "ISB-master-marketing-digital-en-anglais-en-tunisie-isb":
        "Licence admissible",

    "ISA-formation-en-architecture-en-tunisie-cursus-diplome-isa":
        "Baccalauréat"
}

with path.open("r", encoding="utf-8-sig", newline="") as f:
    sample = f.read(4096)
    f.seek(0)
    sep = csv.Sniffer().sniff(sample, delimiters=",;").delimiter
    reader = csv.DictReader(f, delimiter=sep)
    columns = reader.fieldnames
    rows = list(reader)

count = 0

for row in rows:
    fid = row["formation_id"]

    if fid in corrections and not row["required_level"].strip():
        row["required_level"] = corrections[fid]
        count += 1
        print("Complété :", fid)

with path.open("w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=columns, delimiter=sep)
    writer.writeheader()
    writer.writerows(rows)

print("Total complété :", count)
