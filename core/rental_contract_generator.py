from io import BytesIO
from pathlib import Path

from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, PageBreak

NAVY = colors.HexColor('#10243E')
GOLD = colors.HexColor('#F1B90B')
LIGHT = colors.HexColor('#F5F7FA')
MID = colors.HexColor('#D9E0E8')
TEXT = colors.HexColor('#253247')
MUTED = colors.HexColor('#667085')


def _p(text, style):
    return Paragraph(str(text).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('\n','<br/>'), style)


def _styles():
    s = getSampleStyleSheet()
    return {
        'title': ParagraphStyle('ct', parent=s['Title'], fontName='Helvetica-Bold', fontSize=17, leading=21, textColor=NAVY, spaceAfter=5),
        'sub': ParagraphStyle('cs', parent=s['Normal'], fontName='Helvetica', fontSize=8.2, leading=11, textColor=MUTED, spaceAfter=9),
        'section': ParagraphStyle('ce', parent=s['Heading2'], fontName='Helvetica-Bold', fontSize=10.2, leading=13, textColor=NAVY, spaceBefore=5, spaceAfter=5),
        'body': ParagraphStyle('cb', parent=s['BodyText'], fontName='Helvetica', fontSize=8.6, leading=12.2, textColor=TEXT, spaceAfter=5),
        'label': ParagraphStyle('cl', parent=s['BodyText'], fontName='Helvetica-Bold', fontSize=7.2, leading=9.5, textColor=MUTED),
        'value': ParagraphStyle('cv', parent=s['BodyText'], fontName='Helvetica', fontSize=8.1, leading=10.5, textColor=TEXT),
        'small': ParagraphStyle('cm', parent=s['BodyText'], fontName='Helvetica', fontSize=7.1, leading=9, textColor=MUTED),
    }


def _table(rows, styles, widths=(47*mm,121*mm)):
    t = Table([[_p(a.upper(), styles['label']), _p(b, styles['value'])] for a,b in rows], colWidths=widths, repeatRows=0)
    t.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(0,-1),LIGHT),('BOX',(0,0),(-1,-1),0.5,MID),('INNERGRID',(0,0),(-1,-1),0.3,MID),
        ('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),
        ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),
    ]))
    return t


def _section(story, title, text, styles):
    story.append(Paragraph(title, styles['section']))
    story.append(_p(text, styles['body']))


def _identity_rows(user, role):
    name = user.get_full_name() or user.username
    return [
        ('Identité / qualité', f'{name} — {role}'),
        ('Téléphone enregistré', user.username or 'Non renseigné'),
        ('E-mail enregistré', user.email or 'Non renseigné'),
        ('Pièce d’identité', 'Référence vérifiée dans le dossier FASTHOME : ______________________________'),
        ('Adresse / domicile', '____________________________________________________________'),
    ]


def _property_rows(prop):
    def choice(field, value):
        try: return dict(prop._meta.get_field(field).choices).get(value, value or 'Non précisé')
        except Exception: return value or 'Non précisé'
    return [
        ('Référence du bien', prop.reference),('Désignation', prop.title),('Type', choice('property_type', prop.property_type)),
        ('Adresse', prop.full_address or 'Non précisée'),('Province / ville / commune', f'{prop.province} / {prop.city} / {prop.commune or "Non précisée"}'),
        ('Composition', f'{prop.salons} salon(s), {prop.bedrooms} chambre(s), {prop.kitchens} cuisine(s), {prop.bathrooms} salle(s) de bain, {prop.toilets} toilette(s)'),
        ('Capacité', f'{prop.max_occupants} occupant(s) maximum'),('Niveaux', f'{prop.floors} niveau(x), étage {prop.floor_number}'),
        ('Sol / plafond', f'{choice("floor_type",prop.floor_type)} / {choice("ceiling_type",prop.ceiling_type)}'),
        ('Eau', f'{"Disponible" if prop.water else "Non disponible"} — {choice("water_source",prop.water_source)} — {prop.water_days_per_week} jour(s)/semaine'),
        ('Électricité', f'{"Disponible" if prop.electricity else "Non disponible"} — {choice("electricity_source",prop.electricity_source)} — {prop.electricity_days_per_week} jour(s)/semaine'),
        ('Sécurité / parking', f'{"Oui" if prop.security else "Non"} / {"Oui" if prop.parking else "Non"} ({prop.parking_spaces} place(s))'),
        ('Meublé', f'{"Oui" if prop.furnished else "Non"} — {prop.furnished_type or "Non précisé"}'),
        ('État déclaré', prop.condition or 'À constater contradictoirement'),
        ('Détails mobiliers', prop.furniture_details or 'Aucun détail enregistré.'),
    ]


def _page_header(canvas, doc, title, ref):
    w,h=A4
    logo=Path(settings.BASE_DIR)/'static'/'images'/'logo.png'
    if logo.exists():
        try: canvas.drawImage(ImageReader(str(logo)), 42, h-61, width=95, height=38, preserveAspectRatio=True, mask='auto')
        except Exception: pass
    if not logo.exists():
        canvas.setFillColor(NAVY); canvas.setFont('Helvetica-Bold',15); canvas.drawString(42,h-48,'FASTHOME')
    canvas.setStrokeColor(MID); canvas.line(42,h-69,w-42,h-69); canvas.line(42,40,w-42,40)
    canvas.setFillColor(NAVY); canvas.setFont('Helvetica-Bold',8.5); canvas.drawRightString(w-42,h-53,title.upper())
    canvas.setFillColor(MUTED); canvas.setFont('Helvetica',7); canvas.drawString(42,27,f'FASTHOME · {ref} · Document contractuel')
    canvas.drawRightString(w-42,27,f'Page {doc.page}')


def generate_contract_pdf(contract):
    case=contract.rental_case; prop=contract.property; owner=case.owner; tenant=case.tenant
    is_owner=contract.contract_type=='owner_agreement'
    party=owner if is_owner else tenant
    party_role='PROPRIÉTAIRE' if is_owner else 'LOCATAIRE / SOUS-LOCATAIRE'
    title='CONVENTION FASTHOME — PROPRIÉTAIRE' if is_owner else 'CONTRAT FASTHOME — LOCATAIRE / SOUS-LOCATION'
    ref=contract.reference
    amount=f'{contract.amount:,.0f} CDF'.replace(',',' ')
    deposit=f'{contract.deposit:,.0f} CDF'.replace(',',' ')
    margin=f'{getattr(prop,"margin",0):,.0f} CDF'.replace(',',' ')
    styles=_styles(); buf=BytesIO()
    doc=SimpleDocTemplate(buf,pagesize=A4,leftMargin=21*mm,rightMargin=21*mm,topMargin=27*mm,bottomMargin=18*mm,title=title,author='FASTHOME')
    story=[]
    story += [_p(title,styles['title']),_p(f'Ref. {ref} · Dossier {case.reference} · Monnaie contractuelle : FRANC CONGOLAIS (CDF)',styles['sub'])]
    story.append(_table([('Nature du document', 'Convention de gestion, location et autorisation de sous-location' if is_owner else 'Contrat de sous-location à usage résidentiel'),('Partie concernée', party.get_full_name() or party.username),('Date d’établissement', str(contract.created_at.date())),('Entrée en vigueur', str(contract.start_date or prop.availability_date or 'À définir')),('Échéance', str(contract.end_date or 'À définir'))],styles))
    story.append(Spacer(1,7)); story.append(Paragraph('I. IDENTIFICATION DES PARTIES',styles['section']))
    story.append(_table([('FASTHOME','Agence / intermédiaire gestionnaire — siège et coordonnées à compléter au dossier.'),*(_identity_rows(party,party_role)),('Autre partie', (tenant.get_full_name() or tenant.username) if is_owner else (owner.get_full_name() or owner.username))],styles))
    story.append(PageBreak())
    story += [_p('II. DÉSIGNATION DU BIEN ET CONDITIONS FINANCIÈRES',styles['title']),_p('Les caractéristiques ci-dessous sont reprises automatiquement du dossier du bien et constituent la description contractuelle de référence, sous réserve des constatations de l’état des lieux.',styles['sub']),_table(_property_rows(prop),styles)]
    story.append(Spacer(1,7)); story.append(_table([('Loyer mensuel contractuel',amount),('Garantie locative',deposit),('Marge FASTHOME',margin if is_owner else 'Incluse dans le prix de sous-location'),('Modalité de paiement','Paiement en francs congolais, selon échéancier et reçus FASTHOME enregistrés au dossier.'),('Preuve de paiement','Reçu FASTHOME / preuve conservée au dossier pour chaque paiement.')],styles))
    story.append(PageBreak())
    story += [_p('III. OBJET, DURÉE ET OBLIGATIONS',styles['title'])]
    if is_owner:
        clauses=[
        ('Article 1 — Objet','Le propriétaire confie à FASTHOME la gestion de la mise à disposition du bien décrit ci-dessus et autorise FASTHOME, dans les limites convenues et du droit applicable, à conclure et gérer la sous-location avec un occupant sélectionné par FASTHOME.'),
        ('Article 2 — Engagements du propriétaire','Le propriétaire garantit l’exactitude des informations communiquées, son droit de disposer du bien et l’absence d’empêchement juridique non déclaré. Il remet les documents justificatifs demandés et signale immédiatement toute modification affectant le bien.'),
        ('Article 3 — Pouvoir de FASTHOME','FASTHOME assure l’intermédiation, la sélection administrative du locataire, la préparation des documents, le suivi des paiements convenus, les états des lieux et la conservation des preuves dans le dossier.'),
        ('Article 4 — Loyer versé au propriétaire','Le montant convenu avec le propriétaire est celui indiqué dans les conditions financières. Tout changement doit faire l’objet d’un accord écrit conservé au dossier.'),
        ('Article 5 — État du bien','L’état du bien à l’entrée est établi contradictoirement. Les caractéristiques techniques et observations du présent contrat sont complétées par l’état des lieux signé.'),
        ('Article 6 — Accès et interventions','Les visites, réparations et interventions nécessaires sont organisées avec respect des droits de l’occupant et des procédures applicables, sauf urgence.'),
        ('Article 7 — Fin de la convention','La convention prend fin dans les conditions contractuelles et légales applicables, notamment par expiration, accord des parties, inexécution, perte du bien ou autre cause légalement admise.'),
        ]
    else:
        clauses=[
        ('Article 1 — Objet','FASTHOME donne en sous-location au locataire, qui accepte, le logement décrit dans le présent contrat pour un usage exclusivement résidentiel, sous réserve des droits et autorisations dont FASTHOME dispose légalement.'),
        ('Article 2 — Prise d’effet et durée','Le contrat prend effet à la date indiquée dans le dossier et se poursuit jusqu’au terme convenu ou jusqu’à sa cessation selon les règles contractuelles et légales applicables.'),
        ('Article 3 — Loyer','Le loyer mensuel dû à FASTHOME est fixé à '+amount+'. Il est payable en francs congolais selon l’échéancier convenu. Tout paiement doit être justifié par un reçu ou une preuve conservée au dossier.'),
        ('Article 4 — Garantie locative','La garantie est fixée à '+deposit+'. Toute retenue doit être liée à une dette ou à un dommage justifié et traitée conformément aux règles applicables.'),
        ('Article 5 — Destination et occupation','Le logement est exclusivement destiné à l’habitation. Le locataire respecte la capacité déclarée, la tranquillité du voisinage, les règles de sécurité et l’usage normal des équipements.'),
        ('Article 6 — Entretien et réparations','Le locataire assure l’entretien courant et signale rapidement les incidents. Les responsabilités pour réparations sont déterminées selon leur cause, le contrat, l’état des lieux et la réglementation applicable.'),
        ('Article 7 — Interdiction de sous-sous-location','Le locataire ne peut céder son contrat ni sous-louer à un tiers sans autorisation écrite de FASTHOME et sans respecter les exigences légales.'),
        ('Article 8 — État des lieux','L’état des lieux contradictoire signé par les parties constitue la référence pour l’état du logement, les compteurs, les clés, le mobilier et les réserves.'),
        ]
    for h,b in clauses:_section(story,h,b,styles)
    story.append(PageBreak())
    story += [_p('IV. IMPAYÉS, PRÉAVIS, RÉSILIATION ET LITIGES',styles['title'])]
    legal=[
    ('Article 9 — Paiements et impayés','Tout impayé est constaté et documenté. Les relances, mises en demeure, procédures administratives et judiciaires sont conduites conformément au droit applicable. Aucune expulsion forcée ou reprise irrégulière des lieux n’est autorisée.'),
    ('Article 10 — Préavis','Pour un bail résidentiel à durée indéterminée, le délai légal de préavis est de trois mois, sous réserve des textes en vigueur et des procédures administratives applicables. Le délai et la procédure réellement applicables au dossier doivent être respectés.'),
    ('Article 11 — Prolongation légale','Lorsque les conditions légales sont réunies, les éventuelles prorogations ou délais supplémentaires applicables au locataire résidentiel sont respectés.'),
    ('Article 12 — Résiliation','Le contrat peut prendre fin par expiration du terme, accord écrit, préavis légal, inexécution suffisamment établie, perte du bien, force majeure rendant le bien inhabitable ou autre cause prévue par la loi.'),
    ('Article 13 — Manquements graves','Sont notamment traités comme manquements graves : impayés atteignant le seuil légal applicable, sous-location non autorisée, changement de destination, dégradations volontaires, fraude documentaire, activités illicites ou troubles graves et répétés.'),
    ('Article 14 — Preuves et traçabilité','Les parties reconnaissent l’importance des pièces du dossier : contrat, état des lieux, photographies, reçus, preuves de paiement, notifications, échanges, pièces d’identité, décisions de validation et journaux de traitement FASTHOME. Chaque partie peut demander copie des pièces auxquelles elle a droit.'),
    ('Article 15 — Règlement amiable et juridiction','Tout différend est d’abord documenté et recherché à l’amiable. Lorsque la loi prévoit l’intervention du service compétent de l’Habitat ou une formalité préalable, celle-ci est respectée. À défaut de règlement, le litige est porté devant la juridiction compétente conformément au droit de la République démocratique du Congo.'),
    ('Article 16 — Force majeure et perte du bien','Les parties appliquent les règles légales relatives à la force majeure, à la perte ou à l’inhabitabilité du bien et prennent les mesures nécessaires pour limiter les préjudices.'),
    ]
    for h,b in legal:_section(story,h,b,styles)
    story.append(PageBreak())
    story += [_p('V. ÉTAT DES PIÈCES, DÉCLARATIONS ET SIGNATURES',styles)]
    story.append(_table([('Documents du dossier','Pièce d’identité · contrat · état des lieux · photographies · preuves de paiement · reçus · notifications · annexes'),('Déclaration','Les parties déclarent avoir lu le présent contrat, compris les obligations qui leur incombent et avoir eu la possibilité de demander toute clarification avant signature.'),('Exactitude','Toute correction manuscrite doit être paraphée par les parties. Toute page peut être paraphée afin d’éviter toute substitution.'),('Annexes','Les annexes signées ou référencées font partie intégrante du dossier contractuel lorsqu’elles sont identifiées par leur référence.')],styles))
    story.append(Spacer(1,10)); story.append(Paragraph('SIGNATURES — FAIT EN EXEMPLAIRES NÉCESSAIRES',styles['section']))
    sign_party='LE PROPRIÉTAIRE' if is_owner else 'LE LOCATAIRE'
    sign=Table([[_p(sign_party,styles['label']),_p('FASTHOME — REPRÉSENTANT HABILITÉ',styles['label'])],[_p(f'Nom : {party.get_full_name() or party.username}<br/>Téléphone : {party.username or ""}<br/><br/>Lu et approuvé<br/><br/>Signature : ___________________________<br/>Date : ____ / ____ / ______',styles['value']),_p('Nom : _________________________________<br/>Qualité : ______________________________<br/><br/>Lu et approuvé<br/><br/>Signature / cachet : ___________________<br/>Date : ____ / ____ / ______',styles['value'])]],colWidths=[84*mm,84*mm])
    sign.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),LIGHT),('BOX',(0,0),(-1,-1),0.6,MID),('INNERGRID',(0,0),(-1,-1),0.4,MID),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),14)])); story.append(sign)
    story.append(Spacer(1,9)); story.append(_p('Références juridiques indicatives : réglementation congolaise applicable aux baux à loyer, notamment la Loi n°15/025 du 31 décembre 2015 et les textes réglementaires en vigueur. Le présent modèle ne remplace pas une validation par un professionnel du droit pour un dossier litigieux ou atypique.',styles['small']))
    doc.build(story,onFirstPage=lambda c,d:_page_header(c,d,title,ref),onLaterPages=lambda c,d:_page_header(c,d,title,ref)); buf.seek(0); return buf.getvalue()
