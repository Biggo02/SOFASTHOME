import json
from urllib.request import Request, urlopen

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction


class Command(BaseCommand):
    help = 'Importe un GeoJSON administratif dans la table PostGIS FASTHOME.'

    def add_arguments(self, parser):
        parser.add_argument('source', help='Chemin local ou URL du GeoJSON.')
        parser.add_argument('--level', default='commune', choices=['province', 'city', 'territory', 'commune'])
        parser.add_argument('--name-field', default='NAME_3', help='Champ contenant le nom de la zone.')
        parser.add_argument('--province-field', default='NAME_1', help='Champ province.')
        parser.add_argument('--city-field', default='NAME_2', help='Champ ville/territoire parent.')
        parser.add_argument('--source-name', default='GeoJSON administratif RDC')
        parser.add_argument('--clear-level', action='store_true', help='Supprime les zones du même niveau avant import.')

    def handle(self, *args, **options):
        if connection.vendor != 'postgresql':
            raise CommandError('PostGIS nécessite PostgreSQL. Configure DATABASE_URL avec une base PostgreSQL + PostGIS.')

        try:
            data = self._load(options['source'])
        except Exception as exc:
            raise CommandError(f'Impossible de lire le GeoJSON: {exc}') from exc

        if data.get('type') != 'FeatureCollection':
            raise CommandError('Le fichier doit être un GeoJSON FeatureCollection.')

        level = options['level']
        name_field = options['name_field']
        province_field = options['province_field']
        city_field = options['city_field']
        imported = 0
        skipped = 0

        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute('CREATE EXTENSION IF NOT EXISTS postgis')
            if options['clear_level']:
                cursor.execute('DELETE FROM core_administrativearea WHERE level = %s', [level])

            for feature in data.get('features', []):
                geometry = feature.get('geometry')
                props = feature.get('properties') or {}
                name = str(props.get(name_field) or '').strip()
                if not name or not geometry:
                    skipped += 1
                    continue
                province = str(props.get(province_field) or '').strip()
                city = str(props.get(city_field) or '').strip()
                geom_json = json.dumps(geometry, separators=(',', ':'))
                cursor.execute("""
                    INSERT INTO core_administrativearea
                        (level, name, province_name, city_name, geom, source, updated_at)
                    VALUES
                        (%s, %s, %s, %s,
                         ST_Multi(ST_CollectionExtract(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), 3)),
                         %s, NOW())
                    ON CONFLICT (level, name, province_name, city_name)
                    DO UPDATE SET geom = EXCLUDED.geom, source = EXCLUDED.source, updated_at = NOW()
                """, [level, name, province, city, geom_json, options['source_name']])
                imported += 1

        self.stdout.write(self.style.SUCCESS(f'{imported} zones importées ({level}), {skipped} ignorées.'))

    @staticmethod
    def _load(source):
        if source.startswith(('http://', 'https://')):
            request = Request(source, headers={'User-Agent': 'FASTHOME/1.0'})
            with urlopen(request, timeout=60) as response:
                return json.load(response)
        with open(source, 'r', encoding='utf-8') as handle:
            return json.load(handle)
