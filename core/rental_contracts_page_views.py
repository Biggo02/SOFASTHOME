from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .rental_models import RentalContract


@login_required
def rental_contracts(request):
    """Affiche les contrats de location FASTHOME liés au compte connecté.

    Cette page utilise RentalContract (le nouveau système de mise en location /
    sous-location), et non l'ancien modèle Contract utilisé par l'ancien menu
    « Mes contrats ».
    """
    contracts = (
        RentalContract.objects
        .select_related('rental_case', 'property', 'party', 'rental_case__owner', 'rental_case__tenant')
        .filter(party=request.user)
        .order_by('-updated_at')
    )

    return render(request, 'rental_contracts.html', {
        'contracts': contracts,
    })
