import json
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction


COMMUNES = [
    'Annexe', 'Kamalondo', 'Kampemba', 'Katuba', 'Kenya', 'Lubumbashi', 'Ruashi'
]


class Command(BaseCommand):
    help = 'Charge les limites OSM des 7 communes de Lubumbashi dans PostGIS.'

    def add_arguments(self, parser):
        parser.add_argument('--delay', type=float, default=1.1, help='Pause entre les requêtes Nominatim.')

    def handle(self, *args, **options):
        if connection.vendor != 'postgresql':
            raise CommandError('PostGIS nécessite PostgreSQL.')
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT PostGIS_Version()")
        except Exception as exc:
            raise CommandError('PostGIS n’est pas activé dans la base PostgreSQL.') from exc

        imported = 0
        with transaction.atomic(), connection.cursor() as cursor:
            for index, commune in enumerate(COMMUNES):
                if index:
                    time.sleep(max(0, options['delay']))
                data = self._search(commune)
                if not data:
                    self.stderr.write(self.style.WARNING(f'Limite introuvable: {commune}'))
                    continue
                geometry = data.get('geojson')
                if not geometry or geometry.get('type') not in ('Polygon', 'MultiPolygon'):
                    self.stderr.write(self.style.WARNING(f'Géométrie invalide: {commune}'))
                    continue
                cursor.execute("""
                    INSERT INTO core_administrativearea
                        (level, name, province_name, city_name, geom, source, updated_at)
                    VALUES
                        ('commune', %s, 'Haut-Katanga', 'Lubumbashi',
                         ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)),
                         'OpenStreetMap / Nominatim', NOW())
                    ON CONFLICT (level, name, province_name, city_name)
                    DO UPDATE SET geom = EXCLUDED.geom, source = EXCLUDED.source, updated_at = NOW()
                """, [commune, json.dumps(geometry, separators=(',', ':'))])
                imported += 1
                self.stdout.write(f'✓ {commune}')

        self.stdout.write(self.style.SUCCESS(f'{imported}/{len(COMMUNES)} communes de Lubumbashi importées.'))

    @staticmethod
    def _search(commune):
        query = urlencode({
            'q': f'{commune}, Lubumbashi, Haut-Katanga, République démocratique du Congo',
            'format': 'jsonv2',
            'limit': 5,
            'polygon_geojson': 1,
        })
        request = Request(
            f'https://nominatim.openstreetmap.org/search?{query}',
            headers={'User-Agent': 'FASTHOME/1.0 (real-estate search)'}
        )
        with urlopen(request, timeout=60) as response:
            results = json.load(response)
        for item in results:
            geojson = item.get('geojson')
            if geojson and geojson.get('type') in ('Polygon', 'MultiPolygon'):
                return item
        return None
