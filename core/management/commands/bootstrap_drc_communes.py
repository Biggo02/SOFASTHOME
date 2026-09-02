"""Compatibilité: valide le référentiel géographique FASTHOME depuis le document fourni."""

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

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

ALIASES = {"annexe": "Annexes", "selembao": "Ona (Selembao)", "ona selembao": "Ona (Selembao)"}


def clean(value):
    return " ".join(str(value or "").strip().split())


def norm(value):
    return clean(value).casefold()


class Command(BaseCommand):
    help = "Installe le référentiel géographique FASTHOME fourni, sans OSM ni source externe."

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true", help="Supprime d'abord les entrées de communes du référentiel FASTHOME.")
        parser.add_argument("--province", default="", help="Kinshasa, Haut-Katanga ou Lualaba.")

    def handle(self, *args, **options):
        requested = clean(options.get("province"))
        provinces = list(STRUCTURE)
        if requested:
            matched = next((p for p in provinces if norm(p) == norm(requested)), None)
            if not matched:
                raise CommandError("Province autorisée: Kinshasa, Haut-Katanga ou Lualaba.")
            provinces = [matched]

        table = "core_administrativearea"
        with connection.cursor() as cursor:
            # Ce point d'entrée n'effectue plus aucun accès OSM, Overpass ou geoBoundaries.
            cursor.execute("SELECT to_regclass(%s)", [table])
            exists = cursor.fetchone()[0]

        if exists is None:
            raise CommandError(
                "La table géographique historique n'existe plus. "
                "Le référentiel doit maintenant être utilisé par les champs province/ville/commune du modèle Property."
            )

        total = 0
        with transaction.atomic(), connection.cursor() as cursor:
            if options.get("clear"):
                cursor.execute("DELETE FROM core_administrativearea WHERE level='commune' AND source='FASTHOME — document fourni'")

            for province in provinces:
                for city, communes in STRUCTURE[province].items():
                    for commune in communes:
                        cursor.execute(
                            """
                            INSERT INTO core_administrativearea
                                (level, name, province_name, city_name, geom, source, updated_at)
                            VALUES
                                ('commune', %s, %s, %s,
                                 ST_Multi(ST_GeomFromText('MULTIPOLYGON EMPTY', 4326)),
                                 'FASTHOME — document fourni', NOW())
                            ON CONFLICT (level, name, province_name, city_name)
                            DO UPDATE SET source=EXCLUDED.source, updated_at=NOW()
                            """,
                            [commune, province, city],
                        )
                        total += 1

        self.stdout.write(self.style.SUCCESS(
            f"Référentiel FASTHOME chargé depuis le document fourni: {total} communes."
        ))
        self.stdout.write("Aucune requête OSM/Overpass/geoBoundaries n'est utilisée.")
