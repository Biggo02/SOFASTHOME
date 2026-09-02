import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]


def clean(value):
    return " ".join(str(value or "").strip().split())


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
    text = " ".join(
        clean(tags.get(key))
        for key in ("designation", "official_status", "government", "place", "type")
    ).lower()
    return "commune" in text or "municipalit" in text or "municipality" in text


def is_urban_inside_city(geometry, city_shapes):
    from shapely.geometry import shape

    point = shape(geometry).representative_point()
    return any(city_shape.covers(point) for city_shape in city_shapes)


class Command(BaseCommand):
    help = (
        "Importe les communes urbaines RDC depuis OpenStreetMap, avec repli Overpass, "
        "reconstruction géométrique et rattachement PostGIS."
    )

    def add_arguments(self, parser):
        parser.add_argument("--overpass-url", default="", help="Endpoint Overpass personnalisé (facultatif).")
        parser.add_argument("--clear", action="store_true", help="Efface les communes OSM existantes avant import.")

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            raise CommandError("PostgreSQL + PostGIS sont nécessaires.")

        with connection.cursor() as cursor:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS postgis")
            cursor.execute("SELECT PostGIS_Version()")
            version = cursor.fetchone()[0]
        self.stdout.write(self.style.NOTICE(f"PostGIS {version} détecté."))

        query = """
        [out:json][timeout:900];
        area["ISO3166-1"="CD"][boundary=administrative]->.drc;
        (
          relation["boundary"="administrative"]["admin_level"="6"](area.drc);
          relation["boundary"="administrative"]["admin_level"="7"](area.drc);
        );
        out body geom;
        """

        endpoints = [options["overpass_url"]] if options["overpass_url"] else OVERPASS_ENDPOINTS
        data = self._fetch_with_fallback(endpoints, query)
        relations = [e for e in data.get("elements", []) if e.get("type") == "relation"]
        cities = [r for r in relations if (r.get("tags") or {}).get("admin_level") == "6"]
        level7 = [r for r in relations if (r.get("tags") or {}).get("admin_level") == "7"]

        if not level7:
            raise CommandError("Overpass n'a retourné aucune relation admin_level=7 pour la RDC.")

        try:
            from shapely.geometry import shape
        except ImportError as exc:
            raise CommandError("Shapely est requis. Lancez: pip install -r requirements.txt") from exc

        # Les noms servent à l'affichage/diagnostic; le fallback utilise uniquement les géométries.
        city_shapes = []
        for city in cities:
            geometry = build_geometry(city)
            if geometry:
                city_shapes.append((clean((city.get("tags") or {}).get("name")), shape(geometry)))

        self.stdout.write(
            f"OSM: {len(cities)} villes admin_level=6 et {len(level7)} unités admin_level=7 reçues."
        )
        imported = skipped = non_communes = 0
        explicit_count = spatial_count = 0

        with transaction.atomic(), connection.cursor() as cursor:
            if options["clear"]:
                cursor.execute(
                    "DELETE FROM core_administrativearea "
                    "WHERE level='commune' AND source LIKE 'OpenStreetMap%'"
                )

            city_geometries = [geometry for _, geometry in city_shapes]

            for relation in level7:
                tags = relation.get("tags") or {}
                name = clean(tags.get("name") or tags.get("official_name"))
                geometry = build_geometry(relation)
                if not name or not geometry:
                    skipped += 1
                    continue

                explicit = explicitly_commune(tags)
                urban = explicit or is_urban_inside_city(geometry, city_geometries)
                if not urban:
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
                        ('commune', %s, '', '',
                         ST_Multi(ST_CollectionExtract(
                           ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326)),3)),
                         %s, NOW())
                    ON CONFLICT (level,name,province_name,city_name)
                    DO UPDATE SET
                        geom=EXCLUDED.geom,
                        source=EXCLUDED.source,
                        updated_at=NOW()
                    """,
                    [name, geom_json, f"OpenStreetMap relation {relation.get('id')} — admin_level=7"],
                )
                imported += 1

            cursor.execute(
                """
                WITH candidates AS (
                    SELECT
                        c.id AS commune_id,
                        p.name AS province_name,
                        t.name AS city_name,
                        CASE WHEN ST_Covers(p.geom, ST_PointOnSurface(c.geom)) THEN 0 ELSE 1 END AS p_rank,
                        CASE WHEN ST_Covers(t.geom, ST_PointOnSurface(c.geom)) THEN 0 ELSE 1 END AS t_rank,
                        ST_Area(ST_Intersection(c.geom, p.geom)) AS p_overlap,
                        ST_Area(ST_Intersection(c.geom, t.geom)) AS t_overlap
                    FROM core_administrativearea c
                    LEFT JOIN core_administrativearea p
                      ON p.level='province' AND ST_Intersects(c.geom,p.geom)
                    LEFT JOIN core_administrativearea t
                      ON t.level='territory' AND ST_Intersects(c.geom,t.geom)
                    WHERE c.level='commune' AND c.source LIKE 'OpenStreetMap%'
                ),
                ranked AS (
                    SELECT *, ROW_NUMBER() OVER (
                        PARTITION BY commune_id
                        ORDER BY p_rank, t_rank,
                                 p_overlap DESC NULLS LAST,
                                 t_overlap DESC NULLS LAST,
                                 city_name
                    ) AS rn
                    FROM candidates
                )
                UPDATE core_administrativearea c
                   SET province_name=COALESCE(r.province_name,''),
                       city_name=COALESCE(r.city_name,''),
                       updated_at=NOW()
                  FROM ranked r
                 WHERE r.rn=1 AND r.commune_id=c.id
                """
            )
            attached = cursor.rowcount

            cursor.execute(
                """
                SELECT province_name, city_name, COUNT(*)
                  FROM core_administrativearea
                 WHERE level='commune' AND source LIKE 'OpenStreetMap%'
                 GROUP BY province_name, city_name
                 ORDER BY province_name, city_name
                """
            )
            coverage = cursor.fetchall()

        self.stdout.write(self.style.SUCCESS(
            f"Communes importées={imported}, explicites={explicit_count}, "
            f"déduites par frontière de ville={spatial_count}, ignorées={skipped}, "
            f"admin_level=7 non retenues={non_communes}, rattachées={attached}"
        ))
        self.stdout.write("Couverture ville/territoire → communes:")
        for province, city, count in coverage:
            self.stdout.write(f"  - {province or '[sans province]'} / {city or '[sans territoire]'}: {count}")
        self.stdout.write(self.style.WARNING(
            "QUALITÉ: admin_level=7 peut aussi représenter secteur, chefferie ou cité en RDC. "
            "Une unité est retenue si OSM la décrit explicitement comme commune/municipalité "
            "ou si sa frontière est située dans une ville admin_level=6. "
            "Cette couche sert à la recherche géographique FASTHOME et ne constitue pas un registre juridique exhaustif."
        ))
        self.stdout.write("Source: OpenStreetMap / Overpass; attribution OSM requise.")

    def _fetch_with_fallback(self, endpoints, query):
        last_error = None
        for endpoint in endpoints:
            endpoint = endpoint.strip()
            if not endpoint:
                continue
            self.stdout.write(f"Overpass: tentative {endpoint}")
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
                with urlopen(request, timeout=1000) as response:
                    payload = json.load(response)
                if not payload.get("elements"):
                    raise CommandError("Réponse Overpass vide.")
                self.stdout.write(self.style.SUCCESS(f"Overpass OK: {endpoint}"))
                return payload
            except (HTTPError, URLError, TimeoutError, ValueError, CommandError) as exc:
                last_error = exc
                self.stdout.write(self.style.WARNING(f"Échec Overpass: {exc}"))
                continue
            except Exception as exc:
                last_error = exc
                self.stdout.write(self.style.WARNING(f"Échec Overpass inattendu: {exc}"))
                continue
        raise CommandError(f"Tous les endpoints Overpass ont échoué: {last_error}")
