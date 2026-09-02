from decimal import Decimal, InvalidOperation
import math
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


LOCATION_ACCEPT_MATCH = 78.0
MIN_STRICT_RESULTS = 5
ADJACENT_RADIUS_KM = 10.0


def _clean(value):
    return (value or '').strip()


def _normalize_location(value):
    value = _clean(value)
    value = unicodedata.normalize('NFKD', value)
    value = ''.join(char for char in value if not unicodedata.combining(char))
    value = value.casefold().replace("'", ' ')
    value = re.sub(r'[-_/.,]+', ' ', value)
    return re.sub(r'\s+', ' ', value).strip()


def _location_similarity(requested, actual):
    requested_key = _normalize_location(requested)
    actual_key = _normalize_location(actual)
    if not requested_key or not actual_key or ratio is None:
        return 0.0
    if requested_key == actual_key:
        return 100.0
    return float(ratio(requested_key, actual_key))


def _location_match(requested, actual):
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


def _final_rent(prop):
    try:
        return Decimal(str(prop.rent or 0)) + Decimal(str(prop.margin or 0))
    except (TypeError, ValueError, InvalidOperation):
        return Decimal('0')


def _budget_score(prop, maximum, weight):
    """80-100% du budget est la zone idéale; le budget reste un plafond strict."""
    if maximum is None:
        return 0.0
    try:
        maximum = Decimal(str(maximum))
        rent = _final_rent(prop)
    except (TypeError, ValueError, InvalidOperation):
        return 0.0
    if maximum <= 0 or rent <= 0 or rent > maximum:
        return 0.0
    ratio_budget = float(rent / maximum)
    if ratio_budget >= 0.80:
        return float(weight)
    # Pénalité douce sous 80%, sans jamais rendre un bien compatible impossible.
    return float(weight) * (0.85 + 0.15 * (ratio_budget / 0.80))


def _bedroom_score(actual, requested, weight):
    """Le minimum est obligatoire; +1 chambre reste très bien classé."""
    if requested is None:
        return 0.0
    actual = int(actual or 0)
    if actual < requested:
        return 0.0
    if actual == requested:
        return float(weight)
    if actual == requested + 1:
        return float(weight) * 0.98
    return float(weight) * 0.94


def _salon_score(actual, requested, weight):
    if requested is None:
        return 0.0
    actual = int(actual or 0)
    if actual < requested:
        return 0.0
    if actual == requested:
        return float(weight)
    return float(weight) * 0.98


def _occupant_score(actual, requested, weight):
    if requested is None:
        return 0.0
    actual = int(actual or 0)
    if actual < requested:
        return 0.0
    return float(weight) if actual == requested else float(weight) * 0.98


def _haversine_km(lat1, lon1, lat2, lon2):
    try:
        lat1, lon1, lat2, lon2 = map(float, (lat1, lon1, lat2, lon2))
    except (TypeError, ValueError):
        return None
    radius = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return radius * 2 * math.asin(math.sqrt(min(1.0, a)))


def _commune_anchor(properties, criteria):
    """Centre approximatif de la commune demandé à partir des annonces géolocalisées."""
    points = []
    for prop in properties:
        if criteria['province'] and not _location_match(criteria['province'], prop.province or '')[1]:
            continue
        if criteria['city'] and not _location_match(criteria['city'], prop.city or '')[1]:
            continue
        if criteria['commune'] and not _location_match(criteria['commune'], prop.commune or '')[1]:
            continue
        if prop.latitude is not None and prop.longitude is not None:
            try:
                points.append((float(prop.latitude), float(prop.longitude)))
            except (TypeError, ValueError):
                pass
    if not points:
        return None
    return (
        sum(point[0] for point in points) / len(points),
        sum(point[1] for point in points) / len(points),
    )


def _hard_requirements(prop, criteria):
    """Budget, capacité et configuration minimale restent toujours stricts."""
    for field in ('province', 'city'):
        requested = criteria[field]
        if requested and not _location_match(requested, getattr(prop, field, ''))[1]:
            return False

    for criteria_field, property_field in (
        ('salons', 'salons'),
        ('bedrooms', 'bedrooms'),
        ('max_occupants', 'max_occupants'),
    ):
        requested = criteria[criteria_field]
        if requested is not None and int(getattr(prop, property_field, 0) or 0) < requested:
            return False

    if criteria['rent'] is not None:
        final_rent = _final_rent(prop)
        if final_rent <= 0 or final_rent > criteria['rent']:
            return False
    return True


def _strict_location_match(prop, criteria):
    if criteria['commune']:
        return _location_match(criteria['commune'], getattr(prop, 'commune', ''))[1]
    return True


def _is_eligible(prop, criteria, allow_fallback=False, anchor=None):
    if not _hard_requirements(prop, criteria):
        return False
    if _strict_location_match(prop, criteria):
        return True
    if not allow_fallback or not criteria['commune'] or not anchor:
        return False
    if prop.latitude is None or prop.longitude is None:
        return False
    distance = _haversine_km(anchor[0], anchor[1], prop.latitude, prop.longitude)
    return distance is not None and distance <= ADJACENT_RADIUS_KM


def _geographic_score(prop, criteria, fallback=False, anchor=None):
    checks = []
    for field, label, weight in (
        ('province', 'Province', 10.0),
        ('city', 'Ville / territoire', 15.0),
        ('commune', 'Commune / commune rurale', 15.0),
    ):
        requested = criteria[field]
        if not requested:
            continue
        actual = getattr(prop, field, '') or ''
        similarity, accepted = _location_match(requested, actual)
        points = weight * (similarity / 100.0)
        if field == 'commune' and fallback and not accepted:
            distance = _haversine_km(anchor[0], anchor[1], prop.latitude, prop.longitude) if anchor and prop.latitude is not None and prop.longitude is not None else None
            if distance is None:
                points = 0.0
            elif distance <= 3:
                points = weight * 0.90
            elif distance <= 6:
                points = weight * 0.80
            else:
                points = weight * 0.68
            checks.append((label, weight, points, False, similarity, requested, actual, distance))
        else:
            checks.append((label, weight, points, accepted, similarity, requested, actual, None))
    return checks


def matching_score(prop, criteria, fallback=False, anchor=None):
    checks = _geographic_score(prop, criteria, fallback=fallback, anchor=anchor)

    if criteria['salons'] is not None:
        actual = prop.salons or 0
        points = _salon_score(actual, criteria['salons'], 10.0)
        checks.append(('Salons', 10.0, points, actual >= criteria['salons'], None, criteria['salons'], actual, None))

    if criteria['bedrooms'] is not None:
        actual = prop.bedrooms or 0
        points = _bedroom_score(actual, criteria['bedrooms'], 15.0)
        checks.append(('Chambres', 15.0, points, actual >= criteria['bedrooms'], None, criteria['bedrooms'], actual, None))

    if criteria['max_occupants'] is not None:
        actual = prop.max_occupants or 0
        points = _occupant_score(actual, criteria['max_occupants'], 10.0)
        checks.append(('Occupants', 10.0, points, actual >= criteria['max_occupants'], None, criteria['max_occupants'], actual, None))

    if criteria['rent'] is not None:
        actual = _final_rent(prop)
        points = _budget_score(prop, criteria['rent'], 25.0)
        checks.append(('Loyer mensuel final', 25.0, points, actual <= criteria['rent'], None, criteria['rent'], actual, None))

    if not checks:
        return 0, []

    total_weight = sum(item[1] for item in checks)
    earned = sum(item[2] for item in checks)
    score = max(0, min(100, round((earned / total_weight) * 100)))
    breakdown = []
    for label, weight, points, ok, similarity, requested, actual, distance in checks:
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
        if distance is not None:
            item['distance_km'] = round(distance, 2)
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


def _matching_query(criteria):
    return urlencode({key: str(value) for key, value in criteria.items() if value not in ('', None)})


def _decorate(prop, criteria, fallback=False, anchor=None):
    score, breakdown = matching_score(prop, criteria, fallback=fallback, anchor=anchor)
    prop.ui_score = score
    prop.match_breakdown = breakdown
    prop.final_rent = _final_rent(prop)
    prop.matching_fallback = fallback
    prop.fallback_distance_km = None
    if fallback and anchor and prop.latitude is not None and prop.longitude is not None:
        prop.fallback_distance_km = _haversine_km(anchor[0], anchor[1], prop.latitude, prop.longitude)
    return prop


def search(request):
    criteria = _criteria_from_request(request)
    searched = any(value not in ('', None) for value in criteria.values())
    properties = []
    search_expanded = False
    strict_count = 0

    if searched:
        queryset = list(Property.objects.filter(status='published').prefetch_related('images'))
        matching_query = _matching_query(criteria)

        strict_properties = []
        for prop in queryset:
            if _is_eligible(prop, criteria, allow_fallback=False):
                strict_properties.append(_decorate(prop, criteria, fallback=False))

        strict_count = len(strict_properties)
        properties = strict_properties

        # Niveau 2 : si moins de 5 résultats exacts, élargissement géographique progressif.
        if strict_count < MIN_STRICT_RESULTS and criteria['commune']:
            anchor = _commune_anchor(queryset, criteria)
            if anchor:
                strict_ids = {prop.id for prop in strict_properties}
                expanded = []
                for prop in queryset:
                    if prop.id in strict_ids:
                        continue
                    if _is_eligible(prop, criteria, allow_fallback=True, anchor=anchor):
                        expanded.append(_decorate(prop, criteria, fallback=True, anchor=anchor))
                properties.extend(expanded)
                search_expanded = bool(expanded)

        properties.sort(key=lambda prop: (-prop.ui_score, prop.final_rent, prop.id))
        for prop in properties:
            prop.matching_url = f"{reverse('property_detail', args=[prop.pk])}?from_matching=1&fallback={'1' if prop.matching_fallback else '0'}&{matching_query}"

    return render(request, 'search.html', {
        'properties': properties,
        'searched': searched,
        'criteria': criteria,
        'search_expanded': search_expanded,
        'strict_count': strict_count,
        'min_strict_results': MIN_STRICT_RESULTS,
    })


def property_detail(request, pk):
    prop = get_object_or_404(Property.objects.prefetch_related('images'), pk=pk, status='published')
    prop.views += 1
    prop.save(update_fields=['views'])

    matching = request.GET.get('from_matching') == '1'
    fallback = request.GET.get('fallback') == '1'
    score = None
    match_breakdown = []
    match_criteria = None
    matching_query = ''
    matching_fallback = False

    if matching:
        criteria = _criteria_from_request(request)
        queryset = list(Property.objects.filter(status='published'))
        anchor = _commune_anchor(queryset, criteria) if criteria['commune'] else None
        if any(value not in ('', None) for value in criteria.values()) and _is_eligible(prop, criteria, allow_fallback=fallback, anchor=anchor):
            score, match_breakdown = matching_score(prop, criteria, fallback=fallback, anchor=anchor)
            if score > 0:
                match_criteria = criteria
                matching_query = _matching_query(criteria)
                matching_fallback = fallback
            else:
                score = None

    return render(request, 'property_detail.html', {
        'property': prop,
        'images': prop.images.all(),
        'score': score,
        'match_breakdown': match_breakdown,
        'match_criteria': match_criteria,
        'matching_query': matching_query,
        'matching_fallback': matching_fallback,
        'final_rent': _final_rent(prop),
    })
