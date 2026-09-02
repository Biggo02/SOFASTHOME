from django.db import migrations


def create_spatial_table(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("CREATE EXTENSION IF NOT EXISTS postgis")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS core_administrativearea (
                id BIGSERIAL PRIMARY KEY,
                level VARCHAR(30) NOT NULL,
                name VARCHAR(160) NOT NULL,
                province_name VARCHAR(160) NOT NULL DEFAULT '',
                city_name VARCHAR(160) NOT NULL DEFAULT '',
                geom geometry(MultiPolygon, 4326) NOT NULL,
                source VARCHAR(120) NOT NULL DEFAULT '',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(level, name, province_name, city_name)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS core_adminarea_geom_gist ON core_administrativearea USING GIST (geom)")
        cursor.execute("CREATE INDEX IF NOT EXISTS core_adminarea_name_idx ON core_administrativearea (lower(name))")
        cursor.execute("CREATE INDEX IF NOT EXISTS core_adminarea_parent_idx ON core_administrativearea (lower(province_name), lower(city_name))")


def drop_spatial_table(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        with schema_editor.connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS core_administrativearea")


class Migration(migrations.Migration):
    dependencies = [('core', '0006_property_room_details')]
    operations = [migrations.RunPython(create_spatial_table, drop_spatial_table)]
