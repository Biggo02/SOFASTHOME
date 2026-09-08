from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0022_property_fence'),
    ]

    operations = [
        migrations.CreateModel(
            name='OwnerRemittance',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('payment_date', models.DateField()),
                ('period_start', models.DateField(blank=True, null=True)),
                ('period_end', models.DateField(blank=True, null=True)),
                ('reference', models.CharField(blank=True, max_length=60, unique=True)),
                ('payment_method', models.CharField(blank=True, default='', max_length=40)),
                ('proof', models.FileField(blank=True, upload_to='owner_remittances/%Y/%m/')),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='owner_remittances', to='auth.user')),
                ('property', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='owner_remittances', to='core.property')),
                ('rental_case', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='owner_remittances', to='core.rentalcase')),
            ],
        ),
    ]
