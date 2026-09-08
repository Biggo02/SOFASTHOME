from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, render

from .models import Property
from .rental_models import RentalCase, RentalContract, OwnerRemittance


@login_required
def rented_property_detail(request, pk):
    """Dossier du bien loué : le propriétaire voit ses documents et ses versements FASTHOME."""
    property_obj = get_object_or_404(Property, pk=pk)
    if property_obj.owner_id != request.user.id and not request.user.is_staff:
        return HttpResponseForbidden("Ce dossier n'est pas accessible depuis votre espace.")

    rental_cases = list(
        RentalCase.objects.filter(property=property_obj)
        .select_related('owner', 'tenant', 'visit', 'owner_contract', 'tenant_contract')
        .order_by('-updated_at')
    )
    active_case = next((case for case in rental_cases if case.status == 'active'), rental_cases[0] if rental_cases else None)

    contracts = (
        RentalContract.objects.filter(
            rental_case__property=property_obj,
            contract_type='owner_agreement',
            party=request.user,
        )
        .select_related('party', 'rental_case', 'property')
        .order_by('-updated_at')
    )

    documents = []
    if active_case:
        documents = list(
            active_case.documents.filter(
                document_type__in={'owner_contract', 'owner_inspection'}
            ).order_by('document_type', '-updated_at')
        )

    # Relevé distinct : ce sont les sommes effectivement versées par FASTHOME
    # au propriétaire, jamais les dettes ou paiements du locataire.
    remittances = (
        OwnerRemittance.objects.filter(
            property=property_obj,
            owner=request.user,
        )
        .select_related('rental_case')
        .order_by('payment_date', 'id')
    )

    total_remitted = sum((item.amount or 0) for item in remittances)

    return render(request, 'rented_property_detail.html', {
        'property': property_obj,
        'active_case': active_case,
        'rental_cases': rental_cases,
        'contracts': contracts,
        'documents': documents,
        'remittances': remittances,
        'total_remitted': total_remitted,
    })
