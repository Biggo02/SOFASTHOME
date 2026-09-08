from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0020_alter_userprofile_postnom_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='property',
            name='property_type',
            field=models.CharField(
                choices=[
                    ('Appartement', 'Appartement'),
                    ('Maison', 'Maison'),
                    ('Studio', 'Studio'),
                    ('Villa', 'Villa'),
                    ('Duplex', 'Duplex'),
                    ('Triplex', 'Triplex'),
                    ('Bungalow', 'Bungalow'),
                    ('Penthouse', 'Penthouse'),
                    ('Chambre', 'Chambre'),
                    ('Local commercial', 'Local commercial'),
                    ('Autre', 'Autre'),
                ],
                max_length=30,
            ),
        ),
        migrations.AddField(model_name='property', name='neighborhood', field=models.CharField(blank=True, max_length=100)),
        migrations.AddField(model_name='property', name='avenue', field=models.CharField(blank=True, max_length=150)),
        migrations.AddField(model_name='property', name='number', field=models.CharField(blank=True, max_length=40)),
        migrations.AddField(model_name='property', name='geolocation_link', field=models.URLField(blank=True, max_length=500)),
        migrations.AddField(model_name='property', name='owner_authorized_publication', field=models.BooleanField(default=False)),
        migrations.AddField(model_name='property', name='owner_authorized_subletting', field=models.BooleanField(default=False)),
        migrations.AddField(model_name='property', name='authorization_confirmed_at', field=models.DateTimeField(blank=True, null=True)),
    ]
