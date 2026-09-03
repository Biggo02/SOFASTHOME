from django.db import migrations


def remove_legacy_administrative_area(apps, schema_editor):
    """Remove the obsolete geographic table using backend-compatible SQL."""
    table_name = "core_administrativearea"
    existing_tables = schema_editor.connection.introspection.table_names()

    if table_name not in existing_tables:
        return

    quoted_table = schema_editor.quote_name(table_name)
    if schema_editor.connection.vendor == "sqlite":
        schema_editor.execute(f"DROP TABLE IF EXISTS {quoted_table}")
    else:
        schema_editor.execute(f"DROP TABLE IF EXISTS {quoted_table} CASCADE")


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0006_property_room_details'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='property',
            name='neighborhood',
        ),
        migrations.RemoveField(
            model_name='property',
            name='latitude',
        ),
        migrations.RemoveField(
            model_name='property',
            name='longitude',
        ),
        migrations.RunPython(
            remove_legacy_administrative_area,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
