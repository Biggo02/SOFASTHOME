from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0007_remove_geographic_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='property',
            name='status',
            field=models.CharField(
                choices=[
                    ('draft', 'Brouillon'),
                    ('review', 'En vérification'),
                    ('published', 'Publiée'),
                    ('rented', 'Louée'),
                    ('archived', 'Archivée'),
                    ('rejected', 'Refusée'),
                ],
                default='draft',
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name='property',
            name='water_source',
            field=models.CharField(
                blank=True,
                choices=[
                    ('regideso', 'REGIDESO'),
                    ('forage', 'Forage'),
                    ('puits', 'Puits'),
                    ('citerne', 'Citerne'),
                    ('source', 'Source naturelle'),
                    ('other', 'Autre'),
                ],
                max_length=30,
            ),
        ),
        migrations.AlterField(
            model_name='property',
            name='electricity_source',
            field=models.CharField(
                blank=True,
                choices=[
                    ('snél', 'SNEL'),
                    ('solaire', 'Solaire'),
                    ('generateur', 'Générateur'),
                    ('batterie', 'Batterie / onduleur'),
                    ('other', 'Autre'),
                ],
                max_length=30,
            ),
        ),
        migrations.AlterField(
            model_name='property',
            name='floor_type',
            field=models.CharField(
                blank=True,
                choices=[
                    ('carrelage', 'Carrelage'),
                    ('ciment', 'Ciment'),
                    ('parquet', 'Parquet'),
                    ('vinyle', 'Vinyle'),
                    ('terre', 'Terre battue'),
                    ('other', 'Autre'),
                ],
                max_length=30,
            ),
        ),
        migrations.AlterField(
            model_name='property',
            name='ceiling_type',
            field=models.CharField(
                blank=True,
                choices=[
                    ('dalle', 'Dalle béton'),
                    ('plafond', 'Plafond classique'),
                    ('staff', 'Staff'),
                    ('lambris', 'Lambris'),
                    ('tôle', 'Tôle'),
                    ('other', 'Autre'),
                ],
                max_length=30,
            ),
        ),
    ]
