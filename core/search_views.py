from decimal import Decimal, InvalidOperation
import re
import unicodedata
from urllib.parse import urlencode

from django.db import connection
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from .models import Property

try:
    from rapidfuzz.fuzz import ratio
except ImportError:  # pragma: no cover
    ratio = None

LOCATION_ACCEPT_MATCH = 78.0
MIN_RESULTS_BEFORE_FALLBACK = 5
ADJACENT_COMMUNE_SCORE = 0.72


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


def _rent_score(prop, maximum, weight):
    if maximum is None:
        return 0.0
    try:
        maximum = Decimal(str(maximum))
        final_rent = _final_rent(prop)
    except (TypeError, ValueError, InvalidOperation):
        return 0.0
    if final_rent <= 0 or maximum <= 0 or final_rent > maximum:
        return 0.0
    budget_ratio = float(final_rent / maximum)
    if budget_ratio >= 0.80:
        return float(weight)
    return float(weight) * (0.85 + 0.15 * (budget_ratio / 0.80))


def _bedroom_score(actual, requested, weight):
    if requested is None:
        return 0.0
    actual = int(actual or 0)
    requested = int(requested)
    if actual < requested:
        return 0.0
    delta = actual - requested
    if delta == 1:
        return float(weight)
    if delta == 0:
        return float(weight) * 0.98
    if delta == 2:
        return float(weight) * 0.97
    return float(weight) * 0.94


def matching_score(prop, criteria, spatial_level='exact'):
    checks = []
    location_penalty = ADJACENT_COMMUNE_SCORE if spatial_level == 'adjacent' else 1.0
    for field, label, weight in (('province', 'Province', 10.0), ('city', 'Ville / territoire', 15.0), ('commune', 'Commune / commune rurale', 15.0)):
        requested = criteria[field]
        if requested:
            actual = getattr(prop, field, '') or ''
            similarity, accepted = _location_match(requested, actual)
            points = weight * (similarity / 100.0)
            if field == 'commune' and spatial_level == 'adjacent':
                points = weight * location_penalty
                accepted = True
                similarity = location_penalty * 100
            checks.append((label, weight, points, accepted, similarity, requested, actual))
    if criteria['salons'] is not None:
        checks.append(('Salons', 10.0, 10.0, True, None, criteria['salons'], prop.salons or 0))
    if criteria['bedrooms'] is not None:
        checks.append(('Chambres', 15.0, _bedroom_score(prop.bedrooms or 0, criteria['bedrooms'], 15.0), True, None, criteria['bedrooms'], prop.bedrooms or 0))
    if criteria['max_occupants'] is not None:
        checks.append(('Occupants', 10.0, 10.0, True, None, criteria['max_occupants'], prop.max_occupants or 0))
    if criteria['rent'] is not None:
        checks.append(('Loyer mensuel final', 25.0, _rent_score(prop, criteria['rent'], 25.0), True, None, criteria['rent'], _final_rent(prop)))
    if not checks:
        return 0, []
    total_weight = sum(weight for _, weight, *_ in checks)
    earned = sum(points for _, _, points, *_ in checks)
    score = max(0, min(100, round((earned / total_weight) * 100)))
    breakdown = []
    for label, weight, points, ok, similarity, requested, actual in checks:
        item = {'label': label, 'earned': round(points, 1), 'weight': round(weight, 1), 'ok': ok, 'requested': requested, 'actual': actual}
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


def _hard_requirements(prop, criteria, allow_adjacent=False, adjacent_names=None):
    for field in ('province', 'city'):
        requested = criteria[field]
        if requested:
            _, accepted = _location_match(requested, getattr(prop, field, ''))
            if not accepted:
                return False
    requested_commune = criteria['commune']
    if requested_commune:
        _, exact = _location_match(requested_commune, getattr(prop, 'commune', ''))
        if not exact and not (allow_adjacent and _normalize_location(getattr(prop, 'commune', '')) in (adjacent_names or set())):
            return False
    for criteria_field, property_field in (('salons', 'salons'), ('bedrooms', 'bedrooms'), ('max_occupants', 'max_occupants')):
        requested = criteria[criteria_field]
        if requested is not None and int(getattr(prop, property_field, 0) or 0) < requested:
            return False
    if criteria['rent'] is not None:
        final_rent = _final_rent(prop)
        if final_rent <= 0 or final_rent > criteria['rent']:
            return False
    return True


def _postgis_available():
    if connection.vendor != 'postgresql':
        return False
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema=current_schema() AND table_name='core_administrativearea')
            """)
            return bool(cursor.fetchone()[0])
    except Exception:
        return False


def _adjacent_communes(requested, province='', city=''):
    """Résout une commune fuzzy puis retourne uniquement ses voisines réelles."""
    requested_key = _normalize_location(requested)
    if not requested_key or not _postgis_available():
        return set()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id, name
                FROM core_administrativearea
                WHERE level='commune' AND geom IS NOT NULL
                  AND (%s='' OR lower(trim(province_name))=lower(trim(%s)))
                  AND (%s='' OR lower(trim(city_name))=lower(trim(%s)))
            """, [province, province, city, city])
            candidates = cursor.fetchall()
            if not candidates:
                return set()
            ranked = sorted(candidates, key=lambda row: _location_similarity(requested, row[1]), reverse=True)
            best = ranked[0]
            if _location_similarity(requested, best[1]) < LOCATION_ACCEPT_MATCH:
                return set()
            cursor.execute("""
                SELECT DISTINCT a2.name
                FROM core_administrativearea a1
                JOIN core_administrativearea a2
                  ON a2.level='commune' AND a2.geom IS NOT NULL
                 AND ST_Touches(a1.geom,a2.geom)
                 AND lower(trim(a2.province_name))=lower(trim(a1.province_name))
                 AND lower(trim(a2.city_name))=lower(trim(a1.city_name))
                WHERE a1.id=%s
            """, [best[0]])
            return {_normalize_location(row[0]) for row in cursor.fetchall() if row[0]}
    except Exception:
        return set()


def _matching_query(criteria):
    return urlencode({key: str(value) for key, value in criteria.items() if value not in ('', None)})


def search(request):
    criteria = _criteria_from_request(request)
    searched = any(value not in ('', None) for value in criteria.values())
    properties = []
    fallback_used = False
    fallback_count = 0
    exact_count = 0
    if searched:
        queryset = list(Property.objects.filter(status='published').prefetch_related('images'))
        exact = []
        for prop in queryset:
            if _hard_requirements(prop, criteria):
                score, breakdown = matching_score(prop, criteria, 'exact')
                if score > 0:
                    prop.ui_score = score
                    prop.match_breakdown = breakdown
                    prop.final_rent = _final_rent(prop)
                    prop.match_spatial_level = 'exact'
                    exact.append(prop)
        exact_count = len(exact)
        properties = exact[:]
        if len(properties) < MIN_RESULTS_BEFORE_FALLBACK and criteria['commune']:
            adjacent_names = _adjacent_communes(criteria['commune'], criteria['province'], criteria['city'])
            if adjacent_names:
                seen = {p.pk for p in properties}
                for prop in queryset:
                    if prop.pk in seen:
                        continue
                    if not _hard_requirements(prop, criteria, allow_adjacent=True, adjacent_names=adjacent_names):
                        continue
                    if _normalize_location(getattr(prop, 'commune', '')) not in adjacent_names:
                        continue
                    score, breakdown = matching_score(prop, criteria, 'adjacent')
                    if score <= 0:
                        continue
                    prop.ui_score = score
                    prop.match_breakdown = breakdown
                    prop.final_rent = _final_rent(prop)
                    prop.match_spatial_level = 'adjacent'
                    properties.append(prop)
                    seen.add(prop.pk)
                fallback_count = len(properties) - exact_count
                fallback_used = fallback_count > 0
        matching_query = _matching_query(criteria)
        for prop in properties:
            prop.matching_url = f"{reverse('property_detail', args=[prop.pk])}?from_matching=1&spatial_level={prop.match_spatial_level}&{matching_query}"
        properties.sort(key=lambda prop: (-prop.ui_score, 0 if prop.match_spatial_level == 'exact' else 1, prop.final_rent, prop.id))
    return render(request, 'search.html', {
        'properties': properties,
        'searched': searched,
        'criteria': criteria,
        'fallback_used': fallback_used,
        'fallback_count': fallback_count,
        'exact_count': exact_count,
        'postgis_ready': _postgis_available(),
    })


def property_detail(request, pk):
    prop = get_object_or_404(Property.objects.prefetch_related('images'), pk=pk, status='published')
    prop.views += 1
    prop.save(update_fields=['views'])
    matching = request.GET.get('from_matching') == '1'
    score = None
    match_breakdown = []
    match_criteria = None
    matching_query = ''
    spatial_level = request.GET.get('spatial_level', 'exact')
    if matching:
        criteria = _criteria_from_request(request)
        adjacent_names = _adjacent_communes(criteria['commune'], criteria['province'], criteria['city']) if spatial_level == 'adjacent' else set()
        if any(value not in ('', None) for value in criteria.values()) and _hard_requirements(prop, criteria, allow_adjacent=spatial_level == 'adjacent', adjacent_names=adjacent_names):
            if spatial_level != 'adjacent' or _normalize_location(getattr(prop, 'commune', '')) in adjacent_names:
                score, match_breakdown = matching_score(prop, criteria, spatial_level)
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
        'match_spatial_level': spatial_level,
    })
