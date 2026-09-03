from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('core', '0012_visit_final_decision')]

    operations = [
        migrations.CreateModel(
            name='RentalContract',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reference', models.CharField(blank=True, max_length=40, unique=True)),
                ('contract_type', models.CharField(choices=[('owner_agreement', 'FASTHOME ↔ Propriétaire'), ('tenant_sublease', 'FASTHOME ↔ Locataire')], max_length=30)),
                ('amount', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('deposit', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('start_date', models.DateField(blank=True, null=True)),
                ('end_date', models.DateField(blank=True, null=True)),
                ('status', models.CharField(choices=[('draft', 'Brouillon'), ('prepared', 'Préparé'), ('pending_signature', 'À signer'), ('signed', 'Signé'), ('validated', 'Validé'), ('cancelled', 'Annulé')], default='draft', max_length=30)),
                ('signed_at', models.DateTimeField(blank=True, null=True)),
                ('validated_at', models.DateTimeField(blank=True, null=True)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('party', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='rental_contracts', to='auth.user')),
                ('property', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='rental_contracts', to='core.property')),
            ],
        ),
        migrations.CreateModel(
            name='RentalCase',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reference', models.CharField(blank=True, max_length=40, unique=True)),
                ('status', models.CharField(choices=[('preparing', 'Dossier à préparer'), ('owner_contract', 'Contrat propriétaire à valider'), ('tenant_contract', 'Contrat locataire à valider'), ('signing', 'En attente des signatures'), ('payment', 'En attente du paiement'), ('inspection', 'État des lieux'), ('active', 'Location active'), ('cancelled', 'Dossier annulé')], default='preparing', max_length=30)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='owned_rental_cases', to='auth.user')),
                ('property', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='rental_cases', to='core.property')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='tenant_rental_cases', to='auth.user')),
                ('visit', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='rental_case', to='core.visit')),
            ],
        ),
        migrations.CreateModel(
            name='RentalDocument',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('document_type', models.CharField(choices=[('identity', 'Pièce d’identité'), ('owner_contract', 'Contrat FASTHOME – Propriétaire'), ('tenant_contract', 'Contrat FASTHOME – Locataire'), ('inspection', 'État des lieux'), ('payment_proof', 'Preuve de paiement'), ('other', 'Autre document')], max_length=30)),
                ('label', models.CharField(max_length=180)),
                ('file', models.FileField(blank=True, upload_to='rental/%Y/%m/')),
                ('status', models.CharField(choices=[('required', 'À préparer'), ('prepared', 'Préparé'), ('validated', 'Validé'), ('rejected', 'À corriger')], default='required', max_length=20)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('rental_case', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='documents', to='core.rentalcase')),
            ],
        ),
        migrations.AddField(model_name='rentalcontract', name='rental_case', field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='contracts', to='core.rentalcase')),
        migrations.AddField(model_name='rentalcase', name='owner_contract', field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='owner_case', to='core.rentalcontract')),
        migrations.AddField(model_name='rentalcase', name='tenant_contract', field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='tenant_case', to='core.rentalcontract')),
    ]
