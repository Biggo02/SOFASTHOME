from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0018_userprofile'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='date_of_birth',
            field=models.DateField(blank=True, null=True),
        ),
    ]
