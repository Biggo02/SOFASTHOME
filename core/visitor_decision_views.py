from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import Notification, Visit, RentalCase, RentalDocument


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

        if decision == 'interested':
            case, created = RentalCase.objects.get_or_create(
                visit=visit,
                defaults={
                    'property': visit.property,
                    'owner': visit.property.owner,
                    'tenant': request.user,
                    'status': 'preparing',
                },
            )
            if created:
                RentalDocument.objects.bulk_create([
                    RentalDocument(rental_case=case, document_type='identity', label='Pièce d’identité du locataire'),
                    RentalDocument(rental_case=case, document_type='owner_contract', label='Contrat FASTHOME – Propriétaire'),
                    RentalDocument(rental_case=case, document_type='tenant_contract', label='Contrat FASTHOME – Locataire'),
                    RentalDocument(rental_case=case, document_type='inspection', label='État des lieux'),
                ])
            Notification.objects.create(
                user=request.user,
                title='Dossier de location ouvert',
                message='Votre intérêt est enregistré. FASTHOME va préparer votre dossier et les documents nécessaires.',
            )
            Notification.objects.create(
                user=visit.property.owner,
                title='Dossier de location en préparation',
                message=f'FASTHOME prépare un dossier de location pour votre bien {visit.property.reference}.',
            )
            messages.success(request, 'Votre intérêt a bien été enregistré. FASTHOME va préparer votre dossier de location.')
            return redirect('rental_case_detail', pk=case.pk)

        recipient = visit.agent
        if recipient:
            title = 'Décision du visiteur reçue'
            if decision == 'thinking':
                message = f'Le visiteur souhaite réfléchir pour le bien {visit.property.reference}.'
            else:
                message = f'Le visiteur n’est pas intéressé par le bien {visit.property.reference}.'
            Notification.objects.create(user=recipient, title=title, message=message)
        messages.success(request, 'Votre décision a bien été transmise à FASTHOME.')
        return redirect('visits')
    return render(request, 'visitor_final_decision.html', {'visit': visit})
