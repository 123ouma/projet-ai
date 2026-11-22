# Préparer les livrables GitHub depuis le projet LOCAL actuel.
# Exécuter dans le dossier SmartCampus_Data :
#   powershell -ExecutionPolicy Bypass -File .\prepare_smartcampus_github.ps1
$ErrorActionPreference = 'Stop'
$source = (Get-Location).Path
if (-not (Test-Path (Join-Path $source 'modelisation'))) {
  throw 'Ouvrez PowerShell dans le dossier SmartCampus_Data avant de lancer ce script.'
}
$parent = Split-Path $source -Parent
$destination = Join-Path $parent 'SmartCampus_Data_Livrables'
if (Test-Path $destination) {
  $destination = Join-Path $parent ('SmartCampus_Data_Livrables_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
}
New-Item -ItemType Directory -Path $destination -Force | Out-Null
$required = @(
  'modelisation/MCD.md',
  'modelisation/MLD.md',
  'modelisation/diagramme_erd.mmd',
  'modelisation/catalogue.md',
  'modelisation/users_candidatures.md',
  'modelisation/documents_sync.md',
  'database/migrations/001_catalogue.sql',
  'database/migrations/002_users_candidatures.sql',
  'database/migrations/003_documents_sync.sql',
  'database/queries/verification.sql',
  'scripts/create_database.py',
  'scripts/import_csv.py',
  'scripts/verify_database.py',
  'requirements.txt'
)
$optional = @('database/db.py','README.md')
$missing = @()
foreach ($relative in ($required + $optional)) {
  $origin = Join-Path $source $relative
  if (Test-Path -LiteralPath $origin -PathType Leaf) {
    $target = Join-Path $destination $relative
    New-Item -ItemType Directory -Path (Split-Path $target -Parent) -Force | Out-Null
    Copy-Item -LiteralPath $origin -Destination $target -Force
  } elseif ($required -contains $relative) {
    $missing += $relative
  }
}
# Copier les tests, en excluant les caches.
if (Test-Path (Join-Path $source 'tests')) {
  $testFolder = Join-Path $destination 'tests'
  New-Item -ItemType Directory -Path $testFolder -Force | Out-Null
  Get-ChildItem (Join-Path $source 'tests') -Filter '*.py' -File | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $testFolder
  }
}
# Copier les rapports générés réellement par les scripts, sans fabriquer de résultats.
$reports = @('verification_report_db.json','verification_report_db.md','import_report.json','validation_report.json','validation_report.md')
$reportPath = Join-Path $destination 'rapports'
New-Item -ItemType Directory -Path $reportPath -Force | Out-Null
foreach ($report in $reports) {
  $origin = Join-Path (Join-Path $source 'data/exports') $report
  if (Test-Path -LiteralPath $origin -PathType Leaf) {
    Copy-Item -LiteralPath $origin -Destination $reportPath
  }
}
# Exemple sans secrets : ne pas copier le .env local.
@'
# Copiez ce fichier vers .env et renseignez les valeurs uniquement en local.
DATABASE_URL=postgresql://postgres:CHANGE_ME@127.0.0.1:5432/smartcampus_db
DATABASE_URL_ADMIN=postgresql://postgres:CHANGE_ME@127.0.0.1:5432/postgres
DATABASE_URL_TEST=postgresql://postgres:CHANGE_ME@127.0.0.1:5432/smartcampus_ai_test
'@ | Set-Content -Path (Join-Path $destination '.env.example') -Encoding UTF8
@'
.env
.env.*
!.env.example
.venv/
__pycache__/
.pytest_cache/
*.py[cod]
*.log
*.bak
*.zip
data/raw/
data/processed/
data/exports/
'@ | Set-Content -Path (Join-Path $destination '.gitignore') -Encoding UTF8
@'
# SmartCampus AI — Livrables Data / PostgreSQL

## Périmètre
- SA-12 : modélisation du catalogue académique
- SA-13 : modélisation des utilisateurs et candidatures
- SA-14 : documents, sources et synchronisation
- SA-17 : migrations et validation PostgreSQL

## Dossiers
- `modelisation/` : MCD, MLD, diagramme ERD et documentation
- `database/migrations/` : scripts SQL exécutables dans l'ordre 001 → 003
- `database/queries/` : requêtes de vérification
- `scripts/` : création de la base, import CSV et vérification
- `tests/` : tests automatisés
- `rapports/` : rapports copiés depuis l'exécution locale (si présents)

## Installation
1. Installer Python, PostgreSQL et les dépendances de `requirements.txt`.
2. Créer localement `.env` depuis `.env.example` et renseigner les identifiants.
3. Fournir les CSV de SA-18 dans les chemins attendus par `scripts/import_csv.py`.
4. Exécuter la création des tables, puis l'import, puis les vérifications.

**Attention** : les CSV SA-18 ne sont pas inclus dans ce paquet de livrables.
Les rapports éventuels documentent les exécutions effectuées sur le poste d'origine ; le présent script ne relance pas PostgreSQL ni les tests.
'@ | Set-Content -Path (Join-Path $destination 'README.md') -Encoding UTF8
$files = Get-ChildItem -Path $destination -File -Recurse
$problematic = $files | Where-Object {
  $_.Name -notin @('.env.example', 'README.md', '.gitignore') -and
  $_.Extension -in @('.py','.sql','.md','.json','.txt') -and
  (Select-String -LiteralPath $_.FullName -Pattern 'postgresql://[^\s]+:[^\s]+@' -Quiet -ErrorAction SilentlyContinue)
}
$manifest = @()
$manifest += 'LIVRABLES SMARTCAMPUS AI'
$manifest += "Générés le: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
$manifest += "Source locale: $source"
$manifest += "Fichiers: $($files.Count)"
$manifest += "Rapports présents: $((Get-ChildItem $reportPath -File).Count)"
if ($missing.Count -gt 0) { $manifest += ('FICHIERS OBLIGATOIRES MANQUANTS: ' + ($missing -join ', ')) }
else { $manifest += 'Tous les fichiers obligatoires ont été trouvés.' }
if ($problematic.Count -gt 0) { $manifest += 'ATTENTION: vérifier manuellement les URLs de connexion dans ces fichiers: ' + (($problematic | ForEach-Object FullName) -join ', ') }
$manifest | Set-Content -Path (Join-Path $destination 'CONTROLE_LIVRABLES.txt') -Encoding UTF8
$zip = "$destination.zip"
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory($destination, $zip)
Write-Host "Dossier créé : $destination"
Write-Host "ZIP créé     : $zip"
Write-Host "Manquants    : $($missing.Count)"
Write-Host 'Lire CONTROLE_LIVRABLES.txt et vérifier les rapports avant publication.'
