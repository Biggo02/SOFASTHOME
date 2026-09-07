from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone

from .models import Notification
from .rental_models import RentalCase, RentalContract, RentalDocument

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
    complete = all(docs.filter(document_type=kind, status='validated').exclude(file='').exists() for kind in REQUIRED_DOCUMENTS)
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
        _notify(case.tenant, 'Contrat effectif — location active', 'Les 4 documents signés ont été vérifiés par FASTHOME. Votre contrat est maintenant effectif. Votre contrat et votre état des lieux signés sont disponibles dans votre espace.')
        _notify(case.owner, 'Contrat effectif — location active', f'Les 4 documents signés du dossier {case.reference} ont été vérifiés par FASTHOME. Votre convention et votre état des lieux signés sont disponibles dans votre espace.')
    return True


@login_required
def upload_signed_rental_document(request, pk):
    case = get_object_or_404(RentalCase.objects.select_related('property', 'owner', 'tenant', 'owner_contract', 'tenant_contract'), pk=pk)
    if not request.user.is_staff and request.user.pk not in {case.owner_id, case.tenant_id}:
        return HttpResponseForbidden('Accès refusé.')
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

    if doc_type in OWNER_DOCUMENTS and not (request.user.is_staff or request.user.pk == case.owner_id):
        return HttpResponseForbidden('Seul le propriétaire ou FASTHOME peut déposer ce document.')
    if doc_type in TENANT_DOCUMENTS and not (request.user.is_staff or request.user.pk == case.tenant_id):
        return HttpResponseForbidden('Seul le locataire ou FASTHOME peut déposer ce document.')
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
    document.notes = f'Document signé téléversé par {request.user.get_full_name() or request.user.username}, en attente de vérification FASTHOME.'
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

    # Notification uniquement aux personnes qui ont réellement besoin de cette information.
    # Le déposant est informé de la réception de son propre document.
    _notify(request.user, 'Document reçu', f'{LABELS[doc_type]} reçu et transmis à FASTHOME pour vérification.')

    # L'autre partie n'est jamais informée du document signé de son interlocuteur.
    # FASTHOME/staff reçoit uniquement les notifications opérationnelles nécessaires.
    for staff_user in request.user.__class__.objects.filter(is_staff=True).exclude(pk=request.user.pk):
        _notify(staff_user, 'Document signé à vérifier', f'{LABELS[doc_type]} a été téléversé dans le dossier {case.reference} et attend une vérification FASTHOME.')

    messages.success(request, 'Document signé reçu. Il doit maintenant être vérifié par FASTHOME avant de rendre le contrat effectif.')
    return redirect('rental_case_detail', pk=case.pk)


@login_required
def verify_signed_rental_document(request, pk, document_id):
    if not request.user.is_staff:
        return HttpResponseForbidden('Seul FASTHOME peut vérifier les documents signés.')
    case = get_object_or_404(RentalCase.objects.select_related('owner', 'tenant', 'property', 'owner_contract', 'tenant_contract'), pk=pk)
    document = get_object_or_404(RentalDocument, pk=document_id, rental_case=case, document_type__in=REQUIRED_DOCUMENTS)
    if request.method != 'POST':
        return redirect('rental_case_detail', pk=case.pk)
    decision = request.POST.get('decision')
    if decision == 'validate':
        if not document.file:
            messages.error(request, 'Impossible de vérifier un document sans fichier.')
            return redirect('rental_case_detail', pk=case.pk)
        document.status = 'validated'
        document.notes = f'Document vérifié et validé par {request.user.get_full_name() or request.user.username}.'
        document.save(update_fields=['status', 'notes', 'updated_at'])
        if document.document_type == 'owner_contract' and case.owner_contract:
            case.owner_contract.status = 'signed'
            case.owner_contract.validated_at = timezone.now()
            case.owner_contract.save(update_fields=['status', 'validated_at', 'updated_at'])
            _notify(case.owner, 'Document validé', f'{document.label} du dossier {case.reference} a été vérifié et validé par FASTHOME.')
        elif document.document_type == 'tenant_contract' and case.tenant_contract:
            case.tenant_contract.status = 'signed'
            case.tenant_contract.validated_at = timezone.now()
            case.tenant_contract.save(update_fields=['status', 'validated_at', 'updated_at'])
            _notify(case.tenant, 'Document validé', f'{document.label} du dossier {case.reference} a été vérifié et validé par FASTHOME.')
        messages.success(request, f'{document.label} validé.')
        if _activate_if_complete(case):
            messages.success(request, 'Les 4 documents signés sont vérifiés : le contrat devient effectif et la location est active.')
    elif decision == 'reject':
        document.status = 'rejected'
        document.notes = request.POST.get('note', '').strip() or f'Document à corriger — vérification par {request.user.get_full_name() or request.user.username}.'
        document.save(update_fields=['status', 'notes', 'updated_at'])
        messages.warning(request, f'{document.label} doit être corrigé puis téléversé à nouveau.')
        target = case.owner if document.document_type in OWNER_DOCUMENTS else case.tenant
        _notify(target, 'Document à corriger', f'{document.label} du dossier {case.reference} doit être corrigé. Motif : {document.notes}')
    else:
        messages.error(request, 'Décision de vérification invalide.')
    return redirect('rental_case_detail', pk=case.pk)
