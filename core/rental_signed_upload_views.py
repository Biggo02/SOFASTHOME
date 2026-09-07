from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone

from .models import Notification
from .rental_models import RentalCase, RentalDocument

REQUIRED_DOCUMENTS = {'owner_contract', 'tenant_contract', 'owner_inspection', 'tenant_inspection'}
OWNER_DOCUMENTS = {'owner_contract', 'owner_inspection'}
TENANT_DOCUMENTS = {'tenant_contract', 'tenant_inspection'}
LABELS = {
    'owner_contract': 'Contrat FASTHOME ↔ Propriétaire signé',
    'tenant_contract': 'Contrat FASTHOME ↔ Locataire signé',
    'owner_inspection': 'État des lieux FASTHOME ↔ Propriétaire signé',
    'tenant_inspection': 'État des lieux FASTHOME ↔ Locataire signé',
}


def _notify(user, title, message):
    if user:
        Notification.objects.create(user=user, title=title, message=message)


def _activate_if_complete(case):
    docs = case.documents.filter(document_type__in=REQUIRED_DOCUMENTS)
    complete = all(
        docs.filter(document_type=kind, status='validated').exclude(file='').exists()
        for kind in REQUIRED_DOCUMENTS
    )
    if not complete:
        return False

    owner = case.owner_contract
    tenant = case.tenant_contract
    if owner:
        owner.status = 'validated'
        owner.validated_at = timezone.now()
        owner.save(update_fields=['status', 'validated_at', 'updated_at'])
    if tenant:
        tenant.status = 'validated'
        tenant.validated_at = timezone.now()
        tenant.save(update_fields=['status', 'validated_at', 'updated_at'])

    if case.status != 'active':
        case.status = 'active'
        case.save(update_fields=['status', 'updated_at'])
        case.property.status = 'rented'
        case.property.save(update_fields=['status', 'updated_at'])
        _notify(
            case.tenant,
            'Contrat effectif — location active',
            'Les 4 documents signés ont été vérifiés par FASTHOME. Votre contrat et votre état des lieux signés sont maintenant disponibles dans votre espace personnel.',
        )
        _notify(
            case.owner,
            'Contrat effectif — location active',
            f'Les 4 documents signés du dossier {case.reference} ont été vérifiés par FASTHOME. Votre convention et votre état des lieux signés sont maintenant disponibles dans votre espace personnel.',
        )
    return True


@login_required
def upload_signed_rental_document(request, pk):
    """Seul FASTHOME téléverse les documents signés par les parties."""
    if not request.user.is_staff:
        return HttpResponseForbidden('Seul FASTHOME peut téléverser les documents signés.')

    case = get_object_or_404(
        RentalCase.objects.select_related('property', 'owner', 'tenant', 'owner_contract', 'tenant_contract'),
        pk=pk,
    )
    if request.method != 'POST':
        return redirect('rental_case_detail', pk=case.pk)

    doc_type = request.POST.get('document_type', '').strip()
    uploaded = request.FILES.get('file')
    if doc_type not in REQUIRED_DOCUMENTS or not uploaded:
        messages.error(request, 'Veuillez sélectionner le document PDF signé correspondant.')
        return redirect('rental_case_detail', pk=case.pk)
    if uploaded.content_type != 'application/pdf' and not uploaded.name.lower().endswith('.pdf'):
        messages.error(request, 'Le document signé doit être au format PDF.')
        return redirect('rental_case_detail', pk=case.pk)
    if case.status == 'active':
        messages.info(request, 'Ce dossier est déjà actif : les documents signés sont verrouillés.')
        return redirect('rental_case_detail', pk=case.pk)

    document, _ = RentalDocument.objects.get_or_create(
        rental_case=case,
        document_type=doc_type,
        defaults={'label': LABELS[doc_type]},
    )
    document.file = uploaded
    document.status = 'pending_review'
    document.notes = f'Document signé téléversé par FASTHOME ({request.user.get_full_name() or request.user.username}).'
    document.save()

    if doc_type == 'owner_contract' and case.owner_contract:
        case.owner_contract.status = 'pending_signature'
        case.owner_contract.signed_at = timezone.now()
        case.owner_contract.save(update_fields=['status', 'signed_at', 'updated_at'])
    elif doc_type == 'tenant_contract' and case.tenant_contract:
        case.tenant_contract.status = 'pending_signature'
        case.tenant_contract.signed_at = timezone.now()
        case.tenant_contract.save(update_fields=['status', 'signed_at', 'updated_at'])

    case.status = 'signing'
    case.save(update_fields=['status', 'updated_at'])

    # Le client n'envoie rien. Il sera informé uniquement lorsque son document
    # personnel aura été vérifié, puis lorsque les 4 documents seront validés.
    target = case.owner if doc_type in OWNER_DOCUMENTS else case.tenant
    _notify(target, 'Document signé reçu par FASTHOME', f'{LABELS[doc_type]} a été signé et téléversé par FASTHOME. Il est en cours de vérification.')
    messages.success(request, 'Document signé téléversé par FASTHOME. Il doit maintenant être vérifié.')
    return redirect('rental_case_detail', pk=case.pk)


@login_required
def verify_signed_rental_document(request, pk, document_id):
    if not request.user.is_staff:
        return HttpResponseForbidden('Seul FASTHOME peut vérifier les documents signés.')
    case = get_object_or_404(
        RentalCase.objects.select_related('owner', 'tenant', 'property', 'owner_contract', 'tenant_contract'),
        pk=pk,
    )
    document = get_object_or_404(
        RentalDocument,
        pk=document_id,
        rental_case=case,
        document_type__in=REQUIRED_DOCUMENTS,
    )
    if request.method != 'POST':
        return redirect('rental_case_detail', pk=case.pk)

    decision = request.POST.get('decision')
    if decision == 'validate':
        if not document.file:
            messages.error(request, 'Impossible de vérifier un document sans fichier.')
            return redirect('rental_case_detail', pk=case.pk)
        document.status = 'validated'
        document.notes = f'Document vérifié et validé par FASTHOME ({request.user.get_full_name() or request.user.username}).'
        document.save(update_fields=['status', 'notes', 'updated_at'])

        target = case.owner if document.document_type in OWNER_DOCUMENTS else case.tenant
        _notify(target, 'Votre document signé est validé', f'{document.label} du dossier {case.reference} a été vérifié et validé par FASTHOME. Il sera accessible dans votre espace personnel.')

        if document.document_type == 'owner_contract' and case.owner_contract:
            case.owner_contract.status = 'signed'
            case.owner_contract.validated_at = timezone.now()
            case.owner_contract.save(update_fields=['status', 'validated_at', 'updated_at'])
        elif document.document_type == 'tenant_contract' and case.tenant_contract:
            case.tenant_contract.status = 'signed'
            case.tenant_contract.validated_at = timezone.now()
            case.tenant_contract.save(update_fields=['status', 'validated_at', 'updated_at'])

        messages.success(request, f'{document.label} validé.')
        if _activate_if_complete(case):
            messages.success(request, 'Les 4 documents signés sont vérifiés : le contrat devient effectif et la location est active.')

    elif decision == 'reject':
        document.status = 'rejected'
        document.notes = request.POST.get('note', '').strip() or f'Document à corriger — vérification FASTHOME.'
        document.save(update_fields=['status', 'notes', 'updated_at'])
        target = case.owner if document.document_type in OWNER_DOCUMENTS else case.tenant
        _notify(target, 'Document signé à corriger', f'{document.label} du dossier {case.reference} doit être corrigé. Motif : {document.notes}')
        messages.warning(request, f'{document.label} doit être corrigé puis remplacé par FASTHOME.')
    else:
        messages.error(request, 'Décision de vérification invalide.')

    return redirect('rental_case_detail', pk=case.pk)
