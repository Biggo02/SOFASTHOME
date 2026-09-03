from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import get_object_or_404, redirect, render

from .models import Notification, Visit


def _staff(user):
    return user.is_staff


@login_required
def owner_visit_requests(request):
    visits = (
        Visit.objects.filter(property__owner=request.user)
        .select_related('property', 'requester', 'agent')
        .order_by('-created_at')
    )
    return render(request, 'owner_visit_requests.html', {'visits': visits})


@login_required
def owner_visit_decision(request, pk):
    visit = get_object_or_404(
        Visit.objects.select_related('property', 'requester'),
        pk=pk,
        property__owner=request.user,
    )
    if request.method != 'POST':
        return redirect('owner_visit_requests')

    action = request.POST.get('action')
    if action == 'approve':
        visit.owner_approved = True
        if visit.agent_approved:
            visit.status = 'confirmed'
            message = 'La visite est confirmée : le propriétaire et FASTHOME ont validé la demande.'
        else:
            visit.status = 'pending'
            message = 'Votre demande de visite a été validée par le propriétaire. FASTHOME doit encore la valider.'
        visit.save(update_fields=['owner_approved', 'status'])
        Notification.objects.create(user=visit.requester, title='Validation du propriétaire', message=message)
        messages.success(request, 'Demande de visite validée par le propriétaire.')
    elif action == 'reject':
        visit.owner_approved = False
        visit.status = 'rejected'
        visit.observation = request.POST.get('observation', '').strip()
        visit.save(update_fields=['owner_approved', 'status', 'observation'])
        Notification.objects.create(user=visit.requester, title='Demande de visite refusée', message='Le propriétaire n’a pas validé votre demande de visite.')
        messages.success(request, 'Demande de visite refusée. Aucun contact direct n’est communiqué.')
    else:
        messages.error(request, 'Action inconnue.')
    return redirect('owner_visit_requests')


@login_required
@user_passes_test(_staff)
def agent_visit_decision(request, pk):
    visit = get_object_or_404(Visit.objects.select_related('property', 'requester'), pk=pk)
    if request.method != 'POST':
        return render(request, 'manage_visit.html', {'visit': visit})

    action = request.POST.get('action')
    if action == 'approve':
        visit.agent = request.user
        visit.agent_approved = True
        visit.scheduled_date = request.POST.get('scheduled_date') or visit.scheduled_date
        visit.scheduled_time = request.POST.get('scheduled_time') or visit.scheduled_time
        visit.observation = request.POST.get('observation', '').strip()
        visit.status = 'confirmed' if visit.owner_approved else 'pending'
        visit.save(update_fields=['agent', 'agent_approved', 'scheduled_date', 'scheduled_time', 'observation', 'status'])
        text = ('La demande de visite est confirmée : les deux validations sont obtenues.' if visit.owner_approved else 'FASTHOME a validé la demande. La validation du propriétaire est encore requise.')
        Notification.objects.create(user=visit.requester, title='Validation FASTHOME', message=text)
        messages.success(request, 'Décision FASTHOME enregistrée.')
    elif action == 'reject':
        visit.agent = request.user
        visit.agent_approved = False
        visit.observation = request.POST.get('observation', '').strip()
        visit.status = 'rejected'
        visit.save(update_fields=['agent', 'agent_approved', 'observation', 'status'])
        Notification.objects.create(user=visit.requester, title='Demande de visite refusée', message='FASTHOME n’a pas validé votre demande de visite.')
        messages.success(request, 'Demande de visite refusée par FASTHOME.')
    else:
        messages.error(request, 'Action inconnue.')
    return redirect('admin_dashboard')
