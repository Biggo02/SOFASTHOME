from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0014_backfill_rental_cases')]
    operations = [
        migrations.AlterField(
            model_name='rentaldocument',
            name='status',
            field=models.CharField(max_length=20, choices=[('required', 'À préparer'), ('prepared', 'Préparé'), ('validated', 'Signé / validé'), ('rejected', 'À corriger')], default='required'),
        ),
        migrations.AlterField(
            model_name='rentalcontract',
            name='status',
            field=models.CharField(max_length=30, choices=[('draft', 'Brouillon'), ('prepared', 'Préparé'), ('pending_signature', 'À signer'), ('signed', 'Signé'), ('validated', 'Validé'), ('cancelled', 'Annulé')], default='draft'),
        ),
    ]
