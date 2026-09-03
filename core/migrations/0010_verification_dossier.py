from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('core', '0009_alter_payment_status_alter_verificationdocument_kind_and_more')]

    operations = [
        migrations.CreateModel(
            name='VerificationDossier',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('id_front', models.FileField(blank=True, upload_to='verification/%Y/%m/')),
                ('id_back', models.FileField(blank=True, upload_to='verification/%Y/%m/')),
                ('selfie', models.FileField(blank=True, upload_to='verification/%Y/%m/')),
                ('status', models.CharField(choices=[('pending','En attente'),('review','En cours de vérification'),('approved','Vérification validée'),('rejected','Vérification refusée'),('needs_info','Informations supplémentaires requises')], default='pending', max_length=20)),
                ('note', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='verification_dossier', to='auth.user')),
            ],
        ),
    ]
