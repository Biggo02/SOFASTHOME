from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import Notification
from .rental_models import RentalCase, RentalContract, RentalDocument


def _can_access(request, case):
    return request.user.is_staff or request.user.pk in {case.owner_id, case.tenant_id}


def _activate_if_complete(case):
    owner = case.owner_contract
    tenant = case.tenant_contract
    pv = case.documents.filter(document_type='inspection').exclude(file='').exists()
    if owner and tenant and owner.status == 'signed' and tenant.status == 'signed' and pv:
        if case.status != 'active':
            case.status = 'active'
            case.save(update_fields=['status', 'updated_at'])
            case.property.status = 'rented'
            case.property.save(update_fields=['status', 'updated_at'])
            Notification.objects.create(user=case.tenant, title='Location active', message='Votre location est maintenant active. Les documents signés sont disponibles dans votre espace.')
            Notification.objects.create(user=case.owner, title='Location active', message=f'La location du bien {case.property.reference} est maintenant active. Les documents signés sont disponibles dans votre espace.')
        return True
    return False


@login_required
def rental_cases(request):
    queryset = RentalCase.objects.select_related('property', 'owner', 'tenant', 'visit', 'owner_contract', 'tenant_contract').prefetch_related('documents').order_by('-updated_at')
    if not request.user.is_staff:
        queryset = queryset.filter(tenant=request.user) | queryset.filter(owner=request.user)
    return render(request, 'rental_cases.html', {'cases': queryset.distinct()})


@login_required
def rental_case_detail(request, pk):
    case = get_object_or_404(RentalCase.objects.select_related('property', 'owner', 'tenant', 'visit', 'owner_contract', 'tenant_contract').prefetch_related('documents'), pk=pk)
    if not _can_access(request, case):
        return HttpResponseForbidden('Accès refusé.')
    if request.method == 'POST':
        if request.user.is_staff and request.POST.get('action') == 'prepare_contracts':
            from .visitor_decision_views import _prepare_rental_documents
            _prepare_rental_documents(case.visit, case)
            Notification.objects.create(user=case.tenant, title='Documents prêts', message='Les contrats et le procès-verbal sont disponibles dans votre espace.')
            Notification.objects.create(user=case.owner, title='Documents prêts', message='Les contrats et le procès-verbal de votre dossier sont disponibles.')
            messages.success(request, 'Les deux contrats et le procès-verbal ont été générés.')
        return redirect('rental_case_detail', pk=case.pk)
    return render(request, 'rental_case_detail.html', {'case': case})


@login_required
def rental_document_upload(request, pk):
    case = get_object_or_404(RentalCase.objects.select_related('property', 'owner', 'tenant', 'owner_contract', 'tenant_contract'), pk=pk)
    if not _can_access(request, case):
        return HttpResponseForbidden('Accès refusé.')
    if request.method != 'POST':
        return redirect('rental_case_detail', pk=case.pk)
    doc_type = request.POST.get('document_type')
    uploaded = request.FILES.get('file')
    if not uploaded or doc_type not in {'owner_contract', 'tenant_contract', 'inspection'}:
        messages.error(request, 'Veuillez sélectionner un document PDF signé.')
        return redirect('rental_case_detail', pk=case.pk)
    if uploaded.content_type != 'application/pdf' and not uploaded.name.lower().endswith('.pdf'):
        messages.error(request, 'Le document signé doit être au format PDF.')
        return redirect('rental_case_detail', pk=case.pk)
    if doc_type == 'owner_contract' and not (request.user.is_staff or request.user.pk == case.owner_id):
        return HttpResponseForbidden('Seul le propriétaire ou FASTHOME peut déposer ce document.')
    if doc_type == 'tenant_contract' and not (request.user.is_staff or request.user.pk == case.tenant_id):
        return HttpResponseForbidden('Seul le locataire ou FASTHOME peut déposer ce document.')
    if doc_type == 'inspection' and not request.user.is_staff:
        return HttpResponseForbidden('Le procès-verbal signé est déposé par FASTHOME.')

    labels = {'owner_contract': 'Contrat FASTHOME – Propriétaire', 'tenant_contract': 'Contrat FASTHOME – Locataire', 'inspection': 'Procès-verbal de visite / état des lieux'}
    doc = case.documents.filter(document_type=doc_type).first()
    if not doc:
        doc = RentalDocument.objects.create(rental_case=case, document_type=doc_type, label=labels[doc_type])
    doc.file = uploaded
    doc.status = 'validated'
    doc.notes = f'Document signé téléversé par {request.user.get_full_name() or request.user.username}.'
    doc.save()

    if doc_type == 'owner_contract' and case.owner_contract:
        case.owner_contract.status = 'signed'
        case.owner_contract.signed_at = timezone.now()
        case.owner_contract.save(update_fields=['status', 'signed_at', 'updated_at'])
        Notification.objects.create(user=case.tenant, title='Contrat propriétaire reçu', message='Le contrat signé par le propriétaire a été reçu par FASTHOME.')
    elif doc_type == 'tenant_contract' and case.tenant_contract:
        case.tenant_contract.status = 'signed'
        case.tenant_contract.signed_at = timezone.now()
        case.tenant_contract.save(update_fields=['status', 'signed_at', 'updated_at'])
        Notification.objects.create(user=case.owner, title='Contrat locataire reçu', message='Le contrat signé par le locataire a été reçu par FASTHOME.')
    else:
        Notification.objects.create(user=case.tenant, title='Procès-verbal reçu', message='Le procès-verbal signé a été reçu par FASTHOME.')
        Notification.objects.create(user=case.owner, title='Procès-verbal reçu', message='Le procès-verbal signé a été reçu par FASTHOME.')

    if _activate_if_complete(case):
        messages.success(request, 'Tous les documents signés sont reçus : la location est maintenant active.')
    else:
        messages.success(request, 'Document signé téléversé avec succès.')
    return redirect('rental_case_detail', pk=case.pk)


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
        buffer = BytesIO(); c = canvas.Canvas(buffer, pagesize=A4); width, height = A4
        title = 'CONTRAT FASTHOME – PROPRIÉTAIRE' if contract.contract_type == 'owner_agreement' else 'CONTRAT FASTHOME – LOCATAIRE'
        c.setTitle(f'FASTHOME {contract.reference}'); c.setFont('Helvetica-Bold', 18); c.drawString(45, height - 55, title)
        c.setFont('Helvetica', 10); y = height - 90
        lines = [f'Reférence : {contract.reference}', f'Dossier : {contract.rental_case.reference}', f'Bien : {contract.property.title} ({contract.property.reference})', f'Localisation : {contract.property.commune} — {contract.property.city} — {contract.property.province}', f'Partie : {contract.party.get_full_name() or contract.party.username}', f'Nature : {contract.get_contract_type_display()}', f'Montant : {contract.amount} USD', f'Dépôt : {contract.deposit} USD', f'Début : {contract.start_date or "—"}', f'Fin : {contract.end_date or "—"}', f'Statut : {contract.get_status_display()}', 'Signature : _________________________________________________']
        for line in lines:
            c.drawString(45, y, line); y -= 21
        c.setFont('Helvetica', 9); c.drawString(45, y - 5, 'Document préparé par FASTHOME. À imprimer, signer puis téléverser sur la plateforme.')
        qr = qrcode.make(f'FASTHOME|{contract.reference}|{contract.rental_case.reference}'); qbuf = BytesIO(); qr.save(qbuf, format='PNG'); qbuf.seek(0)
        c.drawImage(ImageReader(qbuf), width - 145, 55, width=90, height=90); c.setFont('Helvetica', 8); c.drawString(width - 150, 45, 'Vérification FASTHOME')
        c.showPage(); c.save(); buffer.seek(0)
        return HttpResponse(buffer.getvalue(), content_type='application/pdf', headers={'Content-Disposition': f'inline; filename="{contract.reference}.pdf"'})
    except ImportError:
        messages.error(request, 'Le module PDF n’est pas installé sur cet environnement.')
        return redirect('rental_case_detail', pk=contract.rental_case_id)
