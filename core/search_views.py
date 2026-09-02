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

LOCATION_ACCEPT_MATCH = 78.0


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
    if not requested_key or not actual_key:
        return 0.0
    if requested_key == actual_key:
        return 100.0
    if ratio is None:
        return 0.0
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


def matching_score(prop, criteria):
    checks = []
    for field, label, weight in (
        ('province', 'Province', 10.0),
        ('city', 'Ville / territoire', 15.0),
        ('commune', 'Commune / commune rurale', 15.0),
    ):
        requested = criteria[field]
        if requested:
            actual = getattr(prop, field, '') or ''
            similarity, accepted = _location_match(requested, actual)
            points = weight * (similarity / 100.0)
            checks.append((label, weight, points, accepted, similarity, requested, actual))

    if criteria['salons'] is not None:
        actual = int(prop.salons or 0)
        requested = int(criteria['salons'])
        checks.append(('Salons', 10.0, 10.0, actual >= requested, None, requested, actual))
    if criteria['bedrooms'] is not None:
        checks.append(('Chambres', 15.0, _bedroom_score(prop.bedrooms or 0, criteria['bedrooms'], 15.0), True, None, criteria['bedrooms'], prop.bedrooms or 0))
    if criteria['max_occupants'] is not None:
        actual = int(prop.max_occupants or 0)
        requested = int(criteria['max_occupants'])
        checks.append(('Occupants', 10.0, 10.0, actual >= requested, None, requested, actual))
    if criteria['rent'] is not None:
        checks.append(('Loyer mensuel final', 25.0, _rent_score(prop, criteria['rent'], 25.0), True, None, criteria['rent'], _final_rent(prop)))

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


def _hard_requirements(prop, criteria):
    for field in ('province', 'city', 'commune'):
        requested = criteria[field]
        if requested:
            _, accepted = _location_match(requested, getattr(prop, field, ''))
            if not accepted:
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


def _matching_query(criteria):
    return urlencode({key: str(value) for key, value in criteria.items() if value not in ('', None)})


def _format_fc(value):
    try:
        return f'{Decimal(str(value)):,.0f}'.replace(',', ' ')
    except (TypeError, ValueError, InvalidOperation):
        return str(value)


def build_matching_explanation(prop, criteria):
    """Construit un paragraphe éditorial à partir uniquement des critères réellement saisis."""
    parts = []

    if criteria['province'] and criteria['city'] and criteria['commune']:
        parts.append(
            f"Ce bien correspond d'abord à votre recherche sur le plan géographique : il se trouve dans la province de {prop.province}, "
            f"à {prop.city}, précisément dans la commune de {prop.commune}, ce qui correspond à la localisation que vous avez sélectionnée."
        )
    elif criteria['province'] or criteria['city'] or criteria['commune']:
        location_bits = []
        for key, label in (('province', 'la province'), ('city', 'la ville / le territoire'), ('commune', 'la commune')):
            if criteria[key]:
                location_bits.append(f"{label} de {getattr(prop, key, '')}")
        parts.append("Sur le plan géographique, ce bien respecte " + ", ".join(location_bits) + ", conformément à votre recherche.")

    if criteria['salons'] is not None:
        requested = criteria['salons']
        actual = int(prop.salons or 0)
        if actual == requested:
            parts.append(f"Sa composition correspond également à votre besoin avec exactement {actual} salon{'s' if actual > 1 else ''}, comme demandé.")
        else:
            parts.append(f"Il dispose de {actual} salons, soit {actual - requested} de plus que le minimum de {requested} que vous avez indiqué, ce qui vous offre davantage d'espace sur ce critère.")

    if criteria['bedrooms'] is not None:
        requested = criteria['bedrooms']
        actual = int(prop.bedrooms or 0)
        if actual == requested:
            parts.append(f"Le logement comprend par ailleurs exactement {actual} chambre{'s' if actual > 1 else ''}, correspondant à votre besoin.")
        else:
            parts.append(f"Il propose {actual} chambres, soit {actual - requested} de plus que les {requested} chambres recherchées, ce qui constitue une capacité supplémentaire sans dépasser votre besoin minimal.")

    if criteria['max_occupants'] is not None:
        requested = criteria['max_occupants']
        actual = int(prop.max_occupants or 0)
        if actual == requested:
            parts.append(f"Sa capacité maximale de {actual} occupant{'s' if actual > 1 else ''} correspond également à la limite que vous avez fixée.")
        else:
            parts.append(f"Sa capacité maximale est de {actual} occupants, ce qui couvre votre besoin de {requested} occupant{'s' if requested > 1 else ''}.")

    if criteria['rent'] is not None:
        budget = criteria['rent']
        final_rent = _final_rent(prop)
        if final_rent == budget:
            parts.append(f"Enfin, le loyer mensuel final de {_format_fc(final_rent)} FC correspond exactement à votre budget maximal de {_format_fc(budget)} FC.")
        else:
            difference = budget - final_rent
            parts.append(f"Enfin, son loyer mensuel final de {_format_fc(final_rent)} FC reste inférieur à votre plafond de {_format_fc(budget)} FC, avec une marge de {_format_fc(difference)} FC par rapport au budget maximal que vous avez fixé.")

    if not parts:
        return "Ce bien a été retenu parce qu'il satisfait les critères que vous avez renseignés dans votre recherche."

    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} {parts[1]}"
    return " ".join(parts[:-1]) + " " + parts[-1]


def search(request):
    criteria = _criteria_from_request(request)
    searched = any(value not in ('', None) for value in criteria.values())
    properties = []

    if searched:
        queryset = list(Property.objects.filter(status='published').prefetch_related('images'))
        for prop in queryset:
            if not _hard_requirements(prop, criteria):
                continue
            score, breakdown = matching_score(prop, criteria)
            if score <= 0:
                continue
            prop.ui_score = score
            prop.match_breakdown = breakdown
            prop.final_rent = _final_rent(prop)
            prop.matching_url = f"{reverse('property_detail', args=[prop.pk])}?from_matching=1&{_matching_query(criteria)}"
            prop.matching_explanation = build_matching_explanation(prop, criteria)
            properties.append(prop)
        properties.sort(key=lambda prop: (-prop.ui_score, prop.final_rent, prop.id))

    return render(request, 'search.html', {
        'properties': properties,
        'searched': searched,
        'criteria': criteria,
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
    matching_explanation = ''

    if matching:
        criteria = _criteria_from_request(request)
        if any(value not in ('', None) for value in criteria.values()) and _hard_requirements(prop, criteria):
            score, match_breakdown = matching_score(prop, criteria)
            if score > 0:
                match_criteria = criteria
                matching_query = _matching_query(criteria)
                matching_explanation = build_matching_explanation(prop, criteria)
            else:
                score = None

    return render(request, 'property_detail.html', {
        'property': prop,
        'images': prop.images.all(),
        'score': score,
        'match_breakdown': match_breakdown,
        'match_criteria': match_criteria,
        'matching_query': matching_query,
        'matching_explanation': matching_explanation,
        'final_rent': _final_rent(prop),
    })
