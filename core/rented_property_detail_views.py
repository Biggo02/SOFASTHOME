from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, render

from .models import Payment, Property
from .rental_models import RentalCase, RentalContract


@login_required
def rented_property_detail(request, pk):
    """Owner-only property dossier with strict owner-side document visibility."""
    property_obj = get_object_or_404(Property, pk=pk)
    if property_obj.owner_id != request.user.id and not request.user.is_staff:
        return HttpResponseForbidden("Ce dossier n'est pas accessible depuis votre espace.")

    rental_cases = list(
        RentalCase.objects.filter(property=property_obj)
        .select_related('owner', 'tenant', 'visit', 'owner_contract', 'tenant_contract')
        .order_by('-updated_at')
    )
    active_case = next((case for case in rental_cases if case.status == 'active'), rental_cases[0] if rental_cases else None)

    # Even though both contracts belong to the same property, an owner must
    # only see the contract in which the owner is the contracting party.
    contracts = (
        RentalContract.objects.filter(
            rental_case__property=property_obj,
            contract_type='owner_agreement',
            party=request.user,
        )
        .select_related('party', 'rental_case', 'property')
        .order_by('-updated_at')
    )

    # Same principle for signed documents: tenant documents are never exposed
    # to the owner merely because they are attached to the same rental case.
    documents = []
    if active_case:
        documents = list(
            active_case.documents.filter(
                document_type__in={'owner_contract', 'owner_inspection'}
            ).order_by('document_type', '-updated_at')
        )

    # The owner can consult the payment ledger for money received on this
    # property. Payment proofs remain part of the financial record, not the
    # other party's contractual document area.
    received_payments = (
        Payment.objects.filter(contract__property=property_obj, contract__role='tenant')
        .select_related('contract', 'contract__user')
        .prefetch_related('proofs')
        .order_by('-due_date', '-id')
    )

    total_received = sum((payment.amount_paid or 0) for payment in received_payments)
    total_due = sum((payment.amount_due or 0) for payment in received_payments)

    return render(request, 'rented_property_detail.html', {
        'property': property_obj,
        'active_case': active_case,
        'rental_cases': rental_cases,
        'contracts': contracts,
        'documents': documents,
        'received_payments': received_payments,
        'total_received': total_received,
        'total_due': total_due,
        'balance_due': max(total_due - total_received, 0),
    })
