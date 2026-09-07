from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, render

from .rental_models import RentalContract


@login_required
def rental_contract_detail(request, pk):
    """Detailed personal view of one rental contract and its related rental data."""
    contract = get_object_or_404(
        RentalContract.objects.select_related(
            'rental_case',
            'rental_case__owner',
            'rental_case__tenant',
            'rental_case__visit',
            'property',
            'party',
        ),
        pk=pk,
    )

    if request.user.pk != contract.party_id and not request.user.is_staff:
        return HttpResponseForbidden('Ce contrat ne vous est pas destiné.')

    case = contract.rental_case
    is_owner_contract = contract.contract_type == 'owner_agreement'
    counterpart = case.tenant if is_owner_contract else case.owner
    allowed_document_types = (
        {'owner_contract', 'owner_inspection'}
        if is_owner_contract
        else {'tenant_contract', 'tenant_inspection'}
    )
    documents = list(
        case.documents.filter(document_type__in=allowed_document_types)
        .order_by('document_type', '-updated_at')
    )

    return render(
        request,
        'rental_contract_detail.html',
        {
            'contract': contract,
            'case': case,
            'property': contract.property,
            'counterpart': counterpart,
            'documents': documents,
            'is_owner_contract': is_owner_contract,
            'visit': case.visit,
        },
    )
