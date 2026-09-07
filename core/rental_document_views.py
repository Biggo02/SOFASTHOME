from io import BytesIO

from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from .rental_models import RentalCase, RentalDocument


def _allowed(request, case):
    return request.user.is_staff or request.user.pk in {case.owner_id, case.tenant_id}


def _make_pdf(title, lines):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    c.setTitle(title)
    y = height - 52
    c.setFont('Helvetica-Bold', 16)
    c.drawString(45, y, 'FASTHOME')
    y -= 25
    c.setFont('Helvetica-Bold', 13)
    c.drawString(45, y, title)
    y -= 28
    c.setFont('Helvetica', 9)
    for text in lines:
        line = ''
        for word in str(text).split():
            candidate = f'{line} {word}'.strip()
            if c.stringWidth(candidate, 'Helvetica', 9) <= width - 90:
                line = candidate
            else:
                if line:
                    c.drawString(45, y, line)
                    y -= 13
                line = word
        if line:
            c.drawString(45, y, line)
            y -= 15
        if y < 70:
            c.showPage()
            y = height - 55
            c.setFont('Helvetica', 9)
    c.setFont('Helvetica', 7.5)
    c.drawString(45, 35, 'FASTHOME — Document prérempli à signer puis à téléverser pour vérification.')
    c.save()
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
        f'Dossier : {case.reference}', f'Bien : {prop.title} — {prop.reference}',
        f'Localisation : {prop.commune} — {prop.city} — {prop.province}',
        f'Adresse : {prop.full_address or "Non précisée"}',
        f'Constat : {visit.scheduled_date or visit.preferred_date or "À préciser"} à {visit.scheduled_time or visit.preferred_time or "À préciser"}',
        f'Propriétaire : {owner_name}', f'Locataire : {tenant_name}', '',
        'CARACTÉRISTIQUES PRÉREMPLIES DU BIEN', *_property_lines(prop), '',
        f'Observation de visite : {visit.observation or "Aucune observation enregistrée."}', '',
        'ÉTAT CONTRADICTOIRE À CONFIRMER',
        'Murs / peinture : _______________________________________________',
        'Sols : ___________________________________________________________',
        'Portes / fenêtres / serrures : _________________________________',
        'Installations eau / sanitaires : ______________________________',
        'Installation électrique : _______________________________________',
        'Mobilier / équipements : ________________________________________',
        'Compteurs et relevés : __________________________________________',
        'Clés remises : ___________________________________________________',
        'Réserves / observations complémentaires : _______________________',
        '__________________________________________________________________',
    ]
    specs = [
        ('owner_inspection', 'État des lieux — FASTHOME ↔ Propriétaire', 'EDL-PRO', 'Signature du propriétaire : ______________________________'),
        ('tenant_inspection', 'État des lieux — FASTHOME ↔ Locataire', 'EDL-LOC', 'Signature du locataire : _________________________________'),
    ]
    for doc_type, title, prefix, signature in specs:
        pdf = _make_pdf(title, common + ['', signature, 'Signature / visa FASTHOME : ______________________________', f'Référence : {prefix}-{case.reference}'])
        doc, _ = RentalDocument.objects.get_or_create(rental_case=case, document_type=doc_type, defaults={'label': title})
        if not doc.file or doc.status in {'required', 'prepared', 'rejected'}:
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
        f'Dossier : {case.reference}', f'Bien : {prop.title} — {prop.reference}',
        f'Localisation : {prop.commune} — {prop.city} — {prop.province}',
        f'Adresse : {prop.full_address or "Non précisée"}', f'Propriétaire : {owner}', f'Locataire : {tenant}',
        f'Constat : {visit.scheduled_date or visit.preferred_date or "À préciser"} à {visit.scheduled_time or visit.preferred_time or "À préciser"}',
        '', 'CARACTÉRISTIQUES DU BIEN', *_property_lines(prop), '',
        'ÉTAT CONTRADICTOIRE À CONFIRMER',
        'Murs / peinture : _______________________________________________', 'Sols : ___________________________________________________________',
        'Portes / fenêtres / serrures : _________________________________', 'Installations eau / sanitaires : ______________________________',
        'Installation électrique : _______________________________________', 'Mobilier / équipements : ________________________________________',
        'Compteurs et relevés : __________________________________________', 'Clés remises : ___________________________________________________',
        f'Observations de visite : {visit.observation or "Aucune observation enregistrée."}', '',
    ]
    if document == 'owner_pv':
        return _serve_pdf(request, case, 'ÉTAT DES LIEUX — FASTHOME ↔ PROPRIÉTAIRE', f'EDL-PRO-{case.reference}.pdf', common + ['Partie signataire : Propriétaire', 'Signature du propriétaire : ______________________________', 'Signature / visa FASTHOME : ______________________________'], case.owner_id)
    if document == 'tenant_pv':
        return _serve_pdf(request, case, 'ÉTAT DES LIEUX — FASTHOME ↔ LOCATAIRE', f'EDL-LOC-{case.reference}.pdf', common + ['Partie signataire : Locataire', 'Signature du locataire : _________________________________', 'Signature / visa FASTHOME : ______________________________'], case.tenant_id)
    return HttpResponseForbidden('Document inconnu.')
