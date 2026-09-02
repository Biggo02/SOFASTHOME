# Référentiel administratif RDC — FASTHOME

FASTHOME utilise PostGIS pour les recherches géographiques. Le bootstrap national télécharge automatiquement les limites ouvertes geoBoundaries pour la RDC.

## Niveaux disponibles

- `ADM1` → 26 provinces
- `ADM2` → villes et territoires (189 unités dans la source actuelle)
- `ADM3` → niveau supplémentaire disponible dans geoBoundaries, importable séparément; il ne doit pas être présenté automatiquement comme « commune » car la source le décrit comme territoire.
- `commune` → frontières communales opérationnelles récupérées depuis OpenStreetMap/Overpass lorsque leur qualification communale peut être établie par les règles du chargeur.

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

Le chargeur des communes utilise Shapely. La dépendance est déjà déclarée dans `requirements.txt` sous la forme `Shapely>=2.0,<3.0`. fileciteturn418file0L2-L2

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

### Communes OpenStreetMap

Pour importer ou reconstruire la couche nationale des communes détectées par OSM:

```bash
python manage.py bootstrap_drc_communes --clear
```

Le chargeur interroge Overpass et récupère les relations administratives `admin_level=6` et `admin_level=7`. Il ne transforme pas aveuglément tout `admin_level=7` en commune: en RDC ce niveau peut aussi représenter d'autres unités. Une unité est retenue lorsqu'elle est explicitement identifiée comme communale ou lorsqu'elle est couverte par une frontière de ville `admin_level=6`. Le code d'import correspond à cette logique. fileciteturn419file0L2-L2

Cette couche OSM est une couverture géographique opérationnelle pour la recherche FASTHOME. Elle ne doit pas être présentée comme un registre juridique exhaustif des communes de la RDC sans validation administrative complémentaire.

## Audit après import

Après les imports, lancer:

```bash
python manage.py audit_drc_admin --verbose-coverage
```

L'audit contrôle notamment:

- le nombre de provinces, territoires/villes et communes;
- les communes sans province ou parent;
- les doublons nom + parent;
- la couverture de Lubumbashi;
- les provinces et territoires/villes sans commune importée.

L'audit est en lecture seule et ne modifie aucune donnée.

## Recherche et communes limitrophes

La recherche FASTHOME peut utiliser les géométries des communes pour élargir une recherche lorsque la commune demandée fournit moins de cinq résultats exacts. L'élargissement reste soumis au budget maximum, au nombre minimal de salons/chambres et à la capacité maximale demandée.

Ne pas utiliser automatiquement une couche ADM3 ou ADM7 comme synonyme de « commune » sans validation de sa signification administrative.

## Source et attribution

La source programmatique principale des provinces et territoires/villes est geoBoundaries `gbOpen` pour `COD`. geoBoundaries documente son API et indique que gbOpen est sous CC-BY 4.0; l'attribution est donc conservée dans FASTHOME.

Pour les communes, la source est OpenStreetMap via Overpass. Les données OpenStreetMap sont © les contributeurs OpenStreetMap et sont distribuées sous licence ODbL; FASTHOME doit conserver l'attribution requise lors de leur utilisation et affichage.
