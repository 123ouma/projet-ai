"""Audit non destructif des CSV SmartCampus AI. Aucune correction factuelle inventée."""
import csv
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = BASE / 'data' / 'processed' if (BASE / 'data' / 'processed').exists() else BASE
OUT = BASE / 'audit_sortie'
OUT.mkdir(parents=True, exist_ok=True)

required = ['formations', 'admissions', 'programmes', 'tarifs']
for name in required:
    if not (DATA / f'{name}.csv').exists():
        raise SystemExit(f'Fichier manquant : {DATA / (name + ".csv")}')

sources = {}
p = DATA / 'sources.csv'
if p.exists():
    with p.open(encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            key = (row.get('formation_id',''),row.get('attribute',''))
            sources.setdefault(key, []).append(row)

def read(name):
    with (DATA / (name+'.csv')).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

def write(path, rows, fields):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)

flags=[]
def flag(name,row,col,why):
    refs=sources.get((row.get('formation_id',''),col),[])
    flags.append({'fichier':name+'.csv','formation_id':row.get('formation_id',''),
                  'ligne_id':row.get(name[:-1]+'_id',row.get('tarif_id','')),
                  'champ':col,'valeur_actuelle':row.get(col,''), 'probleme':why,
                  'source_url':row.get('source_url','') or (refs[0].get('source_url','') if refs else ''),
                  'preuve':(refs[0].get('evidence_excerpt','')[:250] if refs else ''),
                  'nouvelle_valeur_verifiee':'', 'decision':'A_VERIFIER'})

for name in required:
    rows=read(name)
    for row in rows:
        if name=='formations':
            for col in ('field','speciality'):
                v=row.get(col,'').strip()
                if v and (len(v)<4 or len(v)>70 or v[0].islower() or v.endswith(':') or v.endswith('.')):
                    flag(name,row,col,'Valeur ressemblant a un fragment de texte, pas a une categorie')
            v=row.get('diploma_awarded','').strip()
            if '|' in v or (v.lower()=='licence' and 'master' in row.get('degree_type','').lower()):
                flag(name,row,'diploma_awarded','Diplome potentiellement confondu avec liste de navigation')
        elif name=='admissions':
            v=row.get('required_baccalaureate','')
            if v and any(t in v.lower() for t in ['prépa','mastère','master','bac +','licence']):
                flag(name,row,'required_baccalaureate','Niveaux universitaires confondus avec types de bac')
            v=row.get('required_level','')
            if v and (v.startswith('niveau ') or v.endswith('.')):
                flag(name,row,'required_level','Formulation incomplète ou extrait de phrase')
        elif name=='programmes':
            for col in ('subjects','modules'):
                v=row.get(col,'')
                if v and ('?' in v or 'copier la réponse' in v.lower() or len(v)>500):
                    flag(name,row,col,'Contenu FAQ / paragraphe et non liste fiable de matieres ou modules')
        elif name=='tarifs':
            if row.get('tuition_fee','').strip() or row.get('registration_fee','').strip():
                flag(name,row,'tuition_fee','Montant non confirme comme frais de scolarite : verifier preuve exacte avant import')
                row['fee_status']='needs_review'
                row['verification_status']='needs_review'
    fields=list(rows[0].keys()) if rows else list(csv.DictReader((DATA/(name+'.csv')).open(encoding='utf-8-sig',newline='')).fieldnames)
    write(OUT/(name+'_a_verifier.csv'),rows,fields)

write(OUT/'rapport_anomalies.csv',flags,['fichier','formation_id','ligne_id','champ','valeur_actuelle','probleme','source_url','preuve','nouvelle_valeur_verifiee','decision'])
print('Audit termine :',len(flags),'anomalies signalees')
print('Consulter :',OUT.resolve())
print('Aucun fichier original modifie. Les montants ont ete marques needs_review dans la COPIE uniquement.')
