from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0013_rental_workflow')]

    operations = [
        migrations.AlterField(
            model_name='rentaldocument',
            name='document_type',
            field=models.CharField(
                choices=[
                    ('identity', 'Pièce d’identité'),
                    ('owner_contract', 'Contrat FASTHOME – Propriétaire'),
                    ('tenant_contract', 'Contrat FASTHOME – Locataire'),
                    ('owner_inspection', 'État des lieux FASTHOME – Propriétaire'),
                    ('tenant_inspection', 'État des lieux FASTHOME – Locataire'),
                    ('inspection', 'État des lieux — ancien format'),
                    ('payment_proof', 'Preuve de paiement'),
                    ('other', 'Autre document'),
                ],
                max_length=30,
            ),
        ),
        migrations.AlterField(
            model_name='rentaldocument',
            name='status',
            field=models.CharField(
                choices=[
                    ('required', 'À préparer'),
                    ('prepared', 'Préparé'),
                    ('pending_review', 'À vérifier'),
                    ('validated', 'Signé / vérifié'),
                    ('rejected', 'À corriger'),
                ],
                default='required',
                max_length=20,
            ),
        ),
    ]
