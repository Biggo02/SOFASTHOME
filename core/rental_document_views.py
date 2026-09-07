from io import BytesIO

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from .rental_models import RentalCase


def _allowed(request, case):
    return request.user.is_staff or request.user.pk in {case.owner_id, case.tenant_id}


def _make_pdf(title, lines):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    c.setTitle(title)
    c.setFont('Helvetica-Bold', 16)
    c.drawString(45, height - 55, 'FASTHOME')
    c.setFont('Helvetica-Bold', 12)
    c.drawString(45, height - 80, title)
    y = height - 115
    c.setFont('Helvetica', 10)
    for text in lines:
        line = ''
        for word in str(text).split():
            candidate = f'{line} {word}'.strip()
            if c.stringWidth(candidate, 'Helvetica', 10) <= width - 90:
                line = candidate
            else:
                c.drawString(45, y, line)
                y -= 15
                line = word
        if line:
            c.drawString(45, y, line)
            y -= 18
        if y < 70:
            c.showPage()
            y = height - 55
            c.setFont('Helvetica', 10)
    c.setFont('Helvetica', 8)
    c.drawString(45, 40, 'Document préparé par FASTHOME — dossier de location')
    c.save()
    buffer.seek(0)
    return buffer.getvalue()


@login_required
def rental_support_document_pdf(request, pk, document):
    case = get_object_or_404(
        RentalCase.objects.select_related('property', 'owner', 'tenant', 'visit'), pk=pk
    )
    if not _allowed(request, case):
        return HttpResponseForbidden('Accès refusé.')

    prop = case.property
    owner = case.owner.get_full_name() or case.owner.username
    tenant = case.tenant.get_full_name() or case.tenant.username
    location = f'{prop.commune} — {prop.city} — {prop.province}'
    visit = case.visit

    if document == 'pv':
        title = f'PROCÈS-VERBAL DE VISITE / ÉTAT DES LIEUX — {case.reference}'
        lines = [
            f'Reférence : PV-{case.reference}', f'Bien : {prop.title} — {prop.reference}',
            f'Localisation : {location}', f'Propriétaire : {owner}', f'Locataire : {tenant}',
            f'Date : {visit.scheduled_date or visit.preferred_date or "À préciser"}',
            f'Heure : {visit.scheduled_time or visit.preferred_time or "À préciser"}',
            f'Observations : {visit.observation or "Aucune observation enregistrée."}',
            '', 'État général : ________________________________________________',
            'Relevés des compteurs : _______________________________________',
            'Nombre de clés remises : ______________________________________',
            '', 'SIGNATURES', 'Propriétaire : ______________________________',
            'Locataire : _________________________________', 'FASTHOME : __________________________________',
        ]
        response = HttpResponse(_make_pdf(title, lines), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="PV-{case.reference}.pdf"'
        return response

    if document == 'annexe':
        title = f'DOCUMENT ANNEXE À LA LOCATION — {case.reference}'
        lines = [
            f'Référence : ANN-{case.reference}', f'Dossier : {case.reference}',
            f'Bien : {prop.title} — {prop.reference}', f'Localisation : {location}',
            f'Propriétaire : {owner}', f'Locataire : {tenant}',
            'Le présent document annexe complète les contrats de location et rassemble les informations pratiques du dossier.',
            '', 'INFORMATIONS DU LOGEMENT',
            f'Chambres : {prop.bedrooms} | Salons : {prop.salons} | Cuisine(s) : {prop.kitchens}',
            f'Salle(s) de bain : {prop.bathrooms} | Toilette(s) : {prop.toilets} | Occupants max. : {prop.max_occupants}',
            f'Eau : {"Disponible" if prop.water else "Non disponible"} | Électricité : {"Disponible" if prop.electricity else "Non disponible"}',
            f'Parking : {"Oui" if prop.parking else "Non"} | Sécurité : {"Oui" if prop.security else "Non"}',
            '', 'CONDITIONS PARTICULIÈRES / OBSERVATIONS',
            '____________________________________________________________________',
            '____________________________________________________________________',
            '____________________________________________________________________',
            '', 'SIGNATURES SI REQUISES', 'Propriétaire : ______________________________',
            'Locataire : _________________________________', 'FASTHOME : __________________________________',
        ]
        response = HttpResponse(_make_pdf(title, lines), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="ANN-{case.reference}.pdf"'
        return response

    return HttpResponseForbidden('Document inconnu.')
