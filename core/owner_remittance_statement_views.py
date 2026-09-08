from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from .models import Property
from .rental_models import RentalCase, OwnerRemittance

NAVY = colors.HexColor('#10243E')
GOLD = colors.HexColor('#F1B90B')
LIGHT = colors.HexColor('#F5F7FA')
MID = colors.HexColor('#D9E0E8')
TEXT = colors.HexColor('#253247')
MUTED = colors.HexColor('#667085')


def _esc(value):
    return str(value or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _cdf(value):
    return f'{value or 0:,.0f}'.replace(',', ' ') + ' CDF'


def _date(value):
    return value.strftime('%d/%m/%Y') if value else '—'


def _page(canvas, doc, statement_ref):
    w, h = A4
    logo = Path(settings.BASE_DIR) / 'static' / 'images' / 'logo.png'
    if logo.exists():
        try:
            canvas.drawImage(ImageReader(str(logo)), 42, h - 62, width=92, height=37, preserveAspectRatio=True, mask='auto')
        except Exception:
            pass
    else:
        canvas.setFillColor(NAVY)
        canvas.setFont('Helvetica-Bold', 15)
        canvas.drawString(42, h - 48, 'FASTHOME')
    canvas.setStrokeColor(MID)
    canvas.line(42, h - 69, w - 42, h - 69)
    canvas.line(42, 40, w - 42, 40)
    canvas.setFillColor(MUTED)
    canvas.setFont('Helvetica', 7)
    canvas.drawString(42, 27, f'FASTHOME · {statement_ref} · Relevé officiel')
    canvas.drawRightString(w - 42, 27, f'Page {doc.page}')


@login_required
def owner_remittance_statement(request, pk):
    property_obj = get_object_or_404(Property, pk=pk)
    if property_obj.owner_id != request.user.id and not request.user.is_staff:
        return HttpResponseForbidden("Ce relevé n'est pas accessible depuis votre espace.")

    cases = list(RentalCase.objects.filter(property=property_obj).select_related('owner', 'tenant', 'owner_contract').order_by('-updated_at'))
    active_case = next((c for c in cases if c.status == 'active'), cases[0] if cases else None)
    remittances = list(OwnerRemittance.objects.filter(property=property_obj, owner=request.user).select_related('rental_case').order_by('payment_date', 'id'))
    total = sum((item.amount or 0) for item in remittances)
    owner_name = request.user.get_full_name() or request.user.username
    tenant_name = 'Non renseigné'
    start_date = end_date = None
    case_ref = '—'
    if active_case:
        tenant_name = active_case.tenant.get_full_name() or active_case.tenant.username
        case_ref = active_case.reference
        contract = active_case.owner_contract or active_case.contracts.filter(contract_type='owner_agreement').order_by('-id').first()
        if contract:
            start_date, end_date = contract.start_date, contract.end_date

    statement_ref = f'FAST-REL-{property_obj.pk:06d}-{len(remittances):04d}'
    styles = getSampleStyleSheet()
    title = ParagraphStyle('st', parent=styles['Title'], fontName='Helvetica-Bold', fontSize=17, leading=21, textColor=NAVY, spaceAfter=5)
    section = ParagraphStyle('ss', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=10, leading=13, textColor=NAVY, spaceBefore=7, spaceAfter=5)
    body = ParagraphStyle('sb', parent=styles['BodyText'], fontName='Helvetica', fontSize=8.5, leading=12, textColor=TEXT)
    small = ParagraphStyle('sm', parent=styles['BodyText'], fontName='Helvetica', fontSize=7, leading=9, textColor=MUTED)
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=17*mm, rightMargin=17*mm, topMargin=28*mm, bottomMargin=18*mm, title='Relevé des versements au propriétaire', author='FASTHOME')
    story = [Paragraph('RELEVÉ DES VERSEMENTS AU PROPRIÉTAIRE', title), Paragraph(f'Ref. relevé : {_esc(statement_ref)} · Généré le {_date(__import__("datetime").date.today())}', small), Spacer(1, 7)]
    info = [
        ['PROPRIÉTAIRE', owner_name],
        ['BIEN', f'{property_obj.title} — {property_obj.reference}'],
        ['LOCALISATION', property_obj.full_address or f'{property_obj.city or ""} {property_obj.neighborhood or ""}'.strip() or 'Non renseignée'],
        ['DOSSIER DE LOCATION', case_ref],
        ['LOCATAIRE', tenant_name],
        ['PÉRIODE DU CONTRAT', f'{_date(start_date)} au {_date(end_date)}'],
    ]
    table = Table([[Paragraph(_esc(a), small), Paragraph(_esc(b), body)] for a,b in info], colWidths=[48*mm, 125*mm])
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(0,-1),LIGHT),('BOX',(0,0),(-1,-1),.5,MID),('INNERGRID',(0,0),(-1,-1),.3,MID),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
    story += [table, Spacer(1, 9), Paragraph('SYNTHÈSE', section)]
    summary = Table([[Paragraph('TOTAL EFFECTIVEMENT VERSÉ', small), Paragraph('NOMBRE D’OPÉRATIONS', small)], [Paragraph(_cdf(total), body), Paragraph(str(len(remittances)), body)]], colWidths=[86*mm, 87*mm])
    summary.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),LIGHT),('BOX',(0,0),(-1,-1),.5,MID),('INNERGRID',(0,0),(-1,-1),.3,MID),('LEFTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
    story += [summary, Spacer(1, 9), Paragraph('DÉTAIL DES VERSEMENTS', section)]
    rows = [[Paragraph(x, small) for x in ['DATE', 'RÉFÉRENCE', 'PÉRIODE', 'MODE', 'MONTANT']]]
    for item in remittances:
        period = f'{_date(item.period_start)} → {_date(item.period_end)}' if item.period_start else '—'
        rows.append([Paragraph(_date(item.payment_date), small), Paragraph(_esc(item.reference), small), Paragraph(period, small), Paragraph(_esc(item.payment_method or '—'), small), Paragraph(_cdf(item.amount), body)])
    if not remittances:
        rows.append([Paragraph('Aucun versement FASTHOME enregistré pour ce bien.', body), '', '', '', ''])
    detail = Table(rows, colWidths=[25*mm, 35*mm, 43*mm, 25*mm, 45*mm], repeatRows=1)
    detail.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),NAVY),('TEXTCOLOR',(0,0),(-1,0),colors.white),('BOX',(0,0),(-1,-1),.5,MID),('INNERGRID',(0,0),(-1,-1),.3,MID),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('ALIGN',(4,1),(4,-1),'RIGHT'),('SPAN',(0,1),(-1,1)) if not remittances else ('ALIGN',(4,1),(4,-1),'RIGHT'),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
    story += [detail, Spacer(1, 10), Paragraph('Ce relevé présente exclusivement les sommes effectivement enregistrées comme versées par FASTHOME au propriétaire pour le bien concerné. Il ne constitue pas un état des dettes ou paiements du locataire.', small), Spacer(1, 18), Paragraph('FASTHOME — Service gestion locative', body), Paragraph('Document généré automatiquement à partir des opérations enregistrées dans le dossier. À conserver avec les reçus et preuves de paiement.', small)]
    doc.build(story, onFirstPage=lambda c,d: _page(c,d,statement_ref), onLaterPages=lambda c,d: _page(c,d,statement_ref))
    response = HttpResponse(buf.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="releve-versements-{property_obj.reference or property_obj.pk}.pdf"'
    return response
