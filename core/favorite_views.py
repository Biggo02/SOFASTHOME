from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from .models import Property


@login_required
def toggle_favorite(request, pk):
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Méthode non autorisée.'}, status=405)

    prop = get_object_or_404(Property, pk=pk, status='published')
    ids = [int(value) for value in request.session.get('favorites', [])]

    if pk in ids:
        ids.remove(pk)
        is_favorite = False
    else:
        ids.append(pk)
        is_favorite = True

    request.session['favorites'] = ids
    request.session.modified = True

    return JsonResponse({
        'ok': True,
        'is_favorite': is_favorite,
        'count': len(ids),
    })
