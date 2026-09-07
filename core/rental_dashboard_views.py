from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render

from .models import Notification, Payment, Property, Visit
from .rental_models import RentalCase, RentalContract


def _links(user, has_tenant_activity):
    primary = [
        ('⌂', 'Tableau de bord', 'dashboard'),
        ('⌕', 'Rechercher un logement', 'search'),
        ('♡', 'Mes favoris', 'favorites'),
        ('◷', 'Mes visites', 'visits'),
    ]
    owner = []
    if Property.objects.filter(owner=user).exists():
        owner = [('▣', 'Mes biens', 'publications'), ('✓', 'Demandes reçues', 'owner_visit_requests')]
    tenant = []
    if has_tenant_activity:
        tenant = [('▤', 'Mes contrats', 'contracts'), ('◉', 'Mes paiements', 'payments'), ('◴', 'Mes échéances', 'due_dates')]
    common = [('♢', 'Notifications', 'notifications'), ('⚙', 'Mon profil', 'profile')]
    return primary, owner, tenant, common


@login_required
def dashboard(request):
    user = request.user
    properties = Property.objects.filter(owner=user).order_by('-updated_at')
    visits = Visit.objects.filter(requester=user).select_related('property').order_by('-created_at')[:5]
    owner_visits = Visit.objects.filter(property__owner=user).select_related('property', 'requester').order_by('-created_at')[:5]
    rental_contracts = RentalContract.objects.filter(party=user).select_related('property', 'rental_case').order_by('-updated_at')
    active_rentals = (
        RentalCase.objects.filter(status='active')
        .filter(Q(owner=user) | Q(tenant=user))
        .select_related('property', 'owner', 'tenant', 'owner_contract', 'tenant_contract')
        .order_by('-updated_at')
    )
    payments = Payment.objects.filter(contract__user=user).select_related('contract__property').order_by('due_date')[:5]
    notifications = Notification.objects.filter(user=user).order_by('-created_at')[:6]

    has_tenant_activity = rental_contracts.exists() or active_rentals.filter(tenant=user).exists()
    primary_links, owner_links, tenant_links, common_links = _links(user, has_tenant_activity)

    pending_contracts = rental_contracts.filter(status__in=['draft', 'prepared', 'pending_signature']).count()
    validated_contracts = rental_contracts.filter(status='validated').count()

    return render(request, 'dashboard.html', {
        'primary_links': primary_links,
        'owner_links': owner_links,
        'tenant_links': tenant_links,
        'common_links': common_links,
        'properties': properties,
        'visits': visits,
        'owner_visits': owner_visits,
        'contracts': rental_contracts,
        'active_rentals': active_rentals,
        'payments': payments,
        'notifications': notifications,
        'has_owner_activity': bool(owner_links),
        'has_tenant_activity': has_tenant_activity,
        'pending_contracts': pending_contracts,
        'validated_contracts': validated_contracts,
    })
