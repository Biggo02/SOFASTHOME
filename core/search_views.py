from decimal import Decimal, InvalidOperation
import re
import unicodedata
from urllib.parse import urlencode

from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from .models import Property

try:
    from rapidfuzz.fuzz import ratio
except ImportError:  # pragma: no cover
    ratio = None


# Seuil élevé pour accepter uniquement les fautes de frappe suffisamment proches.
LOCATION_ACCEPT_MATCH = 78.0


def _clean(value):
    return (value or '').strip()


def _normalize_location(value):
    """Normalise un nom géographique avant la comparaison fuzzy."""
    value = _clean(value)
    value = unicodedata.normalize('NFKD', value)
    value = ''.join(char for char in value if not unicodedata.combining(char))
    value = value.casefold().replace("'", ' ')
    value = re.sub(r'[-_/.,]+', ' ', value)
    value = re.sub(r'\s+', ' ', value).strip()
    return value


def _location_similarity(requested, actual):
    """Retourne un score fuzzy 0-100 pour une localisation."""
    requested_key = _normalize_location(requested)
    actual_key = _normalize_location(actual)
    if not requested_key or not actual_key or ratio is None:
        return 0.0
    if requested_key == actual_key:
        return 100.0
    return float(ratio(requested_key, actual_key))


def _location_match(requested, actual):
    """Renvoie (score, accepté) selon la similarité fuzzy."""
    score = _location_similarity(requested, actual)
    return score, score >= LOCATION_ACCEPT_MATCH


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


def _final_rent(prop):
    """Loyer présenté au demandeur = loyer propriétaire + marge FASTHOME."""
    try:
        rent = Decimal(str(prop.rent or 0))
        margin = Decimal(str(prop.margin or 0))
        return rent + margin
    except (TypeError, ValueError, InvalidOperation):
        return Decimal('0')


def _rent_score(prop, maximum, weight):
    """Le budget est binaire : au-dessus du maximum = incompatible."""
    if maximum is None:
        return 0.0
    try:
        maximum = Decimal(str(maximum))
        final_rent = _final_rent(prop)
    except (TypeError, ValueError, InvalidOperation):
        return 0.0
    if final_rent <= 0 or maximum <= 0:
        return 0.0
    return float(weight) if final_rent <= maximum else 0.0


def matching_score(prop, criteria):
    """Score transparent 0-100 basé uniquement sur les 7 critères de recherche."""
    checks = []

    for field, label, weight in (
        ('province', 'Province', 10.0),
        ('city', 'Ville / territoire', 15.0),
        ('commune', 'Commune / commune rurale', 15.0),
    ):
        requested = criteria[field]
        if requested:
            actual = getattr(prop, field, '') or ''
            location_score, accepted = _location_match(requested, actual)
            checks.append((label, weight, weight * (location_score / 100.0), accepted, location_score, requested, actual))

    if criteria['salons'] is not None:
        actual = prop.salons or 0
        points = _minimum_value_score(actual, criteria['salons'], 10.0)
        checks.append(('Salons', 10.0, points, points >= 10.0, None, criteria['salons'], actual))

    if criteria['bedrooms'] is not None:
        actual = prop.bedrooms or 0
        points = _minimum_value_score(actual, criteria['bedrooms'], 15.0)
        checks.append(('Chambres', 15.0, points, points >= 15.0, None, criteria['bedrooms'], actual))

    if criteria['max_occupants'] is not None:
        actual = prop.max_occupants or 0
        points = _minimum_value_score(actual, criteria['max_occupants'], 10.0)
        checks.append(('Occupants', 10.0, points, points >= 10.0, None, criteria['max_occupants'], actual))

    if criteria['rent'] is not None:
        actual = _final_rent(prop)
        points = _rent_score(prop, criteria['rent'], 25.0)
        checks.append(('Loyer mensuel final', 25.0, points, points >= 25.0, None, criteria['rent'], actual))

    if not checks:
        return 0, []

    total_weight = sum(weight for _, weight, *_ in checks)
    earned = sum(points for _, _, points, *_ in checks)
    score = max(0, min(100, round((earned / total_weight) * 100)))

    breakdown = []
    for label, weight, points, ok, similarity, requested, actual in checks:
        item = {
            'label': label,
            'earned': round(points, 1),
            'weight': round(weight, 1),
            'ok': ok,
            'requested': requested,
            'actual': actual,
        }
        if similarity is not None:
            item['similarity'] = round(similarity, 1)
        breakdown.append(item)
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


def _is_eligible(prop, criteria):
    """Filtres durs : localisation, nombre minimal de pièces/occupants et budget."""
    for field in ('province', 'city', 'commune'):
        requested = criteria[field]
        if requested:
            _, accepted = _location_match(requested, getattr(prop, field, ''))
            if not accepted:
                return False

    # Les quantités demandées sont des exigences minimales.
    # Un bien avec moins de salons, chambres ou capacité d'occupants
    # que ce qui est demandé ne doit donc pas apparaître dans les résultats.
    numeric_requirements = (
        ('salons', 'salons'),
        ('bedrooms', 'bedrooms'),
        ('max_occupants', 'max_occupants'),
    )
    for criteria_field, property_field in numeric_requirements:
        requested = criteria[criteria_field]
        if requested is not None:
            try:
                actual = int(getattr(prop, property_field, 0) or 0)
            except (TypeError, ValueError):
                actual = 0
            if actual < requested:
                return False

    # Le budget demandé est un plafond réel : un bien au-dessus est exclu.
    if criteria['rent'] is not None:
        final_rent = _final_rent(prop)
        if final_rent <= 0 or final_rent > criteria['rent']:
            return False

    return True


def _matching_query(criteria):
    """Construit le contexte de recherche à conserver en ouvrant un bien."""
    params = {}
    for key, value in criteria.items():
        if value not in ('', None):
            params[key] = str(value)
    return urlencode(params)


def search(request):
    criteria = _criteria_from_request(request)
    searched = any(value not in ('', None) for value in criteria.values())
    properties = []

    if searched:
        queryset = Property.objects.filter(status='published').prefetch_related('images')
        matching_query = _matching_query(criteria)
        for prop in queryset:
            if not _is_eligible(prop, criteria):
                continue
            score, breakdown = matching_score(prop, criteria)
            if score <= 0:
                continue
            prop.ui_score = score
            prop.match_breakdown = breakdown
            prop.final_rent = _final_rent(prop)
            prop.matching_url = f"{reverse('property_detail', args=[prop.pk])}?from_matching=1&{matching_query}"
            properties.append(prop)

        properties.sort(key=lambda prop: (-prop.ui_score, prop.final_rent, prop.id))

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

    matching = request.GET.get('from_matching') == '1'
    score = None
    match_breakdown = []
    match_criteria = None
    matching_query = ''

    if matching:
        criteria = _criteria_from_request(request)
        if any(value not in ('', None) for value in criteria.values()) and _is_eligible(prop, criteria):
            score, match_breakdown = matching_score(prop, criteria)
            if score > 0:
                match_criteria = criteria
                matching_query = _matching_query(criteria)
            else:
                score = None

    return render(request, 'property_detail.html', {
        'property': prop,
        'images': prop.images.all(),
        'score': score,
        'match_breakdown': match_breakdown,
        'match_criteria': match_criteria,
        'matching_query': matching_query,
        'final_rent': _final_rent(prop),
    })
