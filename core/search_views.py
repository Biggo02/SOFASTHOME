from decimal import Decimal, InvalidOperation

from django.shortcuts import get_object_or_404, render

from .models import Property


def _clean(value):
    return (value or '').strip()


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_decimal(value):
    try:
        return Decimal(value)
    except (TypeError, ValueError, InvalidOperation):
        return None


def matching_score(prop, criteria):
    """Calculate a score only from criteria explicitly supplied by the user."""
    checks = []

    if criteria['province']:
        checks.append(('Province', 15, prop.province.strip().lower() == criteria['province'].lower()))
    if criteria['city']:
        checks.append(('Ville / territoire', 15, prop.city.strip().lower() == criteria['city'].lower()))
    if criteria['commune']:
        checks.append(('Commune / commune rurale', 15, prop.commune.strip().lower() == criteria['commune'].lower()))
    if criteria['salons'] is not None:
        checks.append(('Salons', 15, prop.salons >= criteria['salons']))
    if criteria['bedrooms'] is not None:
        checks.append(('Chambres', 15, prop.bedrooms >= criteria['bedrooms']))
    if criteria['max_occupants'] is not None:
        checks.append(('Occupants', 10, prop.max_occupants >= criteria['max_occupants']))
    if criteria['rent'] is not None:
        checks.append(('Loyer mensuel', 15, Decimal(str(prop.rent)) <= criteria['rent']))

    if not checks:
        return 0, []

    total_weight = sum(weight for _, weight, _ in checks)
    earned = sum(weight for _, weight, ok in checks if ok)
    score = round((earned / total_weight) * 100)
    breakdown = [
        {'label': label, 'earned': weight if ok else 0, 'weight': weight, 'ok': ok}
        for label, weight, ok in checks
    ]
    return score, breakdown


def search(request):
    criteria = {
        'province': _clean(request.GET.get('province')),
        'city': _clean(request.GET.get('city')),
        'commune': _clean(request.GET.get('commune')),
        'salons': _to_int(request.GET.get('salons')),
        'bedrooms': _to_int(request.GET.get('bedrooms')),
        'max_occupants': _to_int(request.GET.get('max_occupants')),
        'rent': _to_decimal(request.GET.get('rent')),
    }
    searched = any(value not in ('', None) for value in criteria.values())
    properties = []

    if searched:
        for prop in Property.objects.filter(status='published').prefetch_related('images'):
            score, breakdown = matching_score(prop, criteria)
            prop.ui_score = score
            prop.match_breakdown = breakdown
            properties.append(prop)
        properties.sort(key=lambda prop: prop.ui_score, reverse=True)
        properties = [prop for prop in properties if prop.ui_score > 0]

    return render(request, 'search.html', {
        'properties': properties,
        'searched': searched,
        'criteria': criteria,
    })


def property_detail(request, pk):
    prop = get_object_or_404(
        Property.objects.prefetch_related('images'),
        pk=pk,
        status='published',
    )
    prop.views += 1
    prop.save(update_fields=['views'])

    context = {'property': prop, 'images': prop.images.all()}

    if request.GET.get('matching') == '1':
        criteria = {
            'province': _clean(request.GET.get('province')),
            'city': _clean(request.GET.get('city')),
            'commune': _clean(request.GET.get('commune')),
            'salons': _to_int(request.GET.get('salons')),
            'bedrooms': _to_int(request.GET.get('bedrooms')),
            'max_occupants': _to_int(request.GET.get('max_occupants')),
            'rent': _to_decimal(request.GET.get('rent')),
        }
        score, breakdown = matching_score(prop, criteria)
        if any(value not in ('', None) for value in criteria.values()):
            context['score'] = score
            context['match_breakdown'] = breakdown

    return render(request, 'property_detail.html', context)
