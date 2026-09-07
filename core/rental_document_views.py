from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .rental_models import RentalCase, RentalDocument

PAGE_W, PAGE_H = A4
NAVY = colors.HexColor('#10243E')
GOLD = colors.HexColor('#F1B90B')
LIGHT = colors.HexColor('#F5F7FA')
MID = colors.HexColor('#D9E0E8')
TEXT = colors.HexColor('#253247')
MUTED = colors.HexColor('#667085')


def _allowed(request, case):
    return request.user.is_staff or request.user.pk in {case.owner_id, case.tenant_id}


def _logo_path():
    return Path(settings.BASE_DIR) / 'static' / 'images' / 'logo.png'


def _draw_logo(c, width, height):
    logo = _logo_path()
    if logo.exists():
        try:
            c.drawImage(ImageReader(str(logo)), 45, height - 62, width=105, height=42, preserveAspectRatio=True, mask='auto', anchor='sw')
            return
        except Exception:
            pass
    c.setFillColor(NAVY)
    c.setFont('Helvetica-Bold', 16)
    c.drawString(45, height - 48, 'FASTHOME')


def _header_footer(c, title, reference, page_no):
    _draw_logo(c, PAGE_W, PAGE_H)
    c.setStrokeColor(MID)
    c.line(45, PAGE_H - 72, PAGE_W - 45, PAGE_H - 72)
    c.setFillColor(NAVY)
    c.setFont('Helvetica-Bold', 9)
    c.drawRightString(PAGE_W - 45, PAGE_H - 55, title.upper())
    c.setStrokeColor(MID)
    c.line(45, 42, PAGE_W - 45, 42)
    c.setFillColor(MUTED)
    c.setFont('Helvetica', 7.5)
    c.drawString(45, 27, f'FASTHOME · {reference}')
    c.drawRightString(PAGE_W - 45, 27, f'Page {page_no}')


def _doc_styles():
    styles = getSampleStyleSheet()
    return {
        'title': ParagraphStyle('fhTitle', parent=styles['Title'], fontName='Helvetica-Bold', fontSize=17, leading=21, textColor=NAVY, spaceAfter=6),
        'subtitle': ParagraphStyle('fhSubtitle', parent=styles['Normal'], fontName='Helvetica', fontSize=8.5, leading=12, textColor=MUTED, spaceAfter=12),
        'section': ParagraphStyle('fhSection', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=10, leading=13, textColor=NAVY, spaceBefore=7, spaceAfter=6),
        'body': ParagraphStyle('fhBody', parent=styles['BodyText'], fontName='Helvetica', fontSize=8.7, leading=12.5, textColor=TEXT, spaceAfter=5),
        'small': ParagraphStyle('fhSmall', parent=styles['BodyText'], fontName='Helvetica', fontSize=7.5, leading=10, textColor=MUTED),
        'label': ParagraphStyle('fhLabel', parent=styles['BodyText'], fontName='Helvetica-Bold', fontSize=7.5, leading=10, textColor=MUTED),
        'value': ParagraphStyle('fhValue', parent=styles['BodyText'], fontName='Helvetica', fontSize=8.3, leading=11, textColor=TEXT),
    }


def _p(text, style):
    return Paragraph(str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br/>'), style)


def _info_table(rows, styles):
    data = []
    for label, value in rows:
        data.append([_p(label.upper(), styles['label']), _p(value, styles['value'])])
    table = Table(data, colWidths=[42 * mm, 126 * mm], hAlign='LEFT')
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), LIGHT),
        ('BOX', (0, 0), (-1, -1), 0.5, MID),
        ('INNERGRID', (0, 0), (-1, -1), 0.35, MID),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 7),
        ('RIGHTPADDING', (0, 0), (-1, -1), 7),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    return table


def _section(title, rows, styles):
    data = [[_p(label, styles['label']), _p(value, styles['value'])] for label, value in rows]
    table = Table(data, colWidths=[54 * mm, 114 * mm], hAlign='LEFT')
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.white),
        ('BOX', (0, 0), (-1, -1), 0.5, MID),
        ('INNERGRID', (0, 0), (-1, -1), 0.35, MID),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 7),
        ('RIGHTPADDING', (0, 0), (-1, -1), 7),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    return [Paragraph(title.upper(), styles['section']), table, Spacer(1, 5)]


def _edl_story(title, case, document, styles):
    prop = case.property
    owner = case.owner.get_full_name() or case.owner.username
    tenant = case.tenant.get_full_name() or case.tenant.username
    visit = case.visit
    party = 'Propriétaire' if document == 'owner_pv' else 'Locataire'
    ref = f'{"EDL-PRO" if document == "owner_pv" else "EDL-LOC"}-{case.reference}'

    story = [
        _p(title, styles['title']),
        _p(f'Document officiel prérempli · Référence {ref} · À signer après vérification contradictoire', styles['subtitle']),
        _info_table([
            ('Dossier', case.reference),
            ('Bien', f'{prop.title} — {prop.reference}'),
            ('Localisation', f'{prop.commune or "Non précisée"} — {prop.city} — {prop.province}'),
            ('Adresse', prop.full_address or 'Non précisée'),
            ('Propriétaire', owner),
            ('Locataire', tenant),
            ('Partie signataire', party),
            ('Date / heure du constat', f'{visit.scheduled_date or visit.preferred_date or "À préciser"} · {visit.scheduled_time or visit.preferred_time or "À préciser"}'),
        ], styles),
        Spacer(1, 8),
    ]

    characteristics = [
        ('Type', _choice_label(prop, 'property_type', prop.property_type)),
        ('Composition', f'{prop.bedrooms} chambre(s) · {prop.salons} salon(s) · {prop.kitchens} cuisine(s)'),
        ('Sanitaires', f'{prop.bathrooms} salle(s) de bain · {prop.toilets} toilette(s) · {prop.shower_count} douche(s)'),
        ('Niveaux', f'Étage {prop.floor_number} · {prop.floors} niveau(x)'),
        ('Sol', _choice_label(prop, 'floor_type', prop.floor_type)),
        ('Plafond', _choice_label(prop, 'ceiling_type', prop.ceiling_type)),
        ('Eau', f'{"Disponible" if prop.water else "Non disponible"} · {_choice_label(prop, "water_source", prop.water_source)} · {prop.water_days_per_week} jour(s)/semaine'),
        ('Électricité', f'{"Disponible" if prop.electricity else "Non disponible"} · {_choice_label(prop, "electricity_source", prop.electricity_source)} · {prop.electricity_days_per_week} jour(s)/semaine'),
        ('Sécurité / parking', f'{"Oui" if prop.security else "Non"} · parking {"oui" if prop.parking else "non"} · {prop.parking_spaces} place(s)'),
        ('Meublé', f'{"Oui" if prop.furnished else "Non"} · {prop.furnished_type or "Non précisé"}'),
        ('État déclaré', prop.condition or 'À constater contradictoirement'),
    ]
    story += _section('1. Caractéristiques préremplies du logement', characteristics, styles)

    details = [
        ('Mobilier', prop.furniture_details or 'Aucun détail enregistré.'),
        ('Salles de bain', prop.bathroom_details or 'Aucun détail enregistré.'),
        ('Toilettes', prop.toilet_details or 'Aucun détail enregistré.'),
        ('Observation de visite', visit.observation or 'Aucune observation enregistrée.'),
    ]
    story += _section('2. Informations complémentaires', details, styles)

    story += [Paragraph('3. ÉTAT CONTRADICTOIRE À CONFIRMER', styles['section'])]
    inspection_rows = [
        ('Murs / peinture', '____________________________________________________________'),
        ('Sols', '____________________________________________________________'),
        ('Portes / fenêtres / serrures', '____________________________________________________________'),
        ('Eau / sanitaires', '____________________________________________________________'),
        ('Installation électrique', '____________________________________________________________'),
        ('Mobilier / équipements', '____________________________________________________________'),
        ('Compteurs / relevés', '____________________________________________________________'),
        ('Clés remises', '____________________________________________________________'),
        ('Réserves / observations', '____________________________________________________________'),
        ('Observations complémentaires', '____________________________________________________________'),
    ]
    table = Table([[_p(a, styles['label']), _p(b, styles['value'])] for a, b in inspection_rows], colWidths=[54 * mm, 114 * mm])
    table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.5, MID), ('INNERGRID', (0, 0), (-1, -1), 0.35, MID),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LEFTPADDING', (0, 0), (-1, -1), 7),
        ('RIGHTPADDING', (0, 0), (-1, -1), 7), ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story += [table, Spacer(1, 9)]

    signatures = Table([
        [_p(f'SIGNATURE {party.upper()}', styles['label']), _p('VISA / SIGNATURE FASTHOME', styles['label'])],
        [_p(f'Nom : {owner if document == "owner_pv" else tenant}<br/><br/>Signature : ___________________________<br/><br/>Date : ____ / ____ / ______', styles['value']), _p('Nom / qualité : _________________________<br/><br/>Signature / cachet : ____________________<br/><br/>Date : ____ / ____ / ______', styles['value'])],
    ], colWidths=[84 * mm, 84 * mm])
    signatures.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), LIGHT), ('BOX', (0, 0), (-1, -1), 0.6, MID),
        ('INNERGRID', (0, 0), (-1, -1), 0.4, MID), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8), ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
    ]))
    story += [Paragraph('4. SIGNATURES ET VALIDATION', styles['section']), signatures, Spacer(1, 6), _p('Document prérempli par FASTHOME. Toute information doit être vérifiée avant signature. Les réserves doivent être inscrites dans les espaces prévus.', styles['small'])]
    return story, ref


def _make_pdf(title, lines):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=22 * mm, leftMargin=22 * mm, topMargin=27 * mm, bottomMargin=18 * mm, title=title, author='FASTHOME')
    styles = _doc_styles()
    story = [_p(title, styles['title']), _p('Document FASTHOME à vérifier, compléter si nécessaire, signer puis téléverser pour validation.', styles['subtitle'])]
    rows = []
    for text in lines:
        if not text:
            if rows:
                story.append(_info_table(rows, styles)); story.append(Spacer(1, 7)); rows = []
            continue
        if text.isupper() and len(text) < 70:
            if rows:
                story.append(_info_table(rows, styles)); story.append(Spacer(1, 6)); rows = []
            story.append(Paragraph(text, styles['section']))
        elif ':' in text:
            label, value = text.split(':', 1)
            rows.append((label.strip(), value.strip()))
        else:
            if rows:
                story.append(_info_table(rows, styles)); story.append(Spacer(1, 6)); rows = []
            story.append(_p(text, styles['body']))
    if rows:
        story.append(_info_table(rows, styles))
    story += [Spacer(1, 8), Paragraph('SIGNATURES', styles['section'])]
    sig = Table([
        [_p('PARTIE CONCERNÉE', styles['label']), _p('FASTHOME', styles['label'])],
        [_p('Nom : _______________________________<br/><br/>Signature : ___________________________<br/><br/>Date : ____ / ____ / ______', styles['value']), _p('Nom / qualité : _________________________<br/><br/>Signature / cachet : ____________________<br/><br/>Date : ____ / ____ / ______', styles['value'])],
    ], colWidths=[84 * mm, 84 * mm])
    sig.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), LIGHT), ('BOX', (0, 0), (-1, -1), 0.5, MID), ('INNERGRID', (0, 0), (-1, -1), 0.35, MID), ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 8), ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 12)]))
    story.append(sig)

    def decorate(canvas, doc):
        _header_footer(canvas, title, title[:28], doc.page)

    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
    buffer.seek(0)
    return buffer.getvalue()


def _choice_label(prop, field_name, value):
    field = prop._meta.get_field(field_name)
    return dict(field.choices).get(value, value or 'Non précisé')


def _property_lines(prop):
    return [
        f'Type : {_choice_label(prop, "property_type", prop.property_type)}',
        f'Adresse : {prop.full_address or "Non précisée"}',
        f'Province / Ville / Commune : {prop.province} / {prop.city} / {prop.commune or "Non précisée"}',
        f'Pièces : {prop.bedrooms} chambre(s), {prop.salons} salon(s), {prop.kitchens} cuisine(s)',
        f'Sanitaires : {prop.bathrooms} salle(s) de bain, {prop.toilets} toilette(s), douches : {prop.shower_count}',
        f'Étage : {prop.floor_number} / niveaux : {prop.floors}',
        f'Sol : {_choice_label(prop, "floor_type", prop.floor_type)}',
        f'Plafond : {_choice_label(prop, "ceiling_type", prop.ceiling_type)}',
        f'Eau : {"Oui" if prop.water else "Non"} — source : {_choice_label(prop, "water_source", prop.water_source)} — {prop.water_days_per_week} jour(s)/semaine',
        f'Électricité : {"Oui" if prop.electricity else "Non"} — source : {_choice_label(prop, "electricity_source", prop.electricity_source)} — {prop.electricity_days_per_week} jour(s)/semaine',
        f'Sécurité : {"Oui" if prop.security else "Non"}',
        f'Parking : {"Oui" if prop.parking else "Non"} — places : {prop.parking_spaces}',
        f'Meublé : {"Oui" if prop.furnished else "Non"} — type : {prop.furnished_type or "Non précisé"}',
        f'État général déclaré : {prop.condition or "À constater contradictoirement"}',
        f'Détails mobilier : {prop.furniture_details or "Aucun détail enregistré"}',
        f'Détails salles de bain : {prop.bathroom_details or "Aucun détail enregistré"}',
        f'Détails toilettes : {prop.toilet_details or "Aucun détail enregistré"}',
    ]


def prepare_four_rental_documents(case):
    prop = case.property
    owner_name = case.owner.get_full_name() or case.owner.username
    tenant_name = case.tenant.get_full_name() or case.tenant.username
    visit = case.visit
    common = [
        f'Dossier : {case.reference}',
        f'Bien : {prop.title} — {prop.reference}',
        f'Localisation : {prop.commune} — {prop.city} — {prop.province}',
        f'Adresse : {prop.full_address or "Non précisée"}',
        f'Constat : {visit.scheduled_date or visit.preferred_date or "À préciser"} à {visit.scheduled_time or visit.preferred_time or "À préciser"}',
        f'Propriétaire : {owner_name}',
        f'Locataire : {tenant_name}',
        '',
        'CARACTÉRISTIQUES PRÉREMPLIES DU BIEN',
        *_property_lines(prop),
        '',
        f'Observation de visite : {visit.observation or "Aucune observation enregistrée."}',
        '',
        'ÉTAT CONTRADICTOIRE À CONFIRMER',
        'Murs / peinture : ____________________________________________________________',
        'Sols : _____________________________________________________________________',
        'Portes / fenêtres / serrures : ______________________________________________',
        'Installations eau / sanitaires : ____________________________________________',
        'Installation électrique : ___________________________________________________',
        'Mobilier / équipements : ___________________________________________________',
        'Compteurs et relevés : ______________________________________________________',
        'Clés remises : ______________________________________________________________',
        'Réserves / observations complémentaires : ___________________________________',
    ]
    specs = [
        ('owner_inspection', 'État des lieux — FASTHOME ↔ Propriétaire', 'EDL-PRO', 'Signature du propriétaire : ______________________________'),
        ('tenant_inspection', 'État des lieux — FASTHOME ↔ Locataire', 'EDL-LOC', 'Signature du locataire : _________________________________'),
    ]
    for doc_type, title, prefix, signature in specs:
        doc, _ = RentalDocument.objects.get_or_create(rental_case=case, document_type=doc_type, defaults={'label': title})
        if not doc.file:
            pdf = _make_pdf(title, common + ['', signature, 'Signature / visa FASTHOME : ______________________________', f'Reférence : {prefix}-{case.reference}'])
            doc.file.save(f'{prefix}-{case.reference}.pdf', ContentFile(pdf), save=False)
            doc.status = 'prepared'
            doc.notes = 'Document prérempli par FASTHOME, prêt à signature.'
            doc.save()
    case.documents.filter(document_type='inspection').update(status='rejected')


def _serve_pdf(request, case, title, filename, lines, party_id):
    if not _allowed(request, case):
        return HttpResponseForbidden('Accès refusé.')
    if not request.user.is_staff and request.user.pk != party_id:
        return HttpResponseForbidden('Ce document est réservé à la partie concernée.')
    response = HttpResponse(_make_pdf(title, lines), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def rental_support_document_pdf(request, pk, document):
    case = get_object_or_404(RentalCase.objects.select_related('property', 'owner', 'tenant', 'visit'), pk=pk)
    prop = case.property
    owner = case.owner.get_full_name() or case.owner.username
    tenant = case.tenant.get_full_name() or case.tenant.username
    visit = case.visit
    common = [
        f'Référence : {"EDL-PRO" if document == "owner_pv" else "EDL-LOC"}-{case.reference}',
        f'Dossier : {case.reference}',
        f'Bien : {prop.title} — {prop.reference}',
        f'Localisation : {prop.commune} — {prop.city} — {prop.province}',
        f'Adresse : {prop.full_address or "Non précisée"}',
        f'Propriétaire : {owner}',
        f'Locataire : {tenant}',
        f'Constat : {visit.scheduled_date or visit.preferred_date or "À préciser"} à {visit.scheduled_time or visit.preferred_time or "À préciser"}',
        '', 'CARACTÉRISTIQUES DU BIEN', *_property_lines(prop), '',
        'ÉTAT CONTRADICTOIRE À CONFIRMER',
        'Murs / peinture : ____________________________________________________________',
        'Sols : _____________________________________________________________________',
        'Portes / fenêtres / serrures : ______________________________________________',
        'Installations eau / sanitaires : ____________________________________________',
        'Installation électrique : ___________________________________________________',
        'Mobilier / équipements : ___________________________________________________',
        'Compteurs et relevés : ______________________________________________________',
        'Clés remises : ______________________________________________________________',
        f'Observations de visite : {visit.observation or "Aucune observation enregistrée."}', '',
    ]
    if document == 'owner_pv':
        return _serve_pdf(request, case, 'ÉTAT DES LIEUX — FASTHOME ↔ PROPRIÉTAIRE', f'EDL-PRO-{case.reference}.pdf', common + ['Partie signataire : Propriétaire', 'Signature du propriétaire : ______________________________', 'Signature / visa FASTHOME : ______________________________'], case.owner_id)
    if document == 'tenant_pv':
        return _serve_pdf(request, case, 'ÉTAT DES LIEUX — FASTHOME ↔ LOCATAIRE', f'EDL-LOC-{case.reference}.pdf', common + ['Partie signataire : Locataire', 'Signature du locataire : _________________________________', 'Signature / visa FASTHOME : ______________________________'], case.tenant_id)
    return HttpResponseForbidden('Document inconnu.')
