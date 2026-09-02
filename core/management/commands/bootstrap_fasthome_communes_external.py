"""Fallback géographique FASTHOME basé sur geoBoundaries.

OSM reste prioritaire. Ce module complète uniquement les communes du
référentiel FASTHOME qui n'ont pas pu être géométrisées depuis OSM.
geoBoundaries gbOpen est utilisé car sa licence est ouverte sous CC-BY 4.0.
"""

import json
import re
from urllib.request import Request, urlopen

from django.core.management.base import CommandError
from django.db import connection, transaction

from .bootstrap_fasthome_communes import Command as OSMCommand
from .bootstrap_fasthome_communes import STRUCTURE, clean, normalize_name

GEBOUNDARIES_API = "https://www.geoboundaries.org/api/current/gbOpen/COD/ADM4/"
FETCH_TIMEOUT = 180

# Variantes rencontrées dans les bases cartographiques.
NAME_ALIASES = {
    "annexe": "Annexes",
    "annexes": "Annexes",
    "tshituru": "Shituru",
    "shitur": "Shituru",
    "ona selembao": "Ona (Selembao)",
    "selembao": "Ona (Selembao)",
}


def norm(value):
    value = normalize_name(value)
    return NAME_ALIASES.get(value, value)


class Command(OSMCommand):
    help = "Importe le référentiel FASTHOME avec OSM puis un fallback geoBoundaries pour les communes manquantes."

    def _import_province(self, province, data):
        imported, missing, unlisted = super()._import_province(province, data)

        if not missing:
            return imported, missing, unlisted

        self.stdout.write(self.style.NOTICE(
            "  Fallback geoBoundaries: recherche des géométries manquantes..."
        ))
        try:
            features, metadata = self._fetch_geoboundaries()
        except Exception as exc:
            self.stdout.write(self.style.WARNING(
                f"  geoBoundaries indisponible: {exc}"
            ))
            return imported, missing, unlisted

        inserted = self._import_missing_from_geoboundaries(province, missing, features, metadata)
        imported += inserted
        missing -= set(self._last_external_found)

        self.stdout.write(self.style.SUCCESS(
            f"  geoBoundaries: {inserted} géométries supplémentaires importées, "
            f"{len(missing)} toujours manquantes"
        ))
        if missing:
            self.stdout.write(self.style.WARNING(
                "  Toujours sans géométrie: " + ", ".join(sorted(missing))
            ))
        return imported, len(missing), unlisted

    def _fetch_json(self, url):
        request = Request(url, headers={"User-Agent": "FASTHOME/1.0"})
        with urlopen(request, timeout=FETCH_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))

    def _fetch_geoboundaries(self):
        metadata = self._fetch_json(GEBOUNDARIES_API)
        geojson_url = metadata.get("gjDownloadURL") or metadata.get("simplifiedGeometryGeoJSON")
        if not geojson_url:
            raise CommandError("geoBoundaries n'a fourni aucun lien GeoJSON.")
        features_data = self._fetch_json(geojson_url)
        features = features_data.get("features", [])
        if not features:
            raise CommandError("Le GeoJSON geoBoundaries ADM4 est vide.")
        return features, metadata

    def _feature_name(self, feature):
        props = feature.get("properties") or {}
        for key in (
            "shapeName", "shapeName_1", "name", "NAME_4", "NAME_3",
            "admin4Name", "ADM4_NAME", "name_fr", "NAME",
        ):
            value = clean(props.get(key))
            if value:
                return value
        return ""

    def _import_missing_from_geoboundaries(self, province, missing, features, metadata):
        expected = {norm(name): (name, parent) for parent, children in STRUCTURE[province].items() for name in children}
        matched = {}

        for feature in features:
            raw_name = self._feature_name(feature)
            key = norm(raw_name)
            if key not in expected:
                continue
            canonical, parent = expected[key]
            geometry = feature.get("geometry")
            if not geometry or geometry.get("type") not in ("Polygon", "MultiPolygon"):
                continue
            # Ne jamais remplacer une géométrie OSM déjà importée.
            if canonical not in missing:
                continue
            matched[canonical] = (parent, geometry, raw_name)

        self._last_external_found = set(matched)
        if not matched:
            return 0

        source = "geoBoundaries gbOpen ADM4"
        license_name = clean(metadata.get("boundaryLicense"))
        source_url = clean(metadata.get("licenseSource"))
        if license_name:
            source += f" — licence {license_name}"
        if source_url:
            source += f" — source {source_url}"

        with transaction.atomic(), connection.cursor() as cursor:
            for canonical, (parent, geometry, raw_name) in matched.items():
                cursor.execute(
                    """
                    INSERT INTO core_administrativearea
                        (level,name,province_name,city_name,geom,source,updated_at)
                    VALUES
                        ('commune',%s,%s,%s,
                         ST_Multi(ST_CollectionExtract(
                           ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326)),3)),
                         %s,NOW())
                    ON CONFLICT (level,name,province_name,city_name)
                    DO UPDATE SET geom=EXCLUDED.geom,source=EXCLUDED.source,updated_at=NOW()
                    """,
                    (
                        canonical,
                        province,
                        parent,
                        json.dumps(geometry, separators=(",", ":")),
                        source,
                    ),
                )
                self.stdout.write(
                    f"    ✓ {canonical} ← {raw_name} (parent: {parent})"
                )
        return len(matched)
