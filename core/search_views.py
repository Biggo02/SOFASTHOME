from decimal import Decimal, InvalidOperation

from django.shortcuts import get_object_or_404, render

from .models import Property


def _clean(value):
    return (value or '').strip()


def _to_int(value):
    try:
        number = int(value)
        return number if number >= 0 else None
    except (TypeError, ValueError):
        return None


def _to_decimal(value):
    try:
        number = Decimal(value)
        return number if number >= 0 else None
    except (TypeError, ValueError, InvalidOperation):
        return None


def _text_match(actual, requested):
    return bool(actual and requested and actual.strip().casefold() == requested.strip().casefold())


def _minimum_value_score(actual, requested, weight):
    if requested is None:
        return 0.0
    try:
        actual = Decimal(str(actual or 0))
        requested = Decimal(str(requested))
    except (TypeError, ValueError, InvalidOperation):
        return 0.0
    if requested <= 0 or actual >= requested:
        return float(weight)
    return float(weight) * max(0.0, float(actual / requested))


def _rent_score(actual, maximum, weight):
    if maximum is None:
        return 0.0
    try:
        actual = Decimal(str(actual or 0))
        maximum = Decimal(str(maximum))
    except (TypeError, ValueError, InvalidOperation):
        return 0.0
    if actual <= 0 or maximum <= 0:
        return 0.0
    if actual <= maximum:
        return float(weight)
    excess_ratio = (actual - maximum) / maximum
    return float(weight) * max(0.0, 1.0 - float(excess_ratio))


def matching_score(prop, criteria):
    """Transparent 0-100 score using only the seven search criteria."""
    checks = []
    if criteria['province']:
        checks.append(('Province', 10.0, 10.0 if _text_match(prop.province, criteria['province']) else 0.0))
    if criteria['city']:
        checks.append(('Ville / territoire', 15.0, 15.0 if _text_match(prop.city, criteria['city']) else 0.0))
    if criteria['commune']:
        checks.append(('Commune / commune rurale', 15.0, 15.0 if _text_match(prop.commune, criteria['commune']) else 0.0))
    if criteria['salons'] is not None:
        checks.append(('Salons', 10.0, _minimum_value_score(prop.salons, criteria['salons'], 10.0)))
    if criteria['bedrooms'] is not None:
        checks.append(('Chambres', 15.0, _minimum_value_score(prop.bedrooms, criteria['bedrooms'], 15.0)))
    if criteria['max_occupants'] is not None:
        checks.append(('Occupants', 10.0, _minimum_value_score(prop.max_occupants, criteria['max_occupants'], 10.0)))
    if criteria['rent'] is not None:
        checks.append(('Loyer mensuel', 15.0, _rent_score(prop.rent, criteria['rent'], 15.0)))
    if not checks:
        return 0, []
    total_weight = sum(weight for _, weight, _ in checks)
    earned = sum(points for _, _, points in checks)
    score = max(0, min(100, round((earned / total_weight) * 100)))
    breakdown = [
        {'label': label, 'earned': round(points, 1), 'weight': round(weight, 1), 'ok': points >= weight}
        for label, weight, points in checks
    ]
    return score, breakdown


def _criteria_from_request(request):
    return {
        'province': _clean(request.GET.get('province')),
        'city': _clean(request.GET.get('city')),
        'commune': _clean(request.GET.get('commune')),
        'salons': _to_int(request.GET.get('salons')),
        'bedrooms': _to_int(request.GET.get('bedrooms')),
        'max_occupants': _to_int(request.GET.get('max_occupants')),
        'rent': _to_decimal(request.GET.get('rent')),
    }


def _location_is_compatible(prop, criteria):
    if criteria['province'] and not _text_match(prop.province, criteria['province']):
        return False
    if criteria['city'] and not _text_match(prop.city, criteria['city']):
        return False
    if criteria['commune'] and not _text_match(prop.commune, criteria['commune']):
        return False
    return True


def search(request):
    criteria = _criteria_from_request(request)
    searched = any(value not in ('', None) for value in criteria.values())
    properties = []
    if searched:
        for prop in Property.objects.filter(status='published').prefetch_related('images'):
            if not _location_is_compatible(prop, criteria):
                continue
            score, breakdown = matching_score(prop, criteria)
            if score <= 0:
                continue
            prop.ui_score = score
            prop.match_breakdown = breakdown
            properties.append(prop)
        properties.sort(key=lambda prop: (-prop.ui_score, prop.rent, prop.id))
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
    return render(request, 'property_detail.html', {
        'property': prop,
        'images': prop.images.all(),
    })
