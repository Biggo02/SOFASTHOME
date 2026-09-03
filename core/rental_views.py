from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import AuditLog, Notification, Visit, RentalCase, RentalContract, RentalDocument


def staff_required(user):
    return user.is_staff


def __staff_users():
    from django.contrib.auth.models import User
    return User.objects.filter(is_staff=True, is_active=True)


@login_required
@user_passes_test(staff_required)
def rental_cases(request):
    cases = RentalCase.objects.select_related('property', 'owner', 'tenant', 'visit').prefetch_related('contracts', 'documents').order_by('-updated_at')
    return render(request, 'rental_cases.html', {'cases': cases})


@login_required
def rental_case_detail(request, pk):
    case = get_object_or_404(
        RentalCase.objects.select_related('property', 'owner', 'tenant', 'visit', 'owner_contract', 'tenant_contract').prefetch_related('contracts', 'documents'),
        pk=pk,
    )
    if not (request.user.is_staff or request.user.pk in {case.owner_id, case.tenant_id}):
        return HttpResponseForbidden('Accès refusé.')

    if request.method == 'POST':
        if not request.user.is_staff:
            return HttpResponseForbidden('Seul FASTHOME peut modifier le dossier.')
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
def rental_contract_pdf(request, pk):
    contract = get_object_or_404(RentalContract.objects.select_related('rental_case', 'property', 'party'), pk=pk)
    if not (request.user.is_staff or request.user.pk in {contract.rental_case.owner_id, contract.rental_case.tenant_id}):
        return HttpResponseForbidden('Accès refusé.')
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
        c.drawString(45, y - 5, 'Projet généré par FASTHOME. Le document doit être vérifié avant signature.')
        qr = qrcode.make(f'FASTHOME|{contract.reference}|{contract.rental_case.reference}')
        qbuf = BytesIO(); qr.save(qbuf, format='PNG'); qbuf.seek(0)
        c.drawImage(ImageReader(qbuf), width - 145, 55, width=90, height=90)
        c.setFont('Helvetica', 8); c.drawString(width - 150, 45, 'Vérification FASTHOME')
        c.showPage(); c.save(); buffer.seek(0)
        return HttpResponse(buffer.getvalue(), content_type='application/pdf', headers={'Content-Disposition': f'inline; filename="{contract.reference}.pdf"'})
    except ImportError:
        messages.error(request, 'Le module PDF n’est pas installé sur cet environnement.')
        return redirect('rental_case_detail', pk=contract.rental_case_id)
