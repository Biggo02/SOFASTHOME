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
REQUEST_TIMEOUT = 240
RETRIES_PER_ENDPOINT = 2
SUPPORTED_PROVINCES = ("Kinshasa", "Lualaba", "Haut-Katanga")


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
        coords = [(p.get("lon"), p.get("lat")) for p in (member.get("geometry") or []) if p.get("lon") is not None and p.get("lat") is not None]
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
        holes = [list(h.exterior.coords) for h in inner_polygons if polygon.covers(h.representative_point())]
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
    values = [clean(tags.get(key)).casefold() for key in ("designation", "official_status", "government", "place", "type", "admin_type", "boundary", "name:fr")]
    text = " ".join(values)
    return "commune" in text or "municipalit" in text or "municipality" in text


def is_inside_city(geometry, city_shapes):
    from shapely.geometry import shape
    point = shape(geometry).representative_point()
    return any(city_shape.covers(point) for city_shape in city_shapes)


class Command(BaseCommand):
    help = "Importe uniquement les communes des trois provinces couvertes par FASTHOME."

    def add_arguments(self, parser):
        parser.add_argument("--overpass-url", dest="overpass_url", default="", help="Endpoint Overpass personnalisé.")
        parser.add_argument("--clear", action="store_true", help="Efface les communes OSM de la zone FASTHOME avant import.")
        parser.add_argument("--province", dest="province", default="", help="Traite uniquement Kinshasa, Lualaba ou Haut-Katanga.")

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            raise CommandError("PostgreSQL + PostGIS sont nécessaires.")
        with connection.cursor() as cursor:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS postgis")
            cursor.execute("SELECT PostGIS_Version()")
            version = cursor.fetchone()[0]
        self.stdout.write(self.style.NOTICE(f"PostGIS {version} détecté."))

        endpoints = [options["overpass_url"]] if options["overpass_url"] else OVERPASS_ENDPOINTS
        provinces = self._load_supported_provinces(options.get("province"))
        if not provinces:
            requested = clean(options.get("province"))
            if requested:
                raise CommandError(f"Province '{requested}' hors périmètre FASTHOME. Provinces autorisées: {', '.join(SUPPORTED_PROVINCES)}.")
            raise CommandError("Aucune des trois provinces FASTHOME n'existe dans core_administrativearea. Lancez d'abord bootstrap_drc_boundaries.")

        if options["clear"]:
            names = [p["name"] for p in provinces]
            placeholders = ",".join(["%s"] * len(names))
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM core_administrativearea WHERE level='commune' AND source LIKE 'OpenStreetMap%%' "
                    f"AND province_name IN ({placeholders})", names,
                )
            self.stdout.write(self.style.WARNING("Communes OSM supprimées uniquement pour la zone FASTHOME: " + ", ".join(names)))

        self.stdout.write(self.style.NOTICE(f"Périmètre FASTHOME: {', '.join(p['name'] for p in provinces)}. Une requête Overpass par province."))
        totals = {"imported": 0, "skipped": 0, "non_communes": 0, "explicit": 0, "spatial": 0}
        failed_provinces = []

        for index, province in enumerate(provinces, 1):
            province_name = province["name"]
            self.stdout.write(f"\n[{index}/{len(provinces)}] {province_name}")
            try:
                relation_id = self._find_province_relation_id(endpoints, province_name)
                self.stdout.write(f"  Relation OSM admin_level=4: {relation_id}")
                data = self._fetch_with_fallback(endpoints, self._province_query(relation_id), province_name)
            except CommandError as exc:
                failed_provinces.append(province_name)
                self.stdout.write(self.style.ERROR(f"  Province ignorée: {exc}"))
                continue

            relations = [e for e in data.get("elements", []) if e.get("type") == "relation"]
            level6 = [r for r in relations if (r.get("tags") or {}).get("admin_level") == "6"]
            level7 = [r for r in relations if (r.get("tags") or {}).get("admin_level") == "7"]
            # Les relations admin_level=6 retournées dans cette requête sont les villes.
            # Leurs zones sont utilisées directement par Overpass pour récupérer leurs communes.
            city_shapes = []
            city_names = []
            for relation in level6:
                geometry = build_geometry(relation)
                if geometry:
                    try:
                        from shapely.geometry import shape
                        city_shapes.append(shape(geometry))
                    except Exception:
                        pass
                tags = relation.get("tags") or {}
                city_names.append(clean(tags.get("name")))

            imported = skipped = non_communes = explicit_count = spatial_count = 0
            with transaction.atomic(), connection.cursor() as cursor:
                for relation in level7:
                    tags = relation.get("tags") or {}
                    name = clean(tags.get("name") or tags.get("official_name"))
                    geometry = build_geometry(relation)
                    if not name or not geometry:
                        skipped += 1
                        continue
                    # Une relation admin_level=7 issue d'une zone de ville est une commune
                    # urbaine. Les admin_level=7 ruraux restent refusés sauf indication
                    # explicite dans leurs tags.
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
                             ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326)),3)),
                             %s, NOW())
                        ON CONFLICT (level,name,province_name,city_name)
                        DO UPDATE SET geom=EXCLUDED.geom, source=EXCLUDED.source, updated_at=NOW()
                        """,
                        (name, province_name, geom_json, source),
                    )
                    imported += 1

                cursor.execute(
                    """
                    WITH candidates AS (
                        SELECT c.id AS commune_id, p.name AS province_name, t.name AS territory_name,
                               CASE WHEN ST_Covers(p.geom, ST_PointOnSurface(c.geom)) THEN 0 ELSE 1 END AS p_rank,
                               CASE WHEN ST_Covers(t.geom, ST_PointOnSurface(c.geom)) THEN 0 ELSE 1 END AS t_rank,
                               ST_Area(ST_Intersection(c.geom,p.geom)) AS p_overlap,
                               ST_Area(ST_Intersection(c.geom,t.geom)) AS t_overlap
                        FROM core_administrativearea c
                        LEFT JOIN core_administrativearea p ON p.level='province' AND ST_Intersects(c.geom,p.geom)
                        LEFT JOIN core_administrativearea t ON t.level='territory' AND ST_Intersects(c.geom,t.geom)
                        WHERE c.level='commune' AND c.source LIKE 'OpenStreetMap%%' AND c.province_name=%s
                    ), ranked AS (
                        SELECT *, ROW_NUMBER() OVER (
                            PARTITION BY commune_id
                            ORDER BY p_rank,t_rank,p_overlap DESC NULLS LAST,t_overlap DESC NULLS LAST,territory_name
                        ) AS rn FROM candidates
                    )
                    UPDATE core_administrativearea c
                       SET province_name=COALESCE(r.province_name,%s), city_name=COALESCE(r.territory_name,''), updated_at=NOW()
                      FROM ranked r WHERE r.rn=1 AND r.commune_id=c.id
                    """, (province_name, province_name),
                )

            totals["imported"] += imported
            totals["skipped"] += skipped
            totals["non_communes"] += non_communes
            totals["explicit"] += explicit_count
            totals["spatial"] += spatial_count
            self.stdout.write(self.style.SUCCESS(
                f"  villes détectées={len(level6)} ({', '.join(city_names) or 'aucune'}), admin7={len(level7)} → "
                f"communes={imported}, explicites={explicit_count}, urbaines={spatial_count}, "
                f"non-communes refusées={non_communes}, ignorées={skipped}"
            ))
            time.sleep(0.5)

        self.stdout.write("\n" + self.style.SUCCESS("=== IMPORT FASTHOME TERMINÉ ==="))
        self.stdout.write(
            f"Communes importées/mises à jour: {totals['imported']}\n"
            f"Communes explicitement identifiées: {totals['explicit']}\n"
            f"Communes déduites par inclusion dans une ville: {totals['spatial']}\n"
            f"Unités rurales admin_level=7 refusées: {totals['non_communes']}\n"
            f"Relations sans géométrie/nom: {totals['skipped']}"
        )
        if failed_provinces:
            self.stdout.write(self.style.ERROR("Provinces non traitées: " + ", ".join(failed_provinces)))
        self.stdout.write("\nCouverture FASTHOME province → territoire → communes:")
        for province, territory, count in self._coverage():
            self.stdout.write(f"  - {province or '[sans province]'} / {territory or '[sans territoire]'}: {count}")
        self.stdout.write(self.style.WARNING(
            "QUALITÉ: admin_level=7 n'est pas à lui seul une preuve juridique de commune en RDC. "
            "Les secteurs/chefferies/collectivités rurales non explicitement identifiés sont refusés."
        ))
        self.stdout.write("Source cartographique: OpenStreetMap / Overpass; attribution OSM requise.")

    def _load_supported_provinces(self, requested):
        wanted = normalize_name(requested) if requested else ""
        allowed = {normalize_name(name) for name in SUPPORTED_PROVINCES}
        if wanted and wanted not in allowed:
            return []
        with connection.cursor() as cursor:
            cursor.execute("SELECT id,name FROM core_administrativearea WHERE level='province' ORDER BY name")
            rows = cursor.fetchall()
        return [
            {"id": row_id, "name": name}
            for row_id, name in rows
            if normalize_name(name) in allowed and (not wanted or normalize_name(name) == wanted)
        ]

    def _find_province_relation_id(self, endpoints, province_name):
        query = f"""
        [out:json][timeout:45];
        relation["boundary"="administrative"]["admin_level"="4"]["name"={json.dumps(province_name)}];
        out tags;
        """
        data = self._fetch_with_fallback(endpoints, query, f"OSM {province_name}")
        wanted = normalize_name(province_name)
        for relation in data.get("elements", []):
            tags = relation.get("tags") or {}
            if normalize_name(tags.get("name")) == wanted or normalize_name(tags.get("name:fr")) == wanted:
                return int(relation["id"])
        raise CommandError(f"Aucune relation OSM admin_level=4 trouvée pour {province_name}.")

    def _province_query(self, relation_id):
        # On récupère d'abord les villes (admin_level=6), puis on transforme
        # chaque ville en area. Les communes sont ensuite cherchées dans ces
        # areas, ce qui évite de confondre les collectivités rurales admin_level=7
        # avec les communes urbaines.
        return f"""
        [out:json][timeout:180];
        relation({int(relation_id)})->.province_relation;
        .province_relation map_to_area -> .province_area;
        relation(area.province_area)["boundary"="administrative"]["admin_level"="6"]->.cities;
        .cities map_to_area -> .city_areas;
        (
          .cities;
          relation(area.city_areas)["boundary"="administrative"]["admin_level"="7"];
        );
        out tags geom;
        """

    def _fetch_with_fallback(self, endpoints, query, label):
        last_error = None
        for endpoint in endpoints:
            for attempt in range(1, RETRIES_PER_ENDPOINT + 1):
                try:
                    self.stdout.write(self.style.NOTICE(f"  Overpass {endpoint.split('//')[-1].split('/')[0]} tentative {attempt}..."))
                    request = Request(
                        endpoint, data=query.encode("utf-8"),
                        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "FASTHOME/1.0"}, method="POST",
                    )
                    with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                        return json.loads(response.read().decode("utf-8"))
                except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
                    last_error = exc
                    self.stdout.write(self.style.WARNING(f"    Échec: {exc}"))
                    if attempt < RETRIES_PER_ENDPOINT:
                        time.sleep(2)
        raise CommandError(f"Overpass indisponible pour {label}: {last_error}")

    def _coverage(self):
        allowed = list(SUPPORTED_PROVINCES)
        placeholders = ",".join(["%s"] * len(allowed))
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT province_name, city_name, COUNT(*) FROM core_administrativearea "
                "WHERE level='commune' AND province_name IN (" + placeholders + ") "
                "GROUP BY province_name, city_name ORDER BY province_name, city_name",
                allowed,
            )
            return cursor.fetchall()
