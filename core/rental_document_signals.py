from django.core.files.base import ContentFile
from django.db.models.signals import post_save
from django.dispatch import receiver

from .rental_models import RentalDocument
from .rental_contract_generator import generate_contract_pdf


@receiver(post_save, sender=RentalDocument)
def refresh_generated_contract_document(sender, instance, created, **kwargs):
    if getattr(instance, '_contract_pdf_refreshing', False):
        return
    if instance.document_type not in {'owner_contract', 'tenant_contract'}:
        return
    # Never replace a document that a party has uploaded for verification.
    if instance.status not in {'required', 'prepared'} or not instance.file:
        return
    case = instance.rental_case
    contract_type = 'owner_agreement' if instance.document_type == 'owner_contract' else 'tenant_sublease'
    contract = case.contracts.filter(contract_type=contract_type).first()
    if not contract:
        return
    instance._contract_pdf_refreshing = True
    try:
        pdf = generate_contract_pdf(contract)
        instance.file.save(f'{contract.reference}.pdf', ContentFile(pdf), save=False)
        instance.status = 'prepared'
        instance.save(update_fields=['file', 'status', 'updated_at'])
    finally:
        instance._contract_pdf_refreshing = False

# AppConfig already imports this module at startup; this import activates the
# wider notification signal registry without changing the existing bootstrap.
from . import notification_signals  # noqa: E402,F401
