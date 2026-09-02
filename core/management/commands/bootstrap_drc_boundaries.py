import json
from urllib.request import Request, urlopen

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

API = "https://www.geoboundaries.org/api/current/gbOpen/COD/{level}/"
LEVELS = {"ADM1": "province", "ADM2": "territory", "ADM3": "subterritory"}


def first_value(props, *names):
    for name in names:
        value = props.get(name)
        if value not in (None, ""):
            return str(value).strip()
    return ""


class Command(BaseCommand):
    help = "Importe les limites administratives ouvertes de toute la RDC dans PostGIS avec rattachement spatial."

    def add_arguments(self, parser):
        parser.add_argument("--levels", default="ADM1,ADM2", help="Niveaux geoBoundaries à importer: ADM1, ADM2 ou ADM3.")
        parser.add_argument("--simplified", action="store_true", help="Utilise la géométrie simplifiée.")
        parser.add_argument("--clear", action="store_true", help="Supprime les niveaux concernés avant import.")

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            raise CommandError("PostGIS nécessite PostgreSQL.")
        with connection.cursor() as cursor:
            try:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS postgis")
                cursor.execute("SELECT PostGIS_Version()")
                version = cursor.fetchone()[0]
            except Exception as exc:
                raise CommandError(f"PostGIS n'est pas disponible: {exc}") from exc

        requested = [x.strip().upper() for x in options["levels"].split(",") if x.strip()]
        unknown = [x for x in requested if x not in LEVELS]
        if unknown:
            raise CommandError(f"Niveaux inconnus: {', '.join(unknown)}")
        if "ADM2" in requested and "ADM1" not in requested:
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM core_administrativearea WHERE level='province'")
                if cursor.fetchone()[0] == 0:
                    raise CommandError("ADM2 nécessite d'abord les provinces ADM1.")

        self.stdout.write(self.style.NOTICE(f"PostGIS {version} détecté. Import national RDC en cours..."))
        totals = {}
        for level in requested:
            metadata = self._fetch_json(API.format(level=level))
            url = metadata.get("simplifiedGeometryGeoJSON") if options["simplified"] else metadata.get("gjDownloadURL")
            if not url:
                raise CommandError(f"Aucune URL GeoJSON disponible pour {level}.")
            self.stdout.write(f"\n{level}: {metadata.get('boundaryCanonical', '')} — {metadata.get('admUnitCount', '?')} unités")
            data = self._fetch_json(url)
            totals[level] = self._import_features(level, data, metadata, options["clear"])

        self.stdout.write(self.style.SUCCESS("Import terminé: " + ", ".join(f"{level}={count}" for level, count in totals.items())))
        self._report_hierarchy()
        self.stdout.write("Source: geoBoundaries gbOpen / sources RGC-OCHA-OSM selon le niveau; attribution requise.")

    def _import_features(self, level, data, metadata, clear):
        if data.get("type") != "FeatureCollection":
            raise CommandError(f"{level}: le GeoJSON n'est pas une FeatureCollection.")
        db_level = LEVELS[level]
        imported = skipped = 0
        source = f"geoBoundaries gbOpen — {metadata.get('boundarySource', 'RDC')}"

        with transaction.atomic(), connection.cursor() as cursor:
            if clear:
                cursor.execute("DELETE FROM core_administrativearea WHERE level = %s", [db_level])

            for feature in data.get("features", []):
                props = feature.get("properties") or {}
                geometry = feature.get("geometry")
                name = first_value(props, "shapeName", "NAME_1", "NAME_2", "NAME_3", "name")
                if not name or not geometry or geometry.get("type") not in ("Polygon", "MultiPolygon"):
                    skipped += 1
                    continue

                province = first_value(props, "shapeName_1", "NAME_1", "province", "PROVINCE")
                parent = first_value(props, "shapeName_2", "NAME_2", "city", "territory", "DISTRICT", "CITY")
                if level == "ADM1":
                    province, parent = name, ""
                elif level == "ADM2":
                    # geoBoundaries ADM2 does not reliably provide the province
                    # in its properties. Resolve it from the geometry BEFORE the
                    # insert so the unique key is (territory, name, province, city)
                    # instead of incorrectly using an empty province for every unit.
                    province = ""
                    parent = ""
                else:
                    parent = ""

                geom_json = json.dumps(geometry, separators=(",", ":"))

                if level == "ADM2":
                    # The province is determined spatially against the canonical
                    # ADM1 polygons. ST_PointOnSurface avoids failures with a
                    # boundary that only partially overlaps the province polygon.
                    cursor.execute(
                        """
                        WITH new_geom AS (
                            SELECT ST_Multi(
                                ST_CollectionExtract(
                                    ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)), 3
                                )
                            ) AS geom
                        ),
                        province_match AS (
                            SELECT p.name
                            FROM core_administrativearea AS p, new_geom AS g
                            WHERE p.level = 'province'
                              AND ST_Intersects(g.geom, p.geom)
                            ORDER BY
                                CASE WHEN ST_Covers(p.geom, ST_PointOnSurface(g.geom)) THEN 0 ELSE 1 END,
                                ST_Area(ST_Intersection(g.geom, p.geom)) DESC,
                                p.name
                            LIMIT 1
                        )
                        INSERT INTO core_administrativearea
                            (level, name, province_name, city_name, geom, source, updated_at)
                        SELECT
                            'territory', %s,
                            COALESCE((SELECT name FROM province_match), ''),
                            '', new_geom.geom, %s, NOW()
                        FROM new_geom
                        ON CONFLICT (level, name, province_name, city_name)
                        DO UPDATE SET
                            geom = EXCLUDED.geom,
                            source = EXCLUDED.source,
                            updated_at = NOW()
                        """,
                        [geom_json, name, source],
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO core_administrativearea
                            (level, name, province_name, city_name, geom, source, updated_at)
                        VALUES
                            (%s, %s, %s, %s,
                             ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)), 3)),
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

            if level == "ADM2":
                cursor.execute(
                    """
                    WITH candidates AS (
                        SELECT
                            child.id AS child_id,
                            p.name AS province_name,
                            CASE WHEN ST_Covers(p.geom, ST_PointOnSurface(child.geom)) THEN 0 ELSE 1 END AS cover_rank,
                            ST_Area(ST_Intersection(child.geom, p.geom)) AS overlap_area
                        FROM core_administrativearea AS child
                        JOIN core_administrativearea AS p
                          ON p.level = 'province'
                         AND ST_Intersects(child.geom, p.geom)
                        WHERE child.level = 'territory'
                    ),
                    best_parent AS (
                        SELECT DISTINCT ON (child_id)
                            child_id, province_name
                        FROM candidates
                        ORDER BY child_id, cover_rank, overlap_area DESC, province_name
                    )
                    UPDATE core_administrativearea AS child
                    SET province_name = best_parent.province_name,
                        updated_at = NOW()
                    FROM best_parent
                    WHERE child.id = best_parent.child_id
                    """
                )
                spatial_parented = cursor.rowcount
            else:
                spatial_parented = 0

        if level == "ADM2":
            self.stdout.write(self.style.SUCCESS(f"  ✓ {imported} importées, {skipped} ignorées; {spatial_parented} rattachées spatialement à une province"))
        else:
            self.stdout.write(self.style.SUCCESS(f"  ✓ {imported} importées, {skipped} ignorées"))
        return imported

    def _report_hierarchy(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM core_administrativearea WHERE level='province'")
            provinces = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM core_administrativearea WHERE level='territory'")
            territories = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM core_administrativearea WHERE level='territory' AND province_name <> ''")
            attached = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM core_administrativearea WHERE level='territory' AND (province_name IS NULL OR province_name='')")
            orphaned = cursor.fetchone()[0]
        self.stdout.write(f"Hiérarchie RDC: provinces={provinces}, ADM2={territories}, ADM2 rattachées={attached}, ADM2 sans province={orphaned}")

    @staticmethod
    def _fetch_json(url):
        request = Request(url, headers={"User-Agent": "FASTHOME/1.0 (administrative-boundaries importer)"})
        with urlopen(request, timeout=180) as response:
            return json.load(response)
