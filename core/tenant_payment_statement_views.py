from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from .rental_models import RentalContract, RentalPayment


def _money(value):
    return f'{Decimal(value or 0):,.2f}'.replace(',', ' ').replace('.', ',') + ' CDF'


@login_required
def tenant_payment_statement(request, pk):
    """Relevé strictement privé des paiements du locataire pour son contrat."""
    contract = get_object_or_404(
        RentalContract.objects.select_related('rental_case', 'property', 'party'),
        pk=pk,
        contract_type='tenant_sublease',
    )
    if request.user.pk != contract.party_id and not request.user.is_staff:
        return HttpResponseForbidden('Ce relevé ne vous est pas destiné.')

    case = contract.rental_case
    payments = list(
        RentalPayment.objects.filter(
            contract=contract,
            rental_case=case,
            tenant=contract.party,
        ).order_by('payment_date', 'id')
    )

    # Compatibilité avec les dossiers existants créés avant l'historique RentalPayment.
    if not payments and case.rent_payment_date and case.rent_payment_amount:
        payments.append({
            'payment_type': 'rent',
            'payment_date': case.rent_payment_date,
            'reference': 'Dossier ' + case.reference,
            'amount': case.rent_payment_amount,
        })
        if case.guarantee_amount:
            payments.append({
                'payment_type': 'guarantee',
                'payment_date': case.rent_payment_date,
                'reference': 'Dossier ' + case.reference,
                'amount': case.guarantee_amount,
            })

    total_paid = sum((item['amount'] if isinstance(item, dict) else item.amount) or 0 for item in payments)

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="releve-locataire-{contract.reference}.pdf"'
    doc = SimpleDocTemplate(
        response, pagesize=A4, rightMargin=16*mm, leftMargin=16*mm,
        topMargin=17*mm, bottomMargin=17*mm,
        title=f'Relevé locataire {contract.reference}',
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle('TitleFast', parent=styles['Title'], fontName='Helvetica-Bold', fontSize=17, textColor=colors.HexColor('#17324d'), alignment=TA_CENTER, spaceAfter=4)
    small = ParagraphStyle('SmallFast', parent=styles['Normal'], fontSize=8.5, textColor=colors.HexColor('#64748b'), leading=12)
    right = ParagraphStyle('RightFast', parent=small, alignment=TA_RIGHT)
    story = []
    story.append(Paragraph('FASTHOME', title))
    story.append(Paragraph('RELEVÉ DES PAIEMENTS — LOCATAIRE', ParagraphStyle('Sub', parent=title, fontSize=11, textColor=colors.HexColor('#b18a2b'))))
    story.append(Spacer(1, 7*mm))

    identity = [
        ['Contrat', contract.reference],
        ['Dossier', case.reference],
        ['Logement', contract.property.title or '—'],
        ['Locataire', contract.party.get_full_name() or contract.party.username],
        ['Période', f'{contract.start_date or "—"} → {contract.end_date or "—"}'],
        ['Statut', case.get_status_display()],
    ]
    t = Table(identity, colWidths=[36*mm, 142*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (0,-1), colors.HexColor('#f2f5f8')),
        ('TEXTCOLOR', (0,0), (0,-1), colors.HexColor('#526273')),
        ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
        ('FONTNAME', (1,0), (1,-1), 'Helvetica'),
        ('FONTSIZE', (0,0), (-1,-1), 8.5),
        ('GRID', (0,0), (-1,-1), .4, colors.HexColor('#d9e0e7')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 6), ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t)
    story.append(Spacer(1, 7*mm))

    story.append(Paragraph('Historique des sommes enregistrées', ParagraphStyle('H', parent=styles['Heading2'], fontSize=11, textColor=colors.HexColor('#17324d'), spaceAfter=4)))
    rows = [['Date', 'Nature', 'Référence', 'Montant']]
    labels = {'rent': 'Loyer', 'guarantee': 'Garantie', 'other': 'Autre paiement'}
    for item in payments:
        if isinstance(item, dict):
            kind = item['payment_type']; date = item['payment_date']; ref = item['reference']; amount = item['amount']
        else:
            kind = item.payment_type; date = item.payment_date; ref = item.reference; amount = item.amount
        rows.append([date.strftime('%d/%m/%Y'), labels.get(kind, kind), ref or '—', _money(amount)])
    if len(rows) == 1:
        rows.append(['—', 'Aucun paiement', 'Aucune écriture enregistrée', _money(0)])
    table = Table(rows, colWidths=[27*mm, 38*mm, 67*mm, 46*mm], repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#17324d')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('GRID', (0,0), (-1,-1), .4, colors.HexColor('#d9e0e7')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8fafc')]),
        ('ALIGN', (3,1), (3,-1), 'RIGHT'),
        ('TOPPADDING', (0,0), (-1,-1), 6), ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(table)
    story.append(Spacer(1, 7*mm))

    totals = Table([
        ['Loyer contractuel', _money(contract.amount)],
        ['Garantie contractuelle', _money(contract.deposit)],
        ['Total des paiements enregistrés', _money(total_paid)],
    ], colWidths=[115*mm, 63*mm])
    totals.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f2f5f8')),
        ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
        ('FONTNAME', (1,0), (1,-1), 'Helvetica-Bold'),
        ('ALIGN', (1,0), (1,-1), 'RIGHT'),
        ('FONTSIZE', (0,0), (-1,-1), 8.5),
        ('GRID', (0,0), (-1,-1), .4, colors.HexColor('#d9e0e7')),
        ('TOPPADDING', (0,0), (-1,-1), 7), ('BOTTOMPADDING', (0,0), (-1,-1), 7),
    ]))
    story.append(totals)
    story.append(Spacer(1, 8*mm))
    story.append(Paragraph('Ce relevé concerne uniquement les paiements enregistrés pour ce contrat locataire. Les versements de FASTHOME au propriétaire sont suivis dans un relevé distinct et ne sont pas exposés ici.', small))
    story.append(Spacer(1, 3*mm))
    story.append(Paragraph('FASTHOME · Document généré depuis le dossier contractuel · Montants en Franc congolais (CDF)', small))
    doc.build(story)
    return response
