from django.db import migrations


def create_missing_cases(apps, schema_editor):
    Visit = apps.get_model('core', 'Visit')
    RentalCase = apps.get_model('core', 'RentalCase')
    RentalDocument = apps.get_model('core', 'RentalDocument')

    for visit in Visit.objects.filter(status='done', final_decision='interested').select_related('property', 'property__owner', 'requester'):
        case, created = RentalCase.objects.get_or_create(
            visit_id=visit.pk,
            defaults={
                'property_id': visit.property_id,
                'owner_id': visit.property.owner_id,
                'tenant_id': visit.requester_id,
                'status': 'preparing',
            },
        )
        if created:
            RentalDocument.objects.bulk_create([
                RentalDocument(rental_case_id=case.pk, document_type='identity', label='Pièce d’identité du locataire'),
                RentalDocument(rental_case_id=case.pk, document_type='owner_contract', label='Contrat FASTHOME – Propriétaire'),
                RentalDocument(rental_case_id=case.pk, document_type='tenant_contract', label='Contrat FASTHOME – Locataire'),
                RentalDocument(rental_case_id=case.pk, document_type='inspection', label='Procès-verbal / état des lieux commun'),
            ])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [('core', '0013_rental_workflow')]
    operations = [migrations.RunPython(create_missing_cases, noop)]
