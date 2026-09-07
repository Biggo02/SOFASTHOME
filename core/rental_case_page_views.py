from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from .models import Notification
from .rental_models import RentalCase, RentalContract, RentalDocument
from .rental_document_views import prepare_four_rental_documents

REQUIRED = {'owner_contract', 'tenant_contract', 'owner_inspection', 'tenant_inspection'}


def _allowed(request, case):
    return request.user.is_staff or request.user.pk in {case.owner_id, case.tenant_id}


def _status_for(case, doc_type):
    doc = case.documents.filter(document_type=doc_type).first()
    return doc.status if doc else 'required'


@login_required
def rental_case_detail(request, pk):
    case = get_object_or_404(
        RentalCase.objects.select_related('property', 'owner', 'tenant', 'visit', 'owner_contract', 'tenant_contract').prefetch_related('documents'),
        pk=pk,
    )
    if not _allowed(request, case):
        return HttpResponseForbidden('Accès refusé.')

    # Toute ouverture du dossier synchronise les 2 états des lieux préremplis avec le bien.
    if case.owner_contract and case.tenant_contract:
        prepare_four_rental_documents(case)
        case.refresh_from_db()

    documents = {d.document_type: d for d in case.documents.all()}
    context = {
        'case': case,
        'documents': documents,
        'required_document_types': REQUIRED,
        'document_statuses': {kind: _status_for(case, kind) for kind in REQUIRED},
    }

    if request.method == 'POST':
        if request.user.is_staff and request.POST.get('action') == 'prepare_contracts':
            from .visitor_decision_views import _prepare_rental_documents
            _prepare_rental_documents(case.visit, case)
            prepare_four_rental_documents(case)
            Notification.objects.create(user=case.tenant, title='4 documents prêts', message='Les deux contrats et les deux états des lieux préremplis sont disponibles.')
            Notification.objects.create(user=case.owner, title='4 documents prêts', message='Les deux contrats et les deux états des lieux préremplis sont disponibles.')
            messages.success(request, 'Les 2 contrats et les 2 états des lieux ont été générés.')
        return redirect('rental_case_detail', pk=case.pk)

    return render(request, 'rental_case_detail.html', context)


@login_required
def rental_contract_pdf(request, pk):
    """Accès au PDF du contrat uniquement par la partie concernée ou FASTHOME."""
    contract = get_object_or_404(RentalContract.objects.select_related('rental_case'), pk=pk)
    case = contract.rental_case
    if not _allowed(request, case):
        return HttpResponseForbidden('Accès refusé.')
    if not request.user.is_staff and request.user.pk != contract.party_id:
        return HttpResponseForbidden('Ce contrat est réservé à la partie concernée.')
    from .rental_views import rental_contract_pdf as legacy_contract_pdf
    return legacy_contract_pdf(request, pk)
