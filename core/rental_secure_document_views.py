from pathlib import Path

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404

from .rental_models import RentalDocument


@login_required
def signed_document_file(request, document_id):
    """Serve uniquement un document signé et validé à la partie autorisée."""
    document = get_object_or_404(
        RentalDocument.objects.select_related(
            'rental_case', 'rental_case__owner', 'rental_case__tenant'
        ),
        pk=document_id,
        status='validated',
    )
    case = document.rental_case

    if request.user.is_staff:
        allowed = True
    elif document.document_type in {'owner_contract', 'owner_inspection'}:
        allowed = request.user.pk == case.owner_id
    elif document.document_type in {'tenant_contract', 'tenant_inspection'}:
        allowed = request.user.pk == case.tenant_id
    else:
        allowed = False

    if not allowed:
        return HttpResponseForbidden('Ce document ne vous est pas destiné.')
    if not document.file:
        return HttpResponseForbidden('Le document signé n’est pas disponible.')

    with document.file.open('rb') as fh:
        response = HttpResponse(fh.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{Path(document.file.name).name}"'
    return response
