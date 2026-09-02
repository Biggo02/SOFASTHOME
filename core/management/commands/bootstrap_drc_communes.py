"""Point d'entrée historique de l'import géographique FASTHOME."""

# OSM est utilisé en priorité, puis geoBoundaries complète les communes
# du référentiel FASTHOME dont OSM ne fournit pas la géométrie exploitable.
from .bootstrap_fasthome_communes_external import Command
