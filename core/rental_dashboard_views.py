from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render

from .models import Notification, Payment, Property, Visit
from .rental_models import RentalCase, RentalContract


def _links():
    return [
        ('⌂', 'Tableau de bord', 'dashboard'),
        ('⌕', 'Rechercher', 'search'),
        ('♡', 'Mes favoris', 'favorites'),
        ('▣', 'Mes publications', 'publications'),
        ('◷', 'Mes demandes de visite', 'visits'),
        ('▤', 'Mes contrats', 'contracts'),
        ('◉', 'Mes paiements', 'payments'),
        ('◴', 'Mes échéances', 'due_dates'),
        ('●', 'Messages', 'messages'),
        ('♢', 'Notifications', 'notifications'),
        ('⚙', 'Mon profil', 'profile'),
    ]


@login_required
def dashboard(request):
    user = request.user

    properties = Property.objects.filter(owner=user).order_by('-updated_at')
    visits = Visit.objects.filter(requester=user).select_related('property').order_by('-created_at')[:5]

    # The personal space must use the rental contract system, not the legacy Contract model.
    rental_contracts = (
        RentalContract.objects
        .filter(party=user)
        .select_related('property', 'rental_case')
        .order_by('-updated_at')
    )

    active_rentals = (
        RentalCase.objects
        .filter(status='active')
        .filter(Q(owner=user) | Q(tenant=user))
        .select_related('property', 'owner', 'tenant', 'owner_contract', 'tenant_contract')
        .order_by('-updated_at')
    )

    payments = (
        Payment.objects
        .filter(contract__user=user)
        .select_related('contract__property')
        .order_by('due_date')[:5]
    )
    notifications = Notification.objects.filter(user=user).order_by('-created_at')[:6]

    return render(request, 'dashboard.html', {
        'links': _links(),
        'properties': properties,
        'visits': visits,
        'contracts': rental_contracts,
        'active_rentals': active_rentals,
        'payments': payments,
        'notifications': notifications,
    })
