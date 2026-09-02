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

# Référentiel fourni pour FASTHOME: liaisons parent-enfant à respecter.
STRUCTURE = {
    "Kinshasa": {
        "Kinshasa": [
            "Bandalungwa", "Barumbu", "Bumbu", "Gombe", "Kalamu", "Kasa-Vubu",
            "Kimbanseke", "Kinshasa", "Kintambo", "Kisenso", "Lemba", "Limete",
            "Lingwala", "Makala", "Maluku", "Masina", "Matete", "Ngaba", "Ngaliema",
            "Ngiri-Ngiri", "Nsele", "Mont-Ngafula", "Ona (Selembao)", "Ndjili",
        ],
    },
    "Haut-Katanga": {
        "Lubumbashi": ["Kamalondo", "Kampemba", "Katuba", "Kenya", "Lubumbashi", "Ruashi", "Annexes"],
        "Likasi": ["Kikula", "Likasi", "Panda", "Shituru"],
        "Kasumbalesa": ["Musoshi", "Kasumbalesa"],
    },
    "Lualaba": {
        "Kolwezi": ["Dilala", "Manika"],
        "Kasaji": ["Lua", "Monde", "Kasaji"],
        "Lubudi": ["Lubudi", "Fungurume"],
    },
}

ALIASES = {
    "annexe": "Annexes",
    "annexes": "Annexes",
    "selembao": "Ona (Selembao)",
    "ona selembao": "Ona (Selembao)",
    "mont ngafula": "Mont-Ngafula",
}


def clean(value):
    return " ".join(str(value or "").strip().split())


def normalize_name(value):
    value = clean(value).casefold()
    value = re.sub(r"[^a-z0-9àâäçéèêëîïôöùûüÿñœæ -]", " ", value)
    return " ".join(value.split())


def canonical_name(value):
    normalized = normalize_name(value)
    return ALIASES.get(normalized, clean(value))


def build_geometry(relation, ways_by_id):
    try:
        from shapely.geometry import LineString, MultiPolygon, Polygon
        from shapely.ops import polygonize, unary_union
    except ImportError as exc:
        raise CommandError("Shapely est requis. Lancez: pip install -r requirements.txt") from exc

    outer, inner = [], []
    for member in relation.get("members", []):
        if member.get("type") != "way":
            continue
        points = member.get("geometry") or []
        if not points:
            points = (ways_by_id.get(member.get("ref")) or {}).get("geometry") or []
        coords = [
            (p.get("lon"), p.get("lat"))
            for p in points
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


class Command(BaseCommand):
    help = "Importe le référentiel géographique FASTHOME fourni: Kinshasa, Haut-Katanga et Lualaba."

    def add_arguments(self, parser):
        parser.add_argument("--overpass-url", default="", help="Endpoint Overpass personnalisé.")
        parser.add_argument("--clear", action="store_true", help="Supprime les communes OSM des provinces traitées avant import.")
        parser.add_argument("--province", default="", help="Une seule province: Kinshasa, Haut-Katanga ou Lualaba.")

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            raise CommandError("PostgreSQL + PostGIS sont nécessaires.")

        with connection.cursor() as cursor:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS postgis")
            cursor.execute("SELECT PostGIS_Version()")
            self.stdout.write(self.style.NOTICE(f"PostGIS {cursor.fetchone()[0]} détecté."))

        provinces = list(STRUCTURE)
        requested = clean(options.get("province"))
        if requested:
            matches = [p for p in provinces if normalize_name(p) == normalize_name(requested)]
            if not matches:
                raise CommandError(
                    f"Province '{requested}' hors périmètre FASTHOME. "
                    f"Provinces autorisées: {', '.join(provinces)}."
                )
            provinces = matches

        db_names = self._db_provinces(provinces)
        missing = [p for p in provinces if p not in db_names]
        if missing:
            raise CommandError("Provinces absentes de la base: " + ", ".join(missing) + ". Lancez bootstrap_drc_boundaries.")

        endpoints = [options["overpass_url"]] if options["overpass_url"] else OVERPASS_ENDPOINTS
        if options["clear"]:
            placeholders = ",".join(["%s"] * len(provinces))
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM core_administrativearea WHERE level='commune' "
                    "AND source LIKE 'OpenStreetMap%%' AND province_name IN (" + placeholders + ")",
                    provinces,
                )
            self.stdout.write(self.style.WARNING("Communes OSM supprimées pour: " + ", ".join(provinces)))

        totals = {"imported": 0, "missing": 0, "unlisted": 0}
        for index, province in enumerate(provinces, 1):
            self.stdout.write(f"\n[{index}/{len(provinces)}] {province}")
            try:
                relation_id = self._find_province_relation_id(endpoints, province)
                self.stdout.write(f"  Relation OSM admin_level=4: {relation_id}")
                query = self._province_children_query(relation_id)
                data = self._fetch_with_fallback(endpoints, query, province)
                imported, missing_count, unlisted = self._import_province(province, data)
                totals["imported"] += imported
                totals["missing"] += missing_count
                totals["unlisted"] += unlisted
            except CommandError as exc:
                self.stdout.write(self.style.ERROR(f"  Province non traitée: {exc}"))

        self.stdout.write("\n" + self.style.SUCCESS("=== RÉFÉRENTIEL FASTHOME TERMINÉ ==="))
        self.stdout.write(f"Communes importées/mises à jour: {totals['imported']}")
        self.stdout.write(f"Communes du document non retrouvées dans OSM: {totals['missing']}")
        self.stdout.write(f"Relations OSM hors référentiel ignorées: {totals['unlisted']}")

    def _db_provinces(self, names):
        wanted = {normalize_name(n): n for n in names}
        with connection.cursor() as cursor:
            cursor.execute("SELECT name FROM core_administrativearea WHERE level='province'")
            rows = cursor.fetchall()
        return {
            wanted[normalize_name(name)]: name
            for (name,) in rows
            if normalize_name(name) in wanted
        }

    def _find_province_relation_id(self, endpoints, province):
        query = f"""
        [out:json][timeout:45];
        relation["boundary"="administrative"]["admin_level"="4"]["name"={json.dumps(province)}];
        out tags;
        """
        data = self._fetch_with_fallback(endpoints, query, f"OSM {province}")
        wanted = normalize_name(province)
        for relation in data.get("elements", []):
            tags = relation.get("tags") or {}
            if normalize_name(tags.get("name")) == wanted or normalize_name(tags.get("name:fr")) == wanted:
                return int(relation["id"])
        raise CommandError(f"Relation OSM introuvable pour {province}.")

    def _province_children_query(self, relation_id):
        # On récupère toutes les relations admin_level=7 de la province et les
        # ways membres séparément. Cela évite les réponses relationnelles sans
        # géométrie qui produisaient auparavant 'ignorées=9'.
        return f"""
        [out:json][timeout:180];
        relation({int(relation_id)})->.province;
        .province map_to_area -> .province_area;
        relation(area.province_area)["boundary"="administrative"]["admin_level"="7"]->.children;
        (
          .children;
          way(r.children);
        );
        out body geom;
        """

    def _import_province(self, province, data):
        ways = {
            int(e["id"]): e
            for e in data.get("elements", [])
            if e.get("type") == "way" and e.get("id") is not None
        }
        relations = [e for e in data.get("elements", []) if e.get("type") == "relation"]

        allowed = {}
        for parent, children in STRUCTURE[province].items():
            for child in children:
                allowed[normalize_name(child)] = (child, parent)
                allowed[normalize_name(canonical_name(child))] = (child, parent)

        found = set()
        candidates = {}
        unlisted = 0
        for relation in relations:
            tags = relation.get("tags") or {}
            raw = clean(tags.get("name") or tags.get("official_name"))
            key = normalize_name(raw)
            if key not in allowed:
                unlisted += 1
                continue
            canonical, parent = allowed[key]
            geometry = build_geometry(relation, ways)
            if not geometry:
                continue
            found.add(canonical)
            candidates[canonical] = (parent, geometry, relation.get("id"))

        with transaction.atomic(), connection.cursor() as cursor:
            for canonical, (parent, geometry, relation_id) in candidates.items():
                cursor.execute(
                    """
                    INSERT INTO core_administrativearea
                        (level,name,province_name,city_name,geom,source,updated_at)
                    VALUES
                        ('commune',%s,%s,%s,
                         ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326)),3)),
                         %s,NOW())
                    ON CONFLICT (level,name,province_name,city_name)
                    DO UPDATE SET geom=EXCLUDED.geom,source=EXCLUDED.source,updated_at=NOW()
                    """,
                    (
                        canonical,
                        province,
                        parent,
                        json.dumps(geometry, separators=(",", ":")),
                        f"OpenStreetMap relation {relation_id} — référentiel FASTHOME fourni",
                    ),
                )

        expected = {child for children in STRUCTURE[province].values() for child in children}
        missing = expected - found
        self.stdout.write(self.style.SUCCESS(
            f"  Relations admin7={len(relations)}, communes du référentiel trouvées={len(found)}, "
            f"géométries importées={len(candidates)}, manquantes={len(missing)}"
        ))
        if missing:
            self.stdout.write(self.style.WARNING("  Non trouvées dans OSM: " + ", ".join(sorted(missing))))
        return len(candidates), len(missing), unlisted

    def _fetch_with_fallback(self, endpoints, query, label):
        last_error = None
        for endpoint in endpoints:
            for attempt in range(1, RETRIES_PER_ENDPOINT + 1):
                try:
                    self.stdout.write(self.style.NOTICE(
                        f"  Overpass {endpoint.split('//')[-1].split('/')[0]} tentative {attempt}..."
                    ))
                    request = Request(
                        endpoint,
                        data=query.encode("utf-8"),
                        headers={
                            "Content-Type": "application/x-www-form-urlencoded",
                            "User-Agent": "FASTHOME/1.0",
                        },
                        method="POST",
                    )
                    with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                        return json.loads(response.read().decode("utf-8"))
                except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
                    last_error = exc
                    self.stdout.write(self.style.WARNING(f"    Échec: {exc}"))
                    if attempt < RETRIES_PER_ENDPOINT:
                        time.sleep(2)
        raise CommandError(f"Overpass indisponible pour {label}: {last_error}")
