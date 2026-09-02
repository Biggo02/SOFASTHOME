import json
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
GEOBOUNDARIES_API = "https://www.geoboundaries.org/api/current/gbOpen/COD/{level}/"
REQUEST_TIMEOUT = 240
RETRIES_PER_ENDPOINT = 2


def clean(value):
    return " ".join(str(value or "").strip().split())


def normalize_name(value):
    value = clean(value).casefold()
    value = re.sub(r"[^a-z0-9àâäçéèêëîïôöùûüÿñœæ -]", " ", value)
    return " ".join(value.split())


def build_geometry(relation):
    try:
        from shapely.geometry import LineString, MultiPolygon, Polygon
        from shapely.ops import polygonize, unary_union
    except ImportError as exc:
        raise CommandError("Shapely est requis. Lancez: pip install -r requirements.txt") from exc

    outer, inner = [], []
    for member in relation.get("members", []):
        if member.get("type") != "way":
            continue
        coords = [
            (p.get("lon"), p.get("lat"))
            for p in (member.get("geometry") or [])
            if p.get("lon") is not None and p.get("lat") is not None
        ]
        if len(coords) < 2:
            continue
        try:
            line = LineString(coords)
        except Exception:
            continue
        if not line.is_empty and line.length > 0:
            (inner if member.get("role") == "inner" else outer).append(line)

    if not outer:
        return None
    try:
        outer_polygons = list(polygonize(unary_union(outer)))
        inner_polygons = list(polygonize(unary_union(inner))) if inner else []
    except Exception:
        return None

    result = []
    for polygon in outer_polygons:
        holes = [
            list(h.exterior.coords)
            for h in inner_polygons
            if polygon.covers(h.representative_point())
        ]
        candidate = Polygon(polygon.exterior.coords, holes)
        if not candidate.is_valid:
            candidate = candidate.buffer(0)
        if not candidate.is_empty and candidate.area > 0:
            if candidate.geom_type == "Polygon":
                result.append(candidate)
            elif candidate.geom_type == "MultiPolygon":
                result.extend(candidate.geoms)

    if not result:
        return None
    geometry = MultiPolygon(result) if len(result) > 1 else result[0]
    return geometry.__geo_interface__


def explicitly_commune(tags):
    values = [
        clean(tags.get(key)).casefold()
        for key in (
            "designation", "official_status", "government", "place",
            "type", "admin_type", "boundary", "name:fr",
        )
    ]
    text = " ".join(values)
    return "commune" in text or "municipalit" in text or "municipality" in text


def is_city_relation(tags):
    values = {
        key: clean(tags.get(key)).casefold()
        for key in (
            "place", "designation", "official_status", "government",
            "admin_type", "type",
        )
    }
    return (
        values.get("place") in {"city", "town"}
        or "ville" in values.get("designation", "")
        or "ville" in values.get("official_status", "")
        or "city" in values.get("designation", "")
        or "city" in values.get("official_status", "")
    )


def is_inside_city(geometry, city_shapes):
    from shapely.geometry import shape
    point = shape(geometry).representative_point()
    return any(city_shape.covers(point) for city_shape in city_shapes)


class Command(BaseCommand):
    help = (
        "Importe les communes de RDC depuis OpenStreetMap avec des requêtes "
        "Overpass découpées par province, sans confondre les secteurs/chefferies/collectivités."
    )

    def add_arguments(self, parser):
        parser.add_argument("--overpass-url", dest="overpass_url", default="", help="Endpoint Overpass personnalisé.")
        parser.add_argument("--clear", action="store_true", help="Efface les communes OSM existantes avant import.")
        parser.add_argument("--province", dest="province", default="", help="Traite uniquement cette province (nom exact ou partiel).")

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            raise CommandError("PostgreSQL + PostGIS sont nécessaires.")

        with connection.cursor() as cursor:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS postgis")
            cursor.execute("SELECT PostGIS_Version()")
            version = cursor.fetchone()[0]
        self.stdout.write(self.style.NOTICE(f"PostGIS {version} détecté."))

        endpoints = [options["overpass_url"]] if options["overpass_url"] else OVERPASS_ENDPOINTS
        provinces = self._load_provinces(options.get("province"))

        if not provinces:
            self.stdout.write(self.style.WARNING(
                "Les provinces n'ont pas encore d'ID OSM. Récupération spatiale des 26 relations OSM..."
            ))
            self._enrich_province_osm_ids(endpoints)
            provinces = self._load_provinces(options.get("province"))

        if not provinces:
            raise CommandError("Aucune province exploitable après récupération des relations OSM.")

        if options["clear"]:
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM core_administrativearea "
                    "WHERE level='commune' AND source LIKE 'OpenStreetMap%%'"
                )
            self.stdout.write(self.style.WARNING("Communes OSM existantes supprimées."))

        self.stdout.write(self.style.NOTICE(
            f"Import découpé: {len(provinces)} province(s), une requête Overpass par province."
        ))

        totals = {"imported": 0, "skipped": 0, "non_communes": 0, "explicit": 0, "spatial": 0}
        failed_provinces = []

        for index, province in enumerate(provinces, 1):
            province_name = province["name"]
            relation_id = province["osm_relation_id"]
            self.stdout.write(f"\n[{index}/{len(provinces)}] {province_name} — relation OSM {relation_id}")

            try:
                data = self._fetch_with_fallback(
                    endpoints, self._province_query(relation_id), province_name
                )
            except CommandError as exc:
                failed_provinces.append(province_name)
                self.stdout.write(self.style.ERROR(f"  Province ignorée: {exc}"))
                continue

            relations = [e for e in data.get("elements", []) if e.get("type") == "relation"]
            level6 = [r for r in relations if (r.get("tags") or {}).get("admin_level") == "6"]
            level7 = [r for r in relations if (r.get("tags") or {}).get("admin_level") == "7"]

            city_shapes = []
            for relation in level6:
                tags = relation.get("tags") or {}
                if not is_city_relation(tags):
                    continue
                geometry = build_geometry(relation)
                if not geometry:
                    continue
                try:
                    from shapely.geometry import shape
                    city_shapes.append(shape(geometry))
                except Exception:
                    continue

            imported = skipped = non_communes = explicit_count = spatial_count = 0

            with transaction.atomic(), connection.cursor() as cursor:
                for relation in level7:
                    tags = relation.get("tags") or {}
                    name = clean(tags.get("name") or tags.get("official_name"))
                    geometry = build_geometry(relation)
                    if not name or not geometry:
                        skipped += 1
                        continue

                    explicit = explicitly_commune(tags)
                    urban = is_inside_city(geometry, city_shapes)
                    if not explicit and not urban:
                        non_communes += 1
                        continue

                    explicit_count += int(explicit)
                    spatial_count += int(not explicit)
                    geom_json = json.dumps(geometry, separators=(",", ":"))
                    source = f"OpenStreetMap relation {relation.get('id')} — admin_level=7"

                    cursor.execute(
                        """
                        INSERT INTO core_administrativearea
                            (level, name, province_name, city_name, geom, source, updated_at)
                        VALUES
                            ('commune', %s, %s, '',
                             ST_Multi(ST_CollectionExtract(
                                 ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326)),3)),
                             %s, NOW())
                        ON CONFLICT (level,name,province_name,city_name)
                        DO UPDATE SET geom=EXCLUDED.geom, source=EXCLUDED.source, updated_at=NOW()
                        """,
                        (name, province_name, geom_json, source),
                    )
                    imported += 1

                # A commune can legally be inside a territory or a city. We keep
                # the existing schema field city_name as the parent administrative
                # label for compatibility with the search code.
                cursor.execute(
                    """
                    WITH candidates AS (
                        SELECT
                            c.id AS commune_id,
                            p.name AS province_name,
                            t.name AS territory_name,
                            CASE WHEN ST_Covers(p.geom, ST_PointOnSurface(c.geom)) THEN 0 ELSE 1 END AS p_rank,
                            CASE WHEN ST_Covers(t.geom, ST_PointOnSurface(c.geom)) THEN 0 ELSE 1 END AS t_rank,
                            ST_Area(ST_Intersection(c.geom,p.geom)) AS p_overlap,
                            ST_Area(ST_Intersection(c.geom,t.geom)) AS t_overlap
                        FROM core_administrativearea c
                        LEFT JOIN core_administrativearea p
                          ON p.level='province' AND ST_Intersects(c.geom,p.geom)
                        LEFT JOIN core_administrativearea t
                          ON t.level='territory' AND ST_Intersects(c.geom,t.geom)
                        WHERE c.level='commune'
                          AND c.source LIKE 'OpenStreetMap%%'
                          AND c.province_name=%s
                    ), ranked AS (
                        SELECT *, ROW_NUMBER() OVER (
                            PARTITION BY commune_id
                            ORDER BY p_rank,t_rank,
                                     p_overlap DESC NULLS LAST,
                                     t_overlap DESC NULLS LAST,
                                     territory_name
                        ) AS rn
                        FROM candidates
                    )
                    UPDATE core_administrativearea c
                       SET province_name=COALESCE(r.province_name,%s),
                           city_name=COALESCE(r.territory_name,''),
                           updated_at=NOW()
                      FROM ranked r
                     WHERE r.rn=1 AND r.commune_id=c.id
                    """,
                    (province_name, province_name),
                )

            totals["imported"] += imported
            totals["skipped"] += skipped
            totals["non_communes"] += non_communes
            totals["explicit"] += explicit_count
            totals["spatial"] += spatial_count
            self.stdout.write(self.style.SUCCESS(
                f"  admin6={len(level6)}, villes={len(city_shapes)}, admin7={len(level7)} → "
                f"communes={imported}, explicites={explicit_count}, urbaines déduites={spatial_count}, "
                f"non-communes refusées={non_communes}, ignorées={skipped}"
            ))
            time.sleep(0.5)

        self.stdout.write("\n" + self.style.SUCCESS("=== IMPORT TERMINÉ ==="))
        self.stdout.write(
            f"Communes importées/mises à jour: {totals['imported']}\n"
            f"Communes explicitement identifiées: {totals['explicit']}\n"
            f"Communes déduites par inclusion dans une ville: {totals['spatial']}\n"
            f"Unités rurales admin_level=7 refusées: {totals['non_communes']}\n"
            f"Relations sans géométrie/nom: {totals['skipped']}"
        )

        if failed_provinces:
            self.stdout.write(self.style.ERROR("Provinces non traitées: " + ", ".join(failed_provinces)))

        self.stdout.write("\nCouverture province → territoire → communes:")
        for province, territory, count in self._coverage():
            self.stdout.write(f"  - {province or '[sans province]'} / {territory or '[sans territoire]'}: {count}")

        self.stdout.write(self.style.WARNING(
            "QUALITÉ: admin_level=7 n'est pas à lui seul une preuve juridique de commune en RDC. "
            "Les secteurs/chefferies/collectivités rurales non explicitement identifiés sont refusés. "
            "La couche OSM reste cartographique et ne remplace pas les textes administratifs officiels."
        ))
        self.stdout.write("Source cartographique: OpenStreetMap / Overpass; attribution OSM requise.")

    def _load_provinces(self, requested):
        with connection.cursor() as cursor:
            cursor.execute("SELECT id,name,source FROM core_administrativearea WHERE level='province' ORDER BY name")
            rows = cursor.fetchall()
        wanted = normalize_name(requested) if requested else ""
        provinces = []
        for row_id, name, source in rows:
            if wanted and wanted not in normalize_name(name):
                continue
            match = re.search(r"(?:OSM(?: relation)?|relation)\s+(\d+)", source or "", re.IGNORECASE)
            if match:
                provinces.append({"id": row_id, "name": name, "osm_relation_id": int(match.group(1))})
        return provinces

    def _enrich_province_osm_ids(self, endpoints):
        query = """
        [out:json][timeout:120];
        area["ISO3166-1"="CD"][boundary=administrative]->.drc;
        relation["boundary"="administrative"]["admin_level"="4"](area.drc);
        out tags center;
        """
        data = self._fetch_with_fallback(endpoints, query, "RDC / provinces")
        relations = [e for e in data.get("elements", []) if e.get("type") == "relation"]
        if not relations:
            raise CommandError("Overpass n'a retourné aucune province admin_level=4.")

        from shapely.geometry import Point
        from shapely.prepared import prep

        with connection.cursor() as cursor:
            cursor.execute("SELECT id,name,geom FROM core_administrativearea WHERE level='province'")
            db_provinces = cursor.fetchall()

        shapes = []
        for row_id, name, geom in db_provinces:
            if geom is None:
                continue
            # PostGIS geometry is converted through WKBElement by Django/psycopg2;
            # use SQL spatial matching below instead of relying on driver geometry types.
            shapes.append((row_id, name))

        mapping = {}
        with connection.cursor() as cursor:
            for relation in relations:
                center = relation.get("center") or {}
                lon, lat = center.get("lon"), center.get("lat")
                if lon is None or lat is None:
                    continue
                cursor.execute(
                    """
                    SELECT id, name
                    FROM core_administrativearea
                    WHERE level='province'
                      AND ST_Covers(geom, ST_SetSRID(ST_Point(%s,%s),4326))
                    ORDER BY name
                    LIMIT 1
                    """,
                    (float(lon), float(lat)),
                )
                row = cursor.fetchone()
                if row:
                    mapping[row[0]] = int(relation["id"])

        updated = 0
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("SELECT id,name,source FROM core_administrativearea WHERE level='province'")
            rows = cursor.fetchall()
            for row_id, name, source in rows:
                osm_id = mapping.get(row_id)
                if not osm_id:
                    continue
                base_source = re.sub(r"\s*\|\s*OSM relation\s+\d+", "", source or "", flags=re.IGNORECASE).strip()
                base_source = re.sub(r"\s*\|\s*OSM relation non disponible", "", base_source, flags=re.IGNORECASE).strip()
                enriched = f"{base_source} | OSM relation {osm_id}"
                cursor.execute(
                    "UPDATE core_administrativearea SET source=%s, updated_at=NOW() WHERE id=%s",
                    (enriched, row_id),
                )
                updated += 1

        self.stdout.write(self.style.SUCCESS(f"  IDs OSM de provinces récupérés spatialement: {updated}/{len(db_provinces)}"))
        if updated < len(db_provinces):
            missing = [name for row_id, name in db_provinces if row_id not in mapping]
            self.stdout.write(self.style.WARNING("  Provinces sans relation OSM: " + ", ".join(missing)))

    @staticmethod
    def _province_query(relation_id):
        area_id = relation_id + 3600000000
        return f"""
        [out:json][timeout:150];
        area({area_id})->.province;
        (
          relation["boundary"="administrative"]["admin_level"="6"](area.province);
          relation["boundary"="administrative"]["admin_level"="7"](area.province);
        );
        out body geom;
        """

    def _fetch_with_fallback(self, endpoints, query, label):
        last_error = None
        for endpoint in endpoints:
            endpoint = endpoint.strip()
            if not endpoint:
                continue
            for attempt in range(1, RETRIES_PER_ENDPOINT + 1):
                self.stdout.write(f"  Overpass: {endpoint} ({label}, tentative {attempt}/{RETRIES_PER_ENDPOINT})")
                request = Request(
                    endpoint,
                    data=query.encode("utf-8"),
                    method="POST",
                    headers={
                        "User-Agent": "FASTHOME/1.0 (DRC commune boundary importer)",
                        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    },
                )
                try:
                    with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                        payload = json.load(response)
                    if not payload.get("elements"):
                        raise CommandError("Réponse Overpass vide.")
                    self.stdout.write(self.style.SUCCESS(f"  Overpass OK: {endpoint}"))
                    return payload
                except (HTTPError, URLError, TimeoutError, ValueError, CommandError) as exc:
                    last_error = exc
                    self.stdout.write(self.style.WARNING(f"  Échec Overpass: {exc}"))
                    time.sleep(1.5 * attempt)
                except KeyboardInterrupt:
                    raise
                except Exception as exc:
                    last_error = exc
                    self.stdout.write(self.style.WARNING(f"  Échec Overpass inattendu: {exc}"))
                    time.sleep(1.5 * attempt)
        raise CommandError(f"Tous les endpoints Overpass ont échoué pour {label}: {last_error}")

    @staticmethod
    def _coverage():
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT province_name, city_name, COUNT(*)
                  FROM core_administrativearea
                 WHERE level='commune' AND source LIKE 'OpenStreetMap%%'
                 GROUP BY province_name, city_name
                 ORDER BY province_name, city_name
                """
            )
            return cursor.fetchall()
