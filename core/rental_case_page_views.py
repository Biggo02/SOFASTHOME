from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .models import Notification
from .rental_models import RentalCase, RentalContract
from .rental_document_views import prepare_four_rental_documents
from .rental_contract_generator import generate_contract_pdf

REQUIRED = {'owner_contract', 'tenant_contract', 'owner_inspection', 'tenant_inspection'}
OWNER_DOCUMENTS = {'owner_contract', 'owner_inspection'}
TENANT_DOCUMENTS = {'tenant_contract', 'tenant_inspection'}


def _allowed(request, case):
    return request.user.is_staff


@login_required
def rental_case_detail(request, pk):
    case = get_object_or_404(
        RentalCase.objects.select_related(
            'property', 'owner', 'tenant', 'visit', 'owner_contract', 'tenant_contract'
        ).prefetch_related('documents'),
        pk=pk,
    )
    # The complete rental dossier is an internal FASTHOME workspace.
    # Owners and tenants must use their personal space and their own contract/document views.
    if not _allowed(request, case):
        return HttpResponseForbidden('Ce dossier est réservé à FASTHOME.')

    if case.owner_contract and case.tenant_contract:
        prepare_four_rental_documents(case)
        case.refresh_from_db()

    documents = {d.document_type: d for d in case.documents.all()}
    visible_types = REQUIRED

    uploaded_count = sum(
        1 for kind in visible_types if documents.get(kind) and documents[kind].file
    )
    validated_count = sum(
        1 for kind in visible_types
        if documents.get(kind) and documents[kind].status == 'validated' and documents[kind].file
    )

    context = {
        'case': case,
        'documents': documents,
        'required_document_types': REQUIRED,
        'visible_document_types': visible_types,
        'uploaded_count': uploaded_count,
        'validated_count': validated_count,
        'is_owner_view': False,
        'is_tenant_view': False,
        'is_staff_view': True,
        'document_statuses': {kind: (documents.get(kind).status if documents.get(kind) else 'required') for kind in REQUIRED},
    }

    if request.method == 'POST':
        if request.user.is_staff and request.POST.get('action') == 'prepare_contracts':
            from .visitor_decision_views import _prepare_rental_documents
            _prepare_rental_documents(case.visit, case)
            prepare_four_rental_documents(case)
            Notification.objects.create(
                user=case.tenant,
                title='4 documents prêts',
                message='Les deux contrats et les deux états des lieux préremplis sont disponibles.',
            )
            Notification.objects.create(
                user=case.owner,
                title='4 documents prêts',
                message='Les deux contrats et les deux états des lieux préremplis sont disponibles.',
            )
            messages.success(request, 'Les 2 contrats et les 2 états des lieux ont été générés.')
        return redirect('rental_case_detail', pk=case.pk)

    return render(request, 'rental_case_detail.html', context)


@login_required
def rental_contract_pdf(request, pk):
    contract = get_object_or_404(
        RentalContract.objects.select_related(
            'rental_case', 'rental_case__property', 'rental_case__owner',
            'rental_case__tenant', 'party'
        ),
        pk=pk,
    )
    case = contract.rental_case
    if not request.user.is_staff and request.user.pk != contract.party_id:
        return HttpResponseForbidden('Ce contrat est réservé à la partie concernée.')

    pdf = generate_contract_pdf(contract)
    kind = 'mise-en-location-proprietaire' if contract.contract_type == 'owner_agreement' else 'sous-location-locataire'
    filename = f'{kind}-{contract.reference}.pdf'
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response
