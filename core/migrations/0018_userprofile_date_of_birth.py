from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0017_rentalcase_financial_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='date_of_birth',
            field=models.DateField(blank=True, null=True),
        ),
    ]
