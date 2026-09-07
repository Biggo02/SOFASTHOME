from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0017_rentalcase_financial_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('postnom', models.CharField(blank=True, max_length=100)),
                ('profession', models.CharField(blank=True, choices=[
                    ('agent_immobilier', 'Agent immobilier'),
                    ('agriculteur', 'Agriculteur'),
                    ('artisan', 'Artisan'),
                    ('commercant', 'Commerçant'),
                    ('enseignant', 'Enseignant'),
                    ('fonctionnaire', 'Fonctionnaire'),
                    ('medecin', 'Médecin / professionnel de santé'),
                    ('ingenieur', 'Ingénieur'),
                    ('juriste', 'Juriste / avocat'),
                    ('comptable', 'Comptable / financier'),
                    ('entrepreneur', 'Entrepreneur'),
                    ('etudiant', 'Étudiant'),
                    ('sans_emploi', 'Sans emploi'),
                    ('retraite', 'Retraité'),
                    ('autre', 'Autre'),
                ], max_length=40)),
                ('date_of_birth', models.DateField(blank=True, null=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='profile', to='auth.user')),
            ],
        ),
    ]
