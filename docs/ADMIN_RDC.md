# Référentiel administratif RDC — FASTHOME

FASTHOME limite volontairement sa localisation au niveau **Commune / Commune rurale**.

La hiérarchie utilisée par l'application est exclusivement :

**Province → Ville / Territoire → Commune / Commune rurale**

Aucun quartier, aucune frontière GPS et aucune source géographique externe ne sont nécessaires pour le fonctionnement du site.

## Source de référence

Le référentiel opérationnel est celui du document fourni pour FASTHOME :

`liaisons_parent_enfant_rdc (1).pdf`

Ce document couvre les provinces de **Kinshasa, Haut-Katanga et Lualaba** et définit les relations parent-enfant utilisées par FASTHOME.

## Structure retenue

### Kinshasa

Kinshasa est traitée comme province-ville et ses communes sont :

- Bandalungwa
- Barumbu
- Bumbu
- Gombe
- Kalamu
- Kasa-Vubu
- Kimbanseke
- Kinshasa
- Kintambo
- Kisenso
- Lemba
- Limete
- Lingwala
- Makala
- Maluku
- Masina
- Matete
- Ngaba
- Ngaliema
- Ngiri-Ngiri
- Nsele
- Mont-Ngafula
- Ona (Selembao)
- Ndjili

### Haut-Katanga

**Lubumbashi** :

- Kamalondo
- Kampemba
- Katuba
- Kenya
- Lubumbashi
- Ruashi
- Annexes

**Likasi** :

- Kikula
- Likasi
- Panda
- Shituru

**Kasumbalesa** :

- Musoshi
- Kasumbalesa

### Lualaba

**Kolwezi** :

- Dilala
- Manika

**Kasaji** :

- Lua
- Monde
- Kasaji

**Lubudi** :

- Lubudi
- Fungurume

## Règles d'application

- Le champ géographique final d'un bien est toujours la **commune**.
- La recherche utilisateur ne descend jamais au niveau quartier.
- Les résultats affichent la commune et la ville / territoire, sans quartier.
- Le matching géographique compare uniquement Province, Ville / Territoire et Commune.
- Une faute de frappe peut être tolérée lors de la comparaison des noms administratifs connus du référentiel.
- Aucun calcul de distance ou de commune limitrophe n'est effectué.
- Aucune requête OSM, Overpass, geoBoundaries, Nominatim ou autre service géographique externe ne doit être ajoutée.
