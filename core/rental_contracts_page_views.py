from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.db.models import Prefetch

from .rental_models import RentalContract, RentalDocument


@login_required
def rental_contracts(request):
    """Personal contract space: only the connected party's own contract and documents."""
    contracts = (
        RentalContract.objects
        .select_related('rental_case', 'property', 'party', 'rental_case__owner', 'rental_case__tenant')
        .prefetch_related(Prefetch('rental_case__documents', queryset=RentalDocument.objects.order_by('document_type')))
        .filter(party=request.user)
        .order_by('-updated_at')
    )
    return render(request, 'rental_contracts.html', {'contracts': contracts})
