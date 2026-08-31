from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies=[('core','0004_property_dynamic_details')]
    operations=[
        migrations.AddField(
            model_name='property',
            name='max_occupants',
            field=models.PositiveIntegerField(default=1),
        ),
    ]
