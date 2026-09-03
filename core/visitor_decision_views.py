from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from .models import Notification, Visit

@login_required
def visitor_final_decision(request, pk):
    visit = get_object_or_404(Visit.objects.select_related('property', 'agent'), pk=pk, requester=request.user)
    if visit.status != 'done':
        messages.error(request, 'La décision finale est disponible après une visite effectuée.')
        return redirect('visits')
    if visit.final_decision:
        messages.info(request, 'Votre décision finale pour cette visite a déjà été enregistrée.')
        return redirect('visits')
    if request.method == 'POST':
        decision = request.POST.get('final_decision', '').strip()
        allowed = {choice[0] for choice in Visit.FINAL_DECISIONS}
        if decision not in allowed:
            messages.error(request, 'Veuillez sélectionner une décision.')
            return render(request, 'visitor_final_decision.html', {'visit': visit})
        visit.final_decision = decision
        visit.final_decision_comment = request.POST.get('final_decision_comment', '').strip()
        visit.final_decision_at = timezone.now()
        visit.save(update_fields=['final_decision', 'final_decision_comment', 'final_decision_at'])
        recipient = visit.agent
        if recipient:
            Notification.objects.create(user=recipient, title='Décision du visiteur reçue', message=f'Le visiteur a donné sa décision pour le bien {visit.property.reference}.')
        messages.success(request, 'Votre décision a bien été transmise à FASTHOME.')
        return redirect('visits')
    return render(request, 'visitor_final_decision.html', {'visit': visit})
