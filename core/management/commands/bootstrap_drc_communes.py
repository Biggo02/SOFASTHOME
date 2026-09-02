import json
from urllib.request import Request, urlopen

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

OVERPASS_DEFAULT = "https://overpass-api.de/api/interpreter"


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
        coords = [(p.get("lon"), p.get("lat")) for p in (member.get("geometry") or [])]
        coords = [(x, y) for x, y in coords if x is not None and y is not None]
        if len(coords) < 2:
            continue
        try:
            line = LineString(coords)
        except Exception:
            continue
        (inner if member.get("role") == "inner" else outer).append(line)

    if not outer:
        return None
    polygons = list(polygonize(unary_union(outer)))
    holes = list(polygonize(unary_union(inner))) if inner else []
    result = []
    for polygon in polygons:
        polygon_holes = [list(h.exterior.coords) for h in holes if polygon.covers(h.representative_point())]
        candidate = Polygon(polygon.exterior.coords, polygon_holes)
        if not candidate.is_empty and candidate.area > 0:
            result.append(candidate)
    if not result:
        return None
    geometry = MultiPolygon(result) if len(result) > 1 else result[0]
    return geometry.__geo_interface__


def explicitly_commune(tags):
    text = " ".join(
        clean(tags.get(key)) for key in ("designation", "official_status", "government", "place")
    ).lower()
    return "commune" in text or "municipalit" in text or "municipality" in text


class Command(BaseCommand):
    help = "Importe les communes urbaines RDC depuis OpenStreetMap et les rattache aux provinces et territoires/villes PostGIS."

    def add_arguments(self, parser):
        parser.add_argument("--overpass-url", default=OVERPASS_DEFAULT)
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
        data = self._fetch_json(options["overpass_url"], query)
        relations = [e for e in data.get("elements", []) if e.get("type") == "relation"]
        cities = [r for r in relations if (r.get("tags") or {}).get("admin_level") == "6"]
        level7 = [r for r in relations if (r.get("tags") or {}).get("admin_level") == "7"]
        if not level7:
            raise CommandError("Overpass n'a retourné aucune relation admin_level=7 pour la RDC.")

        try:
            from shapely.geometry import Point, shape
        except ImportError as exc:
            raise CommandError("Shapely est requis. Lancez: pip install -r requirements.txt") from exc

        city_shapes = []
        for city in cities:
            geometry = build_geometry(city)
            if geometry:
                city_shapes.append((clean((city.get("tags") or {}).get("name")), shape(geometry)))

        self.stdout.write(f"OSM: {len(cities)} villes admin_level=6 et {len(level7)} unités admin_level=7 reçues.")
        imported = skipped = non_communes = 0

        with transaction.atomic(), connection.cursor() as cursor:
            if options["clear"]:
                cursor.execute("DELETE FROM core_administrativearea WHERE level='commune' AND source LIKE 'OpenStreetMap%'")

            for relation in level7:
                tags = relation.get("tags") or {}
                name = clean(tags.get("name") or tags.get("official_name"))
                geometry = build_geometry(relation)
                if not name or not geometry:
                    skipped += 1
                    continue

                urban = explicitly_commune(tags)
                if not urban:
                    point = shape(geometry).representative_point()
                    urban = any(city_shape.covers(point) for _, city_shape in city_shapes)
                if not urban:
                    non_communes += 1
                    continue

                geom_json = json.dumps(geometry, separators=(",", ":"))
                cursor.execute(
                    """
                    INSERT INTO core_administrativearea
                        (level, name, province_name, city_name, geom, source, updated_at)
                    VALUES
                        ('commune', %s, '', '',
                         ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326)),3)),
                         %s, NOW())
                    ON CONFLICT (level,name,province_name,city_name)
                    DO UPDATE SET geom=EXCLUDED.geom, source=EXCLUDED.source, updated_at=NOW()
                    """,
                    [name, geom_json, f"OpenStreetMap relation {relation.get('id')} — admin_level=7"],
                )
                imported += 1

            cursor.execute(
                """
                WITH parents AS (
                    SELECT
                        c.id AS commune_id,
                        p.name AS province_name,
                        t.name AS city_name,
                        ROW_NUMBER() OVER (
                            PARTITION BY c.id
                            ORDER BY
                              CASE WHEN ST_Covers(p.geom, ST_PointOnSurface(c.geom)) THEN 0 ELSE 1 END,
                              ST_Area(ST_Intersection(c.geom,p.geom)) DESC NULLS LAST,
                              t.name
                        ) AS rn
                    FROM core_administrativearea c
                    LEFT JOIN core_administrativearea p
                      ON p.level='province' AND ST_Intersects(c.geom,p.geom)
                    LEFT JOIN core_administrativearea t
                      ON t.level='territory' AND ST_Intersects(c.geom,t.geom)
                    WHERE c.level='commune' AND c.source LIKE 'OpenStreetMap%'
                )
                UPDATE core_administrativearea c
                   SET province_name=COALESCE(parents.province_name,''),
                       city_name=COALESCE(parents.city_name,''),
                       updated_at=NOW()
                  FROM parents
                 WHERE parents.rn=1 AND parents.commune_id=c.id
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
            f"Communes importées={imported}, ignorées={skipped}, admin_level=7 non urbaines/non communes={non_communes}, rattachées={attached}"
        ))
        self.stdout.write("Couverture ville/territoire → communes:")
        for province, city, count in coverage:
            self.stdout.write(f"  - {province or '[sans province]'} / {city or '[sans territoire]'}: {count}")
        self.stdout.write(self.style.WARNING(
            "Contrôle qualité: en RDC, admin_level=7 peut aussi représenter secteur, chefferie ou cité; seules les unités explicitement communales ou situées dans une frontière de ville admin_level=6 sont importées comme 'commune'."
        ))
        self.stdout.write("Source: OpenStreetMap / Overpass; attribution OSM requise.")

    @staticmethod
    def _fetch_json(url, query):
        request = Request(
            url,
            data=query.encode("utf-8"),
            method="POST",
            headers={
                "User-Agent": "FASTHOME/1.0 (DRC commune boundary importer)",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            },
        )
        try:
            with urlopen(request, timeout=1000) as response:
                return json.load(response)
        except Exception as exc:
            raise CommandError(f"Erreur Overpass: {exc}") from exc
