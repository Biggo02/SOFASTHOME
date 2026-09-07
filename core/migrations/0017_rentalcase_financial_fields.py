from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0016_alter_rentalcase_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='rentalcase',
            name='rent_payment_amount',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name='rentalcase',
            name='rent_payment_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='rentalcase',
            name='guarantee_amount',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
    ]
