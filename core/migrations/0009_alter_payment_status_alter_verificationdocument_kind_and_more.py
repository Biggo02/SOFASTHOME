from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0008_align_property_field_choices'),
    ]

    operations = [
        migrations.AlterField(
            model_name='payment',
            name='status',
            field=models.CharField(default='upcoming', max_length=20),
        ),
        migrations.AlterField(
            model_name='verificationdocument',
            name='kind',
            field=models.CharField(max_length=20),
        ),
        migrations.AlterField(
            model_name='visit',
            name='status',
            field=models.CharField(default='pending', max_length=20),
        ),
    ]
