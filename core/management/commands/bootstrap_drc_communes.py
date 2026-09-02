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

# A national Overpass query containing every geometry in the DRC is too heavy and
# routinely returns 504.  We therefore query one province-area at a time.
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
    """Accept only tags that explicitly describe the unit as a commune/municipality."""
    values = [
        clean(tags.get(key)).casefold()
        for key in (
            "designation",
            "official_status",
            "government",
            "place",
            "type",
            "admin_type",
            "boundary",
            "name:fr",
        )
    ]
    text = " ".join(values)
    return (
        "commune" in text
        or "municipalit" in text
        or "municipality" in text
    )


def is_city_relation(tags):
    values = {
        key: clean(tags.get(key)).casefold()
        for key in (
            "place",
            "designation",
            "official_status",
            "government",
            "admin_type",
            "type",
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
        parser.add_argument(
            "--overpass-url",
            dest="overpass_url",
            default="",
            help="Endpoint Overpass personnalisé (facultatif).",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Efface les communes OSM existantes avant import.",
        )
        parser.add_argument(
            "--province",
            dest="province",
            default="",
            help="Traite uniquement cette province (nom exact ou partiel).",
        )

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
            raise CommandError("Aucune province trouvée dans core_administrativearea.")

        with transaction.atomic(), connection.cursor() as cursor:
            if options["clear"]:
                cursor.execute(
                    "DELETE FROM core_administrativearea "
                    "WHERE level='commune' AND source LIKE 'OpenStreetMap%'"
                )
                self.stdout.write(self.style.WARNING("Communes OSM existantes supprimées."))

        total_imported = 0
        total_skipped = 0
        total_non_communes = 0
        total_explicit = 0
        total_spatial = 0
        failed_provinces = []

        self.stdout.write(
            self.style.NOTICE(
                f"Import découpé: {len(provinces)} province(s), une requête Overpass par province."
            )
        )

        for index, province in enumerate(provinces, 1):
            province_name = province["name"]
            relation_id = province["osm_relation_id"]
            self.stdout.write(
                f"\n[{index}/{len(provinces)}] {province_name} — relation OSM {relation_id}"
            )

            query = self._province_query(relation_id)
            try:
                data = self._fetch_with_fallback(endpoints, query, province_name)
            except CommandError as exc:
                failed_provinces.append(province_name)
                self.stdout.write(self.style.ERROR(f"Province ignorée: {exc}"))
                continue

            relations = [e for e in data.get("elements", []) if e.get("type") == "relation"]
            level6 = [
                r for r in relations
                if (r.get("tags") or {}).get("admin_level") == "6"
            ]
            level7 = [
                r for r in relations
                if (r.get("tags") or {}).get("admin_level") == "7"
            ]

            city_shapes = []
            for relation in level6:
                tags = relation.get("tags") or {}
                geometry = build_geometry(relation)
                if not geometry:
                    continue
                if is_city_relation(tags):
                    try:
                        from shapely.geometry import shape
                        city_shapes.append((clean(tags.get("name")), shape(geometry)))
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

                    # OSM admin_level=7 is not enough in rural DRC: it can mean
                    # collectivité, secteur or chefferie. Only explicit commune
                    # tagging or inclusion in a clearly identified city is accepted.
                    if not explicit and not urban:
                        non_communes += 1
                        continue

                    if explicit:
                        explicit_count += 1
                    else:
                        spatial_count += 1

                    geom_json = json.dumps(geometry, separators=(",", ":"))
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
                        DO UPDATE SET
                            geom=EXCLUDED.geom,
                            source=EXCLUDED.source,
                            updated_at=NOW()
                        """,
                        [
                            name,
                            province_name,
                            geom_json,
                            f"OpenStreetMap relation {relation.get('id')} — admin_level=7",
                        ],
                    )
                    imported += 1

                # Attach every imported commune to the best containing city/territory.
                # Territory is intentionally used as the parent label because a DRC
                # commune may legally exist inside a territory as well as inside a city.
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
                          AND c.source LIKE 'OpenStreetMap%'
                          AND c.province_name=%s
                    ), ranked AS (
                        SELECT *, ROW_NUMBER() OVER (
                            PARTITION BY commune_id
                            ORDER BY p_rank, t_rank,
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
                    [province_name, province_name],
                )

            total_imported += imported
            total_skipped += skipped
            total_non_communes += non_communes
            total_explicit += explicit_count
            total_spatial += spatial_count

            self.stdout.write(
                self.style.SUCCESS(
                    f"  admin6={len(level6)}, villes={len(city_shapes)}, admin7={len(level7)} → "
                    f"communes={imported}, explicites={explicit_count}, urbaines déduites={spatial_count}, "
                    f"non-communes refusées={non_communes}, ignorées={skipped}"
                )
            )

        coverage = self._coverage()
        self.stdout.write("\n" + self.style.SUCCESS("=== IMPORT TERMINÉ ==="))
        self.stdout.write(
            f"Communes importées/mises à jour: {total_imported}\n"
            f"Communes explicitement identifiées: {total_explicit}\n"
            f"Communes déduites par inclusion dans une ville: {total_spatial}\n"
            f"Unités rurales admin_level=7 refusées: {total_non_communes}\n"
            f"Relations sans géométrie/nom: {total_skipped}"
        )

        if failed_provinces:
            self.stdout.write(
                self.style.ERROR(
                    "Provinces non traitées: " + ", ".join(failed_provinces)
                )
            )
            self.stdout.write(
                self.style.WARNING(
                    "Relance possible avec --province <nom> pour traiter uniquement une province échouée."
                )
            )

        self.stdout.write("\nCouverture province → territoire → communes:")
        for province, territory, count in coverage:
            self.stdout.write(f"  - {province or '[sans province]'} / {territory or '[sans territoire]'}: {count}")

        self.stdout.write(
            self.style.WARNING(
                "QUALITÉ: admin_level=7 n'est pas à lui seul une preuve juridique de commune en RDC. "
                "Les secteurs/chefferies/collectivités rurales non explicitement identifiés sont refusés. "
                "La couche OSM reste cartographique et ne remplace pas les textes administratifs officiels."
            )
        )
        self.stdout.write("Source cartographique: OpenStreetMap / Overpass; attribution OSM requise.")

        if failed_provinces:
            raise CommandError(
                f"Import partiel: {len(failed_provinces)} province(s) n'ont pas pu être interrogées."
            )

    def _load_provinces(self, requested):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, name, source
                  FROM core_administrativearea
                 WHERE level='province'
                 ORDER BY name
                """
            )
            rows = cursor.fetchall()

        provinces = []
        wanted = normalize_name(requested) if requested else ""
        for row_id, name, source in rows:
            if wanted and wanted not in normalize_name(name):
                continue
            match = re.search(r"relation\s+(\d+)", source or "")
            if not match:
                # Old imports may not contain the OSM relation id in source.
                continue
            provinces.append({
                "id": row_id,
                "name": name,
                "osm_relation_id": int(match.group(1)),
            })
        return provinces

    def _province_query(self, relation_id):
        # Overpass area ids are relation ids + 3600000000.
        area_id = relation_id + 3600000000
        return f"""
        [out:json][timeout:210];
        area({area_id})->.province;
        (
          relation["boundary"="administrative"]["admin_level"="6"](area.province);
          relation["boundary"="administrative"]["admin_level"="7"](area.province);
        );
        out body geom;
        """

    def _fetch_with_fallback(self, endpoints, query, province_name):
        last_error = None
        for endpoint in endpoints:
            endpoint = endpoint.strip()
            if not endpoint:
                continue
            for attempt in range(1, RETRIES_PER_ENDPOINT + 1):
                self.stdout.write(
                    f"  Overpass: {endpoint} (tentative {attempt}/{RETRIES_PER_ENDPOINT})"
                )
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
                    self.stdout.write(self.style.SUCCESS("  Overpass OK"))
                    return payload
                except KeyboardInterrupt:
                    raise
                except (HTTPError, URLError, TimeoutError, ValueError, CommandError) as exc:
                    last_error = exc
                    self.stdout.write(self.style.WARNING(f"  Échec: {exc}"))
                    if attempt < RETRIES_PER_ENDPOINT:
                        time.sleep(2)
                except Exception as exc:
                    last_error = exc
                    self.stdout.write(self.style.WARNING(f"  Échec inattendu: {exc}"))
                    if attempt < RETRIES_PER_ENDPOINT:
                        time.sleep(2)

        raise CommandError(f"Tous les endpoints Overpass ont échoué pour {province_name}: {last_error}")

    def _coverage(self):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT province_name, city_name, COUNT(*)
                  FROM core_administrativearea
                 WHERE level='commune' AND source LIKE 'OpenStreetMap%'
                 GROUP BY province_name, city_name
                 ORDER BY province_name, city_name
                """
            )
            return cursor.fetchall()
