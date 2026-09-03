from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import AuditLog, Notification, Property, Visit, RentalCase, RentalContract, RentalDocument


def staff_required(user):
    return user.is_staff


@login_required
def final_visit_decision(request, pk):
    visit = get_object_or_404(Visit.objects.select_related('property'), pk=pk, requester=request.user)
    if visit.status != 'done':
        messages.error(request, 'La décision finale sera disponible après la visite.')
        return redirect('visits')
    if visit.final_decision:
        messages.info(request, 'Votre décision pour cette visite a déjà été enregistrée.')
        return redirect('visits')
    if request.method == 'POST':
        decision = request.POST.get('decision')
        allowed = {'interested', 'thinking', 'not_interested'}
        if decision not in allowed:
            messages.error(request, 'Veuillez sélectionner une décision.')
            return render(request, 'final_visit_decision.html', {'visit': visit})
        visit.final_decision = decision
        visit.final_decision_comment = request.POST.get('comment', '').strip()
        visit.final_decision_at = timezone.now()
        visit.save(update_fields=['final_decision', 'final_decision_comment', 'final_decision_at'])
        AuditLog.objects.create(actor=request.user, action='visit.final_decision', object_type='Visit', object_id=str(visit.pk), details={'decision': decision})
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
            Notification.objects.create(user=request.user, title='Dossier de location ouvert', message='Votre intérêt est enregistré. FASTHOME va préparer votre dossier et les documents nécessaires.')
            Notification.objects.create(user=visit.property.owner, title='Dossier de location à préparer', message=f'Un visiteur est intéressé par votre bien {visit.property.reference}. FASTHOME va préparer la suite du dossier.')
            for staff in __staff_users():
                Notification.objects.create(user=staff, title='Nouveau dossier de location', message=f'Le visiteur de {visit.property.reference} est intéressé. Le dossier {case.reference} est à préparer.')
            messages.success(request, 'Votre intérêt a bien été enregistré. FASTHOME va préparer votre dossier de location.')
            return redirect('rental_case_detail', pk=case.pk)
        if decision == 'thinking':
            Notification.objects.create(user=request.user, title='Décision enregistrée', message='Votre demande est conservée en réflexion. Vous pourrez reprendre contact avec FASTHOME lorsque vous serez prêt.')
            for staff in __staff_users():
                Notification.objects.create(user=staff, title='Visiteur en réflexion', message=f'Le visiteur de {visit.property.reference} souhaite réfléchir.')
            messages.success(request, 'Votre décision « Je souhaite réfléchir » a été enregistrée.')
        else:
            Notification.objects.create(user=request.user, title='Décision enregistrée', message='Votre décision a été enregistrée. La visite est clôturée.')
            for staff in __staff_users():
                Notification.objects.create(user=staff, title='Visiteur non intéressé', message=f'Le visiteur de {visit.property.reference} n’est pas intéressé.')
            messages.success(request, 'Votre décision a été enregistrée.')
        return redirect('visits')
    return render(request, 'final_visit_decision.html', {'visit': visit})


def __staff_users():
    from django.contrib.auth.models import User
    return User.objects.filter(is_staff=True, is_active=True)


@login_required
@user_passes_test(staff_required)
def rental_cases(request):
    cases = RentalCase.objects.select_related('property', 'owner', 'tenant', 'visit').prefetch_related('contracts', 'documents').order_by('-updated_at')
    return render(request, 'rental_cases.html', {'cases': cases})


@login_required
@user_passes_test(staff_required)
def rental_case_detail(request, pk):
    case = get_object_or_404(
        RentalCase.objects.select_related('property', 'owner', 'tenant', 'visit', 'owner_contract', 'tenant_contract').prefetch_related('contracts', 'documents'),
        pk=pk,
    )
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'prepare_contracts':
            owner_contract = case.owner_contract
            tenant_contract = case.tenant_contract
            if not owner_contract:
                owner_contract = RentalContract.objects.create(
                    rental_case=case, property=case.property, contract_type='owner_agreement', party=case.owner,
                    amount=case.property.rent, deposit=case.property.deposit, status='prepared',
                )
            if not tenant_contract:
                tenant_contract = RentalContract.objects.create(
                    rental_case=case, property=case.property, contract_type='tenant_sublease', party=case.tenant,
                    amount=case.property.rent + case.property.margin, deposit=case.property.deposit, status='prepared',
                )
            case.owner_contract = owner_contract
            case.tenant_contract = tenant_contract
            case.status = 'owner_contract'
            case.save(update_fields=['owner_contract', 'tenant_contract', 'status', 'updated_at'])
            for document in case.documents.filter(document_type__in=['owner_contract', 'tenant_contract']):
                document.status = 'prepared'
                document.save(update_fields=['status', 'updated_at'])
            Notification.objects.create(user=case.tenant, title='Documents en préparation', message='FASTHOME a commencé la préparation de vos documents de location.')
            Notification.objects.create(user=case.owner, title='Contrat FASTHOME à préparer', message=f'Le dossier {case.reference} est en préparation.')
            messages.success(request, 'Les deux contrats distincts ont été créés et préparés.')
        elif action == 'status':
            new_status = request.POST.get('status')
            if new_status in dict(RentalCase.STATUS):
                case.status = new_status
                case.save(update_fields=['status', 'updated_at'])
                messages.success(request, 'Statut du dossier mis à jour.')
        return redirect('rental_case_detail', pk=case.pk)
    return render(request, 'rental_case_detail.html', {'case': case})


@login_required
@user_passes_test(staff_required)
def rental_contract_pdf(request, pk):
    contract = get_object_or_404(RentalContract.objects.select_related('rental_case', 'property', 'party'), pk=pk)
    try:
        from io import BytesIO
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        import qrcode
        from reportlab.lib.utils import ImageReader
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        title = 'CONTRAT FASTHOME – PROPRIÉTAIRE' if contract.contract_type == 'owner_agreement' else 'CONTRAT FASTHOME – LOCATAIRE'
        c.setTitle(f'FASTHOME {contract.reference}')
        c.setFont('Helvetica-Bold', 18)
        c.drawString(45, height - 55, title)
        c.setFont('Helvetica', 10)
        y = height - 90
        lines = [
            f'Reférence : {contract.reference}',
            f'Dossier : {contract.rental_case.reference}',
            f'Bien : {contract.property.title} ({contract.property.reference})',
            f'Localisation : {contract.property.commune} — {contract.property.city} — {contract.property.province}',
            f'Partie : {contract.party.get_full_name() or contract.party.username}',
            f'Nature : {contract.get_contract_type_display()}',
            f'Montant : {contract.amount} USD',
            f'Dépôt : {contract.deposit} USD',
            f'Début : {contract.start_date or "—"}',
            f'Fin : {contract.end_date or "—"}',
            f'Statut : {contract.get_status_display()}',
        ]
        for line in lines:
            c.drawString(45, y, line)
            y -= 21
        c.setFont('Helvetica', 9)
        c.drawString(45, y - 5, 'Ce document est un projet généré par FASTHOME et doit être vérifié avant signature.')
        qr = qrcode.make(f'FASTHOME|{contract.reference}|{contract.rental_case.reference}')
        qbuf = BytesIO(); qr.save(qbuf, format='PNG'); qbuf.seek(0)
        c.drawImage(ImageReader(qbuf), width - 145, 55, width=90, height=90)
        c.setFont('Helvetica', 8); c.drawString(width - 150, 45, 'Vérification FASTHOME')
        c.showPage(); c.save(); buffer.seek(0)
        return __import__('django.http', fromlist=['HttpResponse']).HttpResponse(buffer.getvalue(), content_type='application/pdf', headers={'Content-Disposition': f'inline; filename="{contract.reference}.pdf"'})
    except ImportError:
        messages.error(request, 'Le module PDF n’est pas installé sur cet environnement.')
        return redirect('rental_case_detail', pk=contract.rental_case_id)
