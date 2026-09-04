from django.core.management.base import BaseCommand
from core.models import Visit, RentalCase, RentalDocument


class Command(BaseCommand):
    help = 'Crée les dossiers de location manquants pour les visiteurs intéressés.'

    def handle(self, *args, **options):
        created_cases = 0
        created_documents = 0
        visits = Visit.objects.filter(final_decision='interested').select_related('property', 'property__owner', 'requester')
        for visit in visits:
            case, created = RentalCase.objects.get_or_create(
                visit=visit,
                defaults={
                    'property': visit.property,
                    'owner': visit.property.owner,
                    'tenant': visit.requester,
                    'status': 'preparing',
                },
            )
            if created:
                created_cases += 1
            required = [
                ('identity', 'Pièce d’identité du locataire'),
                ('owner_contract', 'Contrat FASTHOME – Propriétaire'),
                ('tenant_contract', 'Contrat FASTHOME – Locataire'),
                ('inspection', 'Procès-verbal / état des lieux commun'),
            ]
            existing_types = set(case.documents.values_list('document_type', flat=True))
            for document_type, label in required:
                if document_type not in existing_types:
                    RentalDocument.objects.create(rental_case=case, document_type=document_type, label=label)
                    created_documents += 1
        self.stdout.write(self.style.SUCCESS(f'{created_cases} dossier(s) créé(s), {created_documents} document(s) ajouté(s).'))
