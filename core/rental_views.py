from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import Notification
from .rental_models import RentalCase, RentalContract, RentalDocument


def _can_access(request, case):
    return request.user.is_staff


def _activate_if_complete(case):
    owner = case.owner_contract
    tenant = case.tenant_contract
    pv = case.documents.filter(document_type='inspection').exclude(file='').exists()
    if owner and tenant and owner.status == 'signed' and tenant.status == 'signed' and pv:
        if case.status != 'active':
            case.status = 'active'
            case.save(update_fields=['status', 'updated_at'])
            case.property.status = 'rented'
            case.property.save(update_fields=['status', 'updated_at'])
            Notification.objects.create(user=case.tenant, title='Location active', message='Votre location est maintenant active. Les documents signés sont disponibles dans votre espace.')
            Notification.objects.create(user=case.owner, title='Location active', message=f'La location du bien {case.property.reference} est maintenant active. Les documents signés sont disponibles dans votre espace.')
        return True
    return False


@login_required
def rental_cases(request):
    # The complete dossier is an internal FASTHOME workspace.
    if not request.user.is_staff:
        return redirect('contracts')
    queryset = RentalCase.objects.select_related('property', 'owner', 'tenant', 'visit', 'owner_contract', 'tenant_contract').prefetch_related('documents').order_by('-updated_at')
    return render(request, 'rental_cases.html', {'cases': queryset.distinct()})


@login_required
def rental_case_detail(request, pk):
    case = get_object_or_404(RentalCase.objects.select_related('property', 'owner', 'tenant', 'visit', 'owner_contract', 'tenant_contract').prefetch_related('documents'), pk=pk)
    if not _can_access(request, case):
        return HttpResponseForbidden('Ce dossier est réservé à FASTHOME.')
    if request.method == 'POST':
        if request.user.is_staff and request.POST.get('action') == 'prepare_contracts':
            from .visitor_decision_views import _prepare_rental_documents
            _prepare_rental_documents(case.visit, case)
            Notification.objects.create(user=case.tenant, title='Documents prêts', message='Les contrats et le procès-verbal sont disponibles dans votre espace.')
            Notification.objects.create(user=case.owner, title='Documents prêts', message='Les contrats et le procès-verbal de votre dossier sont disponibles.')
            messages.success(request, 'Les deux contrats et le procès-verbal ont été générés.')
        return redirect('rental_case_detail', pk=case.pk)
    return render(request, 'rental_case_detail.html', {'case': case})


@login_required
def rental_document_upload(request, pk):
    case = get_object_or_404(RentalCase.objects.select_related('property', 'owner', 'tenant', 'owner_contract', 'tenant_contract'), pk=pk)
    if not (request.user.is_staff or request.user.pk in {case.owner_id, case.tenant_id}):
        return HttpResponseForbidden('Accès refusé.')
    if request.method != 'POST':
        return redirect('contracts')
    doc_type = request.POST.get('document_type')
    uploaded = request.FILES.get('file')
    if not uploaded or doc_type not in {'owner_contract', 'tenant_contract', 'inspection'}:
        messages.error(request, 'Veuillez sélectionner un document PDF signé.')
        return redirect('contracts')
    if uploaded.content_type != 'application/pdf' and not uploaded.name.lower().endswith('.pdf'):
        messages.error(request, 'Le document signé doit être au format PDF.')
        return redirect('contracts')
    if doc_type == 'owner_contract' and not (request.user.is_staff or request.user.pk == case.owner_id):
        return HttpResponseForbidden('Seul le propriétaire ou FASTHOME peut déposer ce document.')
    if doc_type == 'tenant_contract' and not (request.user.is_staff or request.user.pk == case.tenant_id):
        return HttpResponseForbidden('Seul le locataire ou FASTHOME peut déposer ce document.')
    if doc_type == 'inspection' and not request.user.is_staff:
        return HttpResponseForbidden('Le procès-verbal signé est déposé par FASTHOME.')

    labels = {'owner_contract': 'Contrat FASTHOME – Propriétaire', 'tenant_contract': 'Contrat FASTHOME – Locataire', 'inspection': 'Procès-verbal de visite / état des lieux'}
    doc = case.documents.filter(document_type=doc_type).first()
    if not doc:
        doc = RentalDocument.objects.create(rental_case=case, document_type=doc_type, label=labels[doc_type])
    doc.file = uploaded
    doc.status = 'validated'
    doc.notes = f'Document signé téléversé par {request.user.get_full_name() or request.user.username}.'
    doc.save()

    if doc_type == 'owner_contract' and case.owner_contract:
        case.owner_contract.status = 'signed'
        case.owner_contract.signed_at = timezone.now()
        case.owner_contract.save(update_fields=['status', 'signed_at', 'updated_at'])
    elif doc_type == 'tenant_contract' and case.tenant_contract:
        case.tenant_contract.status = 'signed'
        case.tenant_contract.signed_at = timezone.now()
        case.tenant_contract.save(update_fields=['status', 'signed_at', 'updated_at'])

    if _activate_if_complete(case):
        messages.success(request, 'Tous les documents signés sont reçus : la location est maintenant active.')
    else:
        messages.success(request, 'Document signé téléversé avec succès.')
    return redirect('contracts')
