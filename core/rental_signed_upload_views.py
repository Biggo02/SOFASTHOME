from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone

from .models import Notification
from .rental_models import RentalCase, RentalDocument


@login_required
def upload_signed_rental_document(request, pk):
    case = get_object_or_404(
        RentalCase.objects.select_related('property', 'owner', 'tenant', 'owner_contract', 'tenant_contract'),
        pk=pk,
    )
    if not request.user.is_staff and request.user.pk not in {case.owner_id, case.tenant_id}:
        return HttpResponseForbidden('Accès refusé.')
    if request.method != 'POST':
        return redirect('rental_case_detail', pk=case.pk)

    doc_type = request.POST.get('document_type', '').strip()
    uploaded = request.FILES.get('file')
    allowed = {'owner_contract', 'tenant_contract', 'inspection'}
    if doc_type not in allowed or not uploaded:
        messages.error(request, 'Veuillez sélectionner le document PDF signé correspondant.')
        return redirect('rental_case_detail', pk=case.pk)
    if uploaded.content_type != 'application/pdf' and not uploaded.name.lower().endswith('.pdf'):
        messages.error(request, 'Le document signé doit être au format PDF.')
        return redirect('rental_case_detail', pk=case.pk)

    if doc_type == 'owner_contract' and not (request.user.is_staff or request.user.pk == case.owner_id):
        return HttpResponseForbidden('Seul le propriétaire ou FASTHOME peut déposer le contrat propriétaire.')
    if doc_type == 'tenant_contract' and not (request.user.is_staff or request.user.pk == case.tenant_id):
        return HttpResponseForbidden('Seul le locataire ou FASTHOME peut déposer le contrat locataire.')
    if doc_type == 'inspection' and not (request.user.is_staff or request.user.pk in {case.owner_id, case.tenant_id}):
        return HttpResponseForbidden('Seules les parties du dossier ou FASTHOME peuvent déposer le document annexe signé.')

    labels = {
        'owner_contract': 'Contrat FASTHOME – Propriétaire',
        'tenant_contract': 'Contrat FASTHOME – Locataire',
        'inspection': 'Document annexe – Procès-verbal / état des lieux',
    }
    document, _ = RentalDocument.objects.get_or_create(
        rental_case=case,
        document_type=doc_type,
        defaults={'label': labels[doc_type]},
    )
    document.file = uploaded
    document.status = 'validated'
    document.notes = f'Document signé téléversé par {request.user.get_full_name() or request.user.username}.'
    document.save()

    if doc_type == 'owner_contract' and case.owner_contract:
        case.owner_contract.status = 'signed'
        case.owner_contract.signed_at = timezone.now()
        case.owner_contract.save(update_fields=['status', 'signed_at', 'updated_at'])
        Notification.objects.create(user=case.tenant, title='Contrat propriétaire reçu', message='Le contrat signé par le propriétaire a été reçu par FASTHOME.')
    elif doc_type == 'tenant_contract' and case.tenant_contract:
        case.tenant_contract.status = 'signed'
        case.tenant_contract.signed_at = timezone.now()
        case.tenant_contract.save(update_fields=['status', 'signed_at', 'updated_at'])
        Notification.objects.create(user=case.owner, title='Contrat locataire reçu', message='Le contrat signé par le locataire a été reçu par FASTHOME.')
    else:
        Notification.objects.create(user=case.owner, title='Document annexe reçu', message='Le document annexe signé a été reçu par FASTHOME.')
        Notification.objects.create(user=case.tenant, title='Document annexe reçu', message='Le document annexe signé a été reçu par FASTHOME.')

    owner = case.owner_contract
    tenant = case.tenant_contract
    annex = case.documents.filter(document_type='inspection').exclude(file='').exists()
    if owner and tenant and owner.status == 'signed' and tenant.status == 'signed' and annex:
        case.status = 'active'
        case.save(update_fields=['status', 'updated_at'])
        case.property.status = 'rented'
        case.property.save(update_fields=['status', 'updated_at'])
        Notification.objects.create(user=case.tenant, title='Location active', message='Les trois documents signés ont été reçus. Votre location est maintenant active.')
        Notification.objects.create(user=case.owner, title='Location active', message=f'Les trois documents signés du dossier {case.reference} ont été reçus. La location est maintenant active.')
        messages.success(request, 'Les 3 documents signés sont reçus : la location est maintenant active.')
    else:
        messages.success(request, 'Document signé téléversé avec succès.')
    return redirect('rental_case_detail', pk=case.pk)
