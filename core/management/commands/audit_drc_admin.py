from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import connection


KNOWN_LUBUMBASHI_COMMUNES = {
    "annexe",
    "kamalondo",
    "kampemba",
    "katuba",
    "kenya",
    "lubumbashi",
    "ruashi",
}


class Command(BaseCommand):
    help = "Audite la couverture géographique RDC importée dans PostGIS sans modifier les données."

    def add_arguments(self, parser):
        parser.add_argument(
            "--verbose-coverage",
            action="store_true",
            help="Affiche aussi les territoires/villes sans commune.",
        )

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            self.stderr.write(self.style.ERROR("PostgreSQL + PostGIS sont nécessaires."))
            return

        with connection.cursor() as cursor:
            cursor.execute("SELECT PostGIS_Version()")
            postgis = cursor.fetchone()[0]

            cursor.execute(
                "SELECT level, COUNT(*) FROM core_administrativearea "
                "GROUP BY level ORDER BY level"
            )
            levels = dict(cursor.fetchall())

            cursor.execute(
                """
                SELECT id, name, province_name, city_name
                FROM core_administrativearea
                WHERE level='commune'
                  AND (province_name='' OR city_name='')
                ORDER BY province_name, city_name, name
                """
            )
            orphaned = cursor.fetchall()

            cursor.execute(
                """
                SELECT province_name, city_name, COUNT(*)
                FROM core_administrativearea
                WHERE level='commune'
                GROUP BY province_name, city_name
                ORDER BY province_name, city_name
                """
            )
            coverage = cursor.fetchall()

            cursor.execute(
                """
                SELECT c.name, c.province_name, c.city_name
                FROM core_administrativearea c
                WHERE c.level='commune'
                  AND lower(trim(c.city_name))='lubumbashi'
                ORDER BY c.name
                """
            )
            lubumbashi = cursor.fetchall()

            cursor.execute(
                """
                SELECT c.province_name, c.city_name, lower(trim(c.name)) AS commune, COUNT(*)
                FROM core_administrativearea c
                WHERE c.level='commune'
                GROUP BY c.province_name, c.city_name, lower(trim(c.name))
                HAVING COUNT(*) > 1
                ORDER BY c.province_name, c.city_name, commune
                """
            )
            duplicates = cursor.fetchall()

            cursor.execute(
                """
                SELECT p.name
                FROM core_administrativearea p
                LEFT JOIN (
                    SELECT DISTINCT province_name
                    FROM core_administrativearea
                    WHERE level='commune' AND province_name <> ''
                ) c ON lower(trim(c.province_name))=lower(trim(p.name))
                WHERE p.level='province' AND c.province_name IS NULL
                ORDER BY p.name
                """
            )
            provinces_without_communes = [row[0] for row in cursor.fetchall()]

            cursor.execute(
                """
                SELECT t.province_name, t.name
                FROM core_administrativearea t
                LEFT JOIN core_administrativearea c
                  ON c.level='commune'
                 AND lower(trim(c.province_name))=lower(trim(t.province_name))
                 AND lower(trim(c.city_name))=lower(trim(t.name))
                WHERE t.level='territory'
                GROUP BY t.province_name, t.name
                HAVING COUNT(c.id)=0
                ORDER BY t.province_name, t.name
                """
            )
            territories_without_communes = cursor.fetchall()

        self.stdout.write(self.style.NOTICE(f"PostGIS: {postgis}"))
        self.stdout.write("\n=== COMPTAGE DES NIVEAUX ===")
        for level, count in levels.items():
            self.stdout.write(f"{level}: {count}")

        self.stdout.write("\n=== CONTRÔLE DES COMMUNES ===")
        self.stdout.write(f"Communes totales: {levels.get('commune', 0)}")
        self.stdout.write(f"Communes sans province ou ville/territoire: {len(orphaned)}")
        self.stdout.write(f"Doublons nom + parent: {len(duplicates)}")

        if orphaned:
            self.stdout.write(self.style.WARNING("Communes non rattachées:"))
            for _, name, province, city in orphaned:
                self.stdout.write(f"  - {name} | province={province or '[vide]'} | parent={city or '[vide]'}")
        else:
            self.stdout.write(self.style.SUCCESS("✓ Toutes les communes ont une province et un parent."))

        if duplicates:
            self.stdout.write(self.style.WARNING("Doublons détectés:"))
            for province, city, commune, count in duplicates:
                self.stdout.write(f"  - {province} / {city} / {commune}: {count}")

        self.stdout.write("\n=== LUBUMBASHI ===")
        actual = {_normalize(row[0]) for row in lubumbashi}
        self.stdout.write(f"Communes actuellement rattachées: {len(lubumbashi)}")
        for name, province, city in lubumbashi:
            self.stdout.write(f"  - {name} ({province} / {city})")
        missing = sorted(KNOWN_LUBUMBASHI_COMMUNES - actual)
        if missing:
            self.stdout.write(self.style.WARNING(
                "Communes de Lubumbashi attendues mais absentes de la base: " + ", ".join(missing)
            ))
        else:
            self.stdout.write(self.style.SUCCESS("✓ Les 7 communes administratives connues de Lubumbashi sont présentes."))

        self.stdout.write("\n=== PROVINCES ===")
        self.stdout.write(f"Provinces sans aucune commune importée: {len(provinces_without_communes)}")
        if provinces_without_communes:
            for name in provinces_without_communes:
                self.stdout.write(f"  - {name}")

        self.stdout.write("\n=== VILLES / TERRITOIRES ===")
        self.stdout.write(f"ADM2 sans aucune commune importée: {len(territories_without_communes)}")
        if options["verbose_coverage"]:
            for province, city in territories_without_communes:
                self.stdout.write(f"  - {province} / {city}")

        self.stdout.write("\n=== COUVERTURE ACTUELLE ===")
        for province, city, count in coverage:
            self.stdout.write(f"  - {province or '[sans province]'} / {city or '[sans parent]'}: {count}")

        self.stdout.write("\nAudit terminé: aucune donnée n'a été modifiée.")


def _normalize(value):
    import unicodedata
    value = str(value or '').strip().casefold()
    value = unicodedata.normalize('NFKD', value)
    return ''.join(c for c in value if not unicodedata.combining(c))
