from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0005_property_max_occupants')]

    operations = [
        migrations.AddField(
            model_name='property',
            name='room_details',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
