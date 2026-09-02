# Référentiel administratif RDC — FASTHOME

FASTHOME utilise PostGIS pour les recherches géographiques. Le bootstrap national télécharge automatiquement les limites ouvertes geoBoundaries pour la RDC.

## Niveaux disponibles

- `ADM1` → 26 provinces
- `ADM2` → villes et territoires (189 unités dans la source actuelle)
- `ADM3` → niveau supplémentaire disponible dans geoBoundaries, importable séparément; il ne doit pas être présenté automatiquement comme « commune » car la source le décrit comme territoire.

## Installation

Configurer PostgreSQL + PostGIS puis activer le backend spatial:

```bash
export POSTGIS=1
python manage.py migrate
```

Sur Windows PowerShell:

```powershell
$env:POSTGIS="1"
python manage.py migrate
```

## Import national

Version complète:

```bash
python manage.py bootstrap_drc_boundaries --levels ADM1,ADM2
```

Version simplifiée, recommandée pour les premiers tests:

```bash
python manage.py bootstrap_drc_boundaries --levels ADM1,ADM2 --simplified
```

Pour ajouter le niveau ADM3:

```bash
python manage.py bootstrap_drc_boundaries --levels ADM3 --simplified
```

Pour reconstruire les niveaux:

```bash
python manage.py bootstrap_drc_boundaries --levels ADM1,ADM2 --simplified --clear
```

## Source et licence

La source programmatique utilisée est geoBoundaries `gbOpen` pour `COD`. geoBoundaries documente son API et indique que gbOpen est sous CC-BY 4.0; l'attribution est donc conservée dans FASTHOME.

Les ADM1 actuels indiquent 26 provinces. Les ADM2 indiquent 189 unités et proviennent du Référentiel Géographique Commun / OCHA RDC. Les limites communales urbaines ne sont pas uniformément disponibles à l'échelle nationale dans cette source; FASTHOME ne les invente pas.
