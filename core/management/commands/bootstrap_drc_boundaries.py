import json
from urllib.request import Request, urlopen

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction


API = "https://www.geoboundaries.org/api/current/gbOpen/COD/{level}/"
LEVELS = {
    "ADM1": "province",
    "ADM2": "territory",
    "ADM3": "subterritory",
}


def first_value(props, *names):
    for name in names:
        value = props.get(name)
        if value not in (None, ""):
            return str(value).strip()
    return ""


class Command(BaseCommand):
    help = "Importe les limites administratives ouvertes de toute la RDC dans PostGIS avec rattachement spatial des niveaux."

    def add_arguments(self, parser):
        parser.add_argument(
            "--levels",
            default="ADM1,ADM2",
            help="Niveaux geoBoundaries à importer, par défaut ADM1,ADM2. ADM3 peut être ajouté séparément.",
        )
        parser.add_argument(
            "--simplified",
            action="store_true",
            help="Utilise la géométrie simplifiée pour réduire la taille et accélérer l'import.",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Supprime les niveaux concernés avant import.",
        )

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            raise CommandError("PostGIS nécessite PostgreSQL. Configurez DATABASE_URL avec une base PostgreSQL + PostGIS.")
        try:
            with connection.cursor() as cursor:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS postgis")
                cursor.execute("SELECT PostGIS_Version()")
                version = cursor.fetchone()[0]
        except Exception as exc:
            raise CommandError(f"PostGIS n'est pas disponible: {exc}") from exc

        requested = [x.strip().upper() for x in options["levels"].split(",") if x.strip()]
        unknown = [x for x in requested if x not in LEVELS]
        if unknown:
            raise CommandError(f"Niveaux inconnus: {', '.join(unknown)}. Utilisez ADM1, ADM2 ou ADM3.")

        self.stdout.write(self.style.NOTICE(f"PostGIS {version} détecté. Import national RDC en cours..."))
        totals = {}

        # ADM1 must exist before ADM2 so that province parents can be resolved spatially.
        if "ADM2" in requested and "ADM1" not in requested:
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM core_administrativearea WHERE level='province'")
                if cursor.fetchone()[0] == 0:
                    raise CommandError("ADM2 nécessite d'abord les provinces ADM1. Lancez avec --levels ADM1,ADM2.")

        for level in requested:
            metadata = self._fetch_json(API.format(level=level))
            url = metadata.get("simplifiedGeometryGeoJSON") if options["simplified"] else metadata.get("gjDownloadURL")
            if not url:
                raise CommandError(f"Aucune URL GeoJSON disponible pour {level}.")
            self.stdout.write(
                f"\n{level}: {metadata.get('boundaryCanonical', '')} — {metadata.get('admUnitCount', '?')} unités"
            )
            data = self._fetch_json(url)
            count = self._import_features(level, data, metadata, options["clear"])
            totals[level] = count

        self.stdout.write(self.style.SUCCESS(
            "Import terminé: " + ", ".join(f"{level}={count}" for level, count in totals.items())
        ))
        self._report_hierarchy()
        self.stdout.write(
            "Source: geoBoundaries gbOpen / sources RGC-OCHA-OSM selon le niveau; attribution requise."
        )

    def _import_features(self, level, data, metadata, clear):
        if data.get("type") != "FeatureCollection":
            raise CommandError(f"{level}: le GeoJSON n'est pas une FeatureCollection.")

        db_level = LEVELS[level]
        imported = 0
        skipped = 0
        spatial_parented = 0
        source = f"geoBoundaries gbOpen — {metadata.get('boundarySource', 'RDC')}"

        with transaction.atomic(), connection.cursor() as cursor:
            if clear:
                cursor.execute("DELETE FROM core_administrativearea WHERE level = %s", [db_level])

            for feature in data.get("features", []):
                props = feature.get("properties") or {}
                geometry = feature.get("geometry")
                name = first_value(props, "shapeName", "NAME_1", "NAME_2", "NAME_3", "name")
                if not name or not geometry:
                    skipped += 1
                    continue
                if geometry.get("type") not in ("Polygon", "MultiPolygon"):
                    skipped += 1
                    continue

                province = first_value(props, "shapeName_1", "NAME_1", "province", "PROVINCE")
                parent = first_value(props, "shapeName_2", "NAME_2", "city", "territory", "DISTRICT", "CITY")
                if level == "ADM1":
                    province = name
                    parent = ""
                elif level == "ADM2":
                    # The current DRC ADM2 GeoJSON does not reliably expose the parent
                    # province in the expected property names. Resolve it from geometry.
                    province = ""
                    parent = ""
                else:
                    # ADM3 is deliberately kept separate. It is not renamed to "commune"
                    # because an administrative level number alone does not prove that
                    # every unit is a DRC commune.
                    parent = ""

                geom_json = json.dumps(geometry, separators=(",", ":"))
                cursor.execute(
                    """
                    INSERT INTO core_administrativearea
                        (level, name, province_name, city_name, geom, source, updated_at)
                    VALUES
                        (%s, %s, %s, %s,
                         ST_Multi(ST_CollectionExtract(ST_MakeValid(
                           ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)), 3)),
                         %s, NOW())
                    ON CONFLICT (level, name, province_name, city_name)
                    DO UPDATE SET
                        geom = EXCLUDED.geom,
                        source = EXCLUDED.source,
                        updated_at = NOW()
                    """,
                    [db_level, name, province, parent, geom_json, source],
                )
                imported += 1

            # For ADM2, derive the province parent from spatial containment/maximum
            # intersection with the already imported ADM1 polygons. This is much safer
            # than guessing from names or undocumented property columns.
            if level == "ADM2":
                cursor.execute(
                    """
                    UPDATE core_administrativearea child
                    SET province_name = parent.name,
                        updated_at = NOW()
                    FROM LATERAL (
                        SELECT p.name
                        FROM core_administrativearea p
                        WHERE p.level = 'province'
                          AND ST_Intersects(child.geom, p.geom)
                        ORDER BY
                          CASE WHEN ST_Covers(p.geom, ST_PointOnSurface(child.geom)) THEN 0 ELSE 1 END,
                          ST_Area(ST_Intersection(child.geom, p.geom)) DESC,
                          p.id
                        LIMIT 1
                    ) parent
                    WHERE child.level = 'territory'
                      AND (child.province_name IS NULL OR child.province_name = '')
                    """
                )
                spatial_parented = cursor.rowcount

        if level == "ADM2":
            self.stdout.write(self.style.SUCCESS(
                f"  ✓ {imported} importées, {skipped} ignorées; {spatial_parented} rattachées spatialement à une province"
            ))
        else:
            self.stdout.write(self.style.SUCCESS(f"  ✓ {imported} importées, {skipped} ignorées"))
        return imported

    def _report_hierarchy(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM core_administrativearea WHERE level='province'")
            provinces = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM core_administrativearea WHERE level='territory'")
            territories = cursor.fetchone()[0]
            cursor.execute(
                "SELECT COUNT(*) FROM core_administrativearea WHERE level='territory' AND province_name <> ''"
            )
            attached = cursor.fetchone()[0]
            cursor.execute(
                "SELECT COUNT(*) FROM core_administrativearea WHERE level='territory' AND (province_name IS NULL OR province_name='')"
            )
            orphaned = cursor.fetchone()[0]
        self.stdout.write(
            f"Hiérarchie RDC: provinces={provinces}, ADM2={territories}, ADM2 rattachées={attached}, ADM2 sans province={orphaned}"
        )

    @staticmethod
    def _fetch_json(url):
        request = Request(url, headers={"User-Agent": "FASTHOME/1.0 (administrative-boundaries importer)"})
        with urlopen(request, timeout=180) as response:
            return json.load(response)
