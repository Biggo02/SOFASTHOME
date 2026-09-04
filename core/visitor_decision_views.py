from io import BytesIO

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import Notification, Visit
from .rental_models import RentalCase, RentalContract, RentalDocument


def _pdf_bytes(title, lines):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    c.setTitle(title)
    c.setFont('Helvetica-Bold', 17)
    c.drawString(45, height - 55, title)
    y = height - 90
    c.setFont('Helvetica', 10)
    for line in lines:
        if y < 65:
            c.showPage()
            y = height - 55
            c.setFont('Helvetica', 10)
        c.drawString(45, y, str(line)[:115])
        y -= 19
    c.setFont('Helvetica', 8)
    c.drawString(45, 40, 'Document préparé par FASTHOME — à imprimer, signer puis téléverser sur la plateforme.')
    c.save()
    buffer.seek(0)
    return buffer.getvalue()


def _prepare_rental_documents(visit, case):
    prop = visit.property
    owner = prop.owner
    tenant = visit.requester
    location = f'{prop.commune} — {prop.city} — {prop.province}'
    owner_name = owner.get_full_name() or owner.username
    tenant_name = tenant.get_full_name() or tenant.username

    owner_contract, _ = RentalContract.objects.get_or_create(
        rental_case=case,
        contract_type='owner_agreement',
        defaults={
            'property': prop,
            'party': owner,
            'amount': prop.rent,
            'deposit': prop.deposit,
            'status': 'pending_signature',
        },
    )
    tenant_contract, _ = RentalContract.objects.get_or_create(
        rental_case=case,
        contract_type='tenant_sublease',
        defaults={
            'property': prop,
            'party': tenant,
            'amount': prop.rent + prop.margin,
            'deposit': prop.deposit,
            'status': 'pending_signature',
        },
    )
    case.owner_contract = owner_contract
    case.tenant_contract = tenant_contract
    case.status = 'signing'
    case.save(update_fields=['owner_contract', 'tenant_contract', 'status', 'updated_at'])

    owner_pdf = _pdf_bytes('CONTRAT FASTHOME — PROPRIÉTAIRE', [
        f'Reférence : {owner_contract.reference}', f'Dossier : {case.reference}',
        f'Bien : {prop.title} ({prop.reference})', f'Localisation : {location}',
        f'Propriétaire : {owner_name}', f'Locataire concerné : {tenant_name}',
        'Nature : Convention FASTHOME – Propriétaire', f'Loyer convenu avec le propriétaire : {prop.rent} USD',
        f'Dépôt : {prop.deposit} USD', f'Début prévu : {prop.availability_date or "À définir"}',
        'Signature du propriétaire : ______________________________',
        'Signature / visa FASTHOME : ______________________________',
    ])
    tenant_pdf = _pdf_bytes('CONTRAT FASTHOME — LOCATAIRE', [
        f'Reférence : {tenant_contract.reference}', f'Dossier : {case.reference}',
        f'Bien : {prop.title} ({prop.reference})', f'Localisation : {location}',
        f'Locataire : {tenant_name}', f'Propriétaire du bien : {owner_name}',
        'Nature : Contrat FASTHOME – Locataire / sous-location', f'Loyer mensuel : {prop.rent + prop.margin} USD',
        f'Dépôt : {prop.deposit} USD', f'Début prévu : {prop.availability_date or "À définir"}',
        'Signature du locataire : ______________________________',
        'Signature / visa FASTHOME : ______________________________',
    ])
    pv_pdf = _pdf_bytes('PROCÈS-VERBAL — FASTHOME', [
        f'Référence : PV-{case.reference}', f'Dossier : {case.reference}',
        f'Bien : {prop.title} ({prop.reference})', f'Localisation : {location}',
        f'Parties présentes : FASTHOME, {owner_name}, {tenant_name}',
        f'Visite effectuée le : {visit.scheduled_date or visit.preferred_date or timezone.localdate()}',
        f'Heure : {visit.scheduled_time or visit.preferred_time or "À préciser"}',
        f'Observations : {visit.observation or "Aucune observation enregistrée."}',
        'Signature du propriétaire : ______________________________',
        'Signature du locataire : ______________________________',
        'Signature FASTHOME : ______________________________',
    ])

    owner_doc, _ = RentalDocument.objects.get_or_create(rental_case=case, document_type='owner_contract', defaults={'label': 'Contrat FASTHOME – Propriétaire'})
    tenant_doc, _ = RentalDocument.objects.get_or_create(rental_case=case, document_type='tenant_contract', defaults={'label': 'Contrat FASTHOME – Locataire'})
    pv_doc, _ = RentalDocument.objects.get_or_create(rental_case=case, document_type='inspection', defaults={'label': 'Procès-verbal de visite / état des lieux'})
    if not owner_doc.file:
        owner_doc.file.save(f'{owner_contract.reference}.pdf', ContentFile(owner_pdf), save=False)
    owner_doc.status = 'prepared'
    owner_doc.save()
    if not tenant_doc.file:
        tenant_doc.file.save(f'{tenant_contract.reference}.pdf', ContentFile(tenant_pdf), save=False)
    tenant_doc.status = 'prepared'
    tenant_doc.save()
    if not pv_doc.file:
        pv_doc.file.save(f'PV-{case.reference}.pdf', ContentFile(pv_pdf), save=False)
    pv_doc.status = 'prepared'
    pv_doc.save()
    return owner_contract, tenant_contract, pv_doc


def _activate_if_signed(case):
    owner = case.owner_contract
    tenant = case.tenant_contract
    pv = case.documents.filter(document_type='inspection', file__isnull=False).exclude(file='').first()
    if owner and tenant and owner.status == 'signed' and tenant.status == 'signed' and pv:
        case.status = 'active'
        case.save(update_fields=['status', 'updated_at'])
        case.property.status = 'rented'
        case.property.save(update_fields=['status', 'updated_at'])
        return True
    return False


@login_required
def visitor_final_decision(request, pk):
    visit = get_object_or_404(Visit.objects.select_related('property', 'property__owner', 'agent'), pk=pk, requester=request.user)
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
            case, _ = RentalCase.objects.get_or_create(
                visit=visit,
                defaults={'property': visit.property, 'owner': visit.property.owner, 'tenant': request.user, 'status': 'preparing'},
            )
            _prepare_rental_documents(visit, case)
            Notification.objects.create(user=request.user, title='Dossier de location ouvert', message='Votre décision est enregistrée. Les documents de location sont prêts dans votre espace.')
            Notification.objects.create(user=visit.property.owner, title='Le locataire souhaite prendre le bien', message=f'Le dossier {case.reference} concernant votre bien {visit.property.reference} est prêt pour signature.')
            if visit.agent:
                Notification.objects.create(user=visit.agent, title='Dossier de location à suivre', message=f'Le dossier {case.reference} est prêt. Les documents ont été générés.')
            messages.success(request, 'Votre décision est enregistrée. Les contrats et le procès-verbal sont maintenant disponibles.')
            return redirect('rental_case_detail', pk=case.pk)

        if visit.agent:
            message = f'Le visiteur souhaite réfléchir pour le bien {visit.property.reference}.' if decision == 'thinking' else f'Le visiteur n’est pas intéressé par le bien {visit.property.reference}.'
            Notification.objects.create(user=visit.agent, title='Décision du visiteur reçue', message=message)
        messages.success(request, 'Votre décision a bien été transmise à FASTHOME.')
        return redirect('visits')
    return render(request, 'visitor_final_decision.html', {'visit': visit})
