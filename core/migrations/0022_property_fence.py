from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0021_property_publication_details'),
    ]

    operations = [
        migrations.AddField(
            model_name='property',
            name='fence',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='property',
            name='fence_type',
            field=models.CharField(blank=True, choices=[('mur', 'Mur'), ('grillage', 'Grillage'), ('metal', 'Métallique'), ('beton', 'Béton'), ('bois', 'Bois'), ('mixte', 'Mixte'), ('other', 'Autre')], max_length=30),
        ),
        migrations.AddField(
            model_name='property',
            name='fence_condition',
            field=models.CharField(blank=True, max_length=30),
        ),
    ]
