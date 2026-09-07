from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from .models import Notification
from .rental_models import RentalCase


def _can_access(request, case):
    return request.user.is_staff


@login_required
def rental_cases(request):
    # Le dossier complet est un espace interne réservé à FASTHOME.
    if not request.user.is_staff:
        return redirect('contracts')
    queryset = RentalCase.objects.select_related(
        'property', 'owner', 'tenant', 'visit', 'owner_contract', 'tenant_contract'
    ).prefetch_related('documents').order_by('-updated_at')
    return render(request, 'rental_cases.html', {'cases': queryset.distinct()})


@login_required
def rental_case_detail(request, pk):
    case = get_object_or_404(
        RentalCase.objects.select_related(
            'property', 'owner', 'tenant', 'visit', 'owner_contract', 'tenant_contract'
        ).prefetch_related('documents'),
        pk=pk,
    )
    if not _can_access(request, case):
        return HttpResponseForbidden('Ce dossier est réservé à FASTHOME.')
    if request.method == 'POST':
        if request.user.is_staff and request.POST.get('action') == 'prepare_contracts':
            from .visitor_decision_views import _prepare_rental_documents
            _prepare_rental_documents(case.visit, case)
            Notification.objects.create(user=case.tenant, title='Documents prêts', message='Les contrats et les états des lieux sont disponibles auprès de FASTHOME.')
            Notification.objects.create(user=case.owner, title='Documents prêts', message='Les contrats et les états des lieux de votre dossier sont prêts.')
            messages.success(request, 'Les documents ont été préparés.')
        return redirect('rental_case_detail', pk=case.pk)
    return render(request, 'rental_case_detail.html', {'case': case})


@login_required
def rental_document_upload(request, pk):
    # Ancienne route conservée uniquement pour compatibilité : aucun client ne téléverse.
    if not request.user.is_staff:
        return HttpResponseForbidden('Seul FASTHOME peut téléverser les documents signés.')
    return redirect('rental_case_detail', pk=pk)
