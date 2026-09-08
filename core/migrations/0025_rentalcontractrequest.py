from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0024_rentalpayment'),
    ]

    operations = [
        migrations.CreateModel(
            name='RentalContractRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('request_type', models.CharField(choices=[('problem', 'Signalement d’un problème'), ('notice', 'Demande de départ avec préavis')], max_length=20)),
                ('description', models.TextField()),
                ('requested_date', models.DateField(blank=True, null=True)),
                ('status', models.CharField(choices=[('pending', 'À traiter'), ('in_progress', 'En traitement'), ('resolved', 'Traité'), ('rejected', 'Refusé')], default='pending', max_length=20)),
                ('response', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('contract', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='requests', to='core.rentalcontract')),
                ('rental_case', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='contract_requests', to='core.rentalcase')),
                ('requester', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='rental_contract_requests', to='auth.user')),
            ],
        ),
    ]
