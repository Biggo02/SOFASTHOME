from django.db import migrations


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
    ]
