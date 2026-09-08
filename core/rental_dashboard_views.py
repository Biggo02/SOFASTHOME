from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render

from .models import Notification, Payment, Property, Visit
from .rental_models import RentalCase, RentalContract


def _links(user, has_tenant_activity):
    # The personal space has the same navigation for every account.
    # What appears inside each section is filtered by the user's rights/data.
    primary = [
        ('⌂', 'Tableau de bord', 'dashboard'),
        ('⌕', 'Rechercher un logement', 'search'),
        ('♡', 'Mes favoris', 'favorites'),
        ('◷', 'Mes visites', 'visits'),
    ]
    owner = [('▣', 'Mes biens', 'publications'), ('✓', 'Demandes reçues', 'owner_visit_requests')]
    tenant = [('▤', 'Mes contrats', 'contracts'), ('◉', 'Mes paiements', 'payments'), ('◴', 'Mes échéances', 'due_dates')]
    common = [('⚙', 'Mon profil', 'profile')]
    return primary, owner, tenant, common


@login_required
def dashboard(request):
    user = request.user

    properties = Property.objects.filter(owner=user).prefetch_related('images').order_by('-updated_at')
    draft_properties = properties.filter(status='draft')
    review_properties = properties.filter(status='review')
    available_properties = properties.filter(status='published')
    rented_properties = properties.filter(status='rented')

    # Only requests that still require an action are displayed. A completed,
    # rejected or cancelled visit therefore disappears from this dashboard.
    active_visit_statuses = ['pending', 'confirmed']
    owner_visit_requests = (
        Visit.objects.filter(property__owner=user, status__in=active_visit_statuses)
        .select_related('property', 'requester')
        .order_by('preferred_date', 'preferred_time', '-created_at')
    )
    my_visit_requests = (
        Visit.objects.filter(requester=user, status__in=active_visit_statuses)
        .select_related('property', 'property__owner')
        .order_by('preferred_date', 'preferred_time', '-created_at')
    )

    rental_contracts = (
        RentalContract.objects.filter(party=user)
        .select_related('property', 'rental_case')
        .order_by('-updated_at')
    )
    tenant_rental_contracts = rental_contracts.filter(contract_type='tenant_sublease')

    active_rentals = (
        RentalCase.objects.filter(status='active')
        .filter(Q(owner=user) | Q(tenant=user))
        .select_related('property', 'owner', 'tenant', 'owner_contract', 'tenant_contract')
        .order_by('-updated_at')
    )

    # Keep the legacy payment module compatible while limiting the personal
    # space to payments belonging to tenant contracts.
    tenant_payments = (
        Payment.objects.filter(contract__user=user, contract__role='tenant')
        .select_related('contract__property')
        .prefetch_related('proofs')
        .order_by('due_date')
    )

    # IMPORTANT: the layout is identical for every account.  We therefore do
    # not hide the owner/tenant sections according to activity.  Empty sections
    # simply show their empty state, while the underlying queries remain
    # strictly scoped to the logged-in user.
    has_owner_activity = True
    has_tenant_activity = True
    primary_links, owner_links, tenant_links, common_links = _links(user, has_tenant_activity)

    pending_contracts = tenant_rental_contracts.filter(status__in=['draft', 'prepared', 'pending_signature']).count()
    validated_contracts = tenant_rental_contracts.filter(status='validated').count()

    return render(request, 'dashboard.html', {
        'primary_links': primary_links,
        'owner_links': owner_links,
        'tenant_links': tenant_links,
        'common_links': common_links,
        'properties': properties,
        'draft_properties': draft_properties,
        'review_properties': review_properties,
        'available_properties': available_properties,
        'rented_properties': rented_properties,
        'property_counts': {
            'draft': draft_properties.count(),
            'review': review_properties.count(),
            'available': available_properties.count(),
            'rented': rented_properties.count(),
        },
        'owner_visit_requests': owner_visit_requests,
        'owner_visit_count': owner_visit_requests.count(),
        'my_visit_requests': my_visit_requests,
        'my_visit_count': my_visit_requests.count(),
        'visits': my_visit_requests[:5],
        'rental_contracts': rental_contracts,
        'tenant_rental_contracts': tenant_rental_contracts,
        'tenant_contract_count': tenant_rental_contracts.count(),
        'active_rentals': active_rentals,
        'payments': tenant_payments[:5],
        'tenant_payments': tenant_payments,
        'tenant_payment_count': tenant_payments.count(),
        'next_payment': tenant_payments.filter(status__in=['upcoming', 'partial', 'late']).first(),
        'notifications': Notification.objects.filter(user=user).order_by('-created_at')[:6],
        'has_owner_activity': has_owner_activity,
        'has_tenant_activity': has_tenant_activity,
        'pending_contracts': pending_contracts,
        'validated_contracts': validated_contracts,
    })
