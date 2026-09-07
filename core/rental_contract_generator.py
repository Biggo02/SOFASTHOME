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
    return Paragraph(str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br/>'), style)


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


def _table(rows, styles, widths=(47*mm, 121*mm)):
    t = Table([[_p(a.upper(), styles['label']), _p(b, styles['value'])] for a, b in rows], colWidths=widths)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), LIGHT),
        ('BOX', (0, 0), (-1, -1), 0.5, MID),
        ('INNERGRID', (0, 0), (-1, -1), 0.3, MID),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 7),
        ('RIGHTPADDING', (0, 0), (-1, -1), 7),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
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
        try:
            return dict(prop._meta.get_field(field).choices).get(value, value or 'Non précisé')
        except Exception:
            return value or 'Non précisé'
    return [
        ('Référence du bien', prop.reference),
        ('Désignation', prop.title),
        ('Type', choice('property_type', prop.property_type)),
        ('Adresse précise du bien', prop.full_address or 'À renseigner lors de la signature'),
        ('Province / ville / commune', f'{prop.province} / {prop.city} / {prop.commune or "À renseigner"}'),
        ('Composition', f'{prop.salons} salon(s), {prop.bedrooms} chambre(s), {prop.kitchens} cuisine(s), {prop.bathrooms} salle(s) de bain, {prop.toilets} toilette(s)'),
        ('Capacité', f'{prop.max_occupants} occupant(s) maximum'),
        ('Niveaux', f'{prop.floors} niveau(x), étage {prop.floor_number}'),
        ('Sol / plafond', f'{choice("floor_type", prop.floor_type)} / {choice("ceiling_type", prop.ceiling_type)}'),
        ('Eau', f'{"Disponible" if prop.water else "Non disponible"} — {choice("water_source", prop.water_source)} — {prop.water_days_per_week} jour(s)/semaine'),
        ('Électricité', f'{"Disponible" if prop.electricity else "Non disponible"} — {choice("electricity_source", prop.electricity_source)} — {prop.electricity_days_per_week} jour(s)/semaine'),
        ('Sécurité / parking', f'{"Oui" if prop.security else "Non"} / {"Oui" if prop.parking else "Non"} ({prop.parking_spaces} place(s))'),
        ('Meublé', f'{"Oui" if prop.furnished else "Non"} — {prop.furnished_type or "Non précisé"}'),
        ('État déclaré', prop.condition or 'À constater contradictoirement'),
        ('Détails mobiliers', prop.furniture_details or 'Aucun détail enregistré.'),
    ]


def _page_header(canvas, doc, title, ref):
    w, h = A4
    logo = Path(settings.BASE_DIR) / 'static' / 'images' / 'logo.png'
    if logo.exists():
        try:
            canvas.drawImage(ImageReader(str(logo)), 42, h - 61, width=95, height=38, preserveAspectRatio=True, mask='auto')
        except Exception:
            pass
    if not logo.exists():
        canvas.setFillColor(NAVY)
        canvas.setFont('Helvetica-Bold', 15)
        canvas.drawString(42, h - 48, 'FASTHOME')
    canvas.setStrokeColor(MID)
    canvas.line(42, h - 69, w - 42, h - 69)
    canvas.line(42, 40, w - 42, 40)
    canvas.setFillColor(NAVY)
    canvas.setFont('Helvetica-Bold', 8.5)
    canvas.drawRightString(w - 42, h - 53, title.upper())
    canvas.setFillColor(MUTED)
    canvas.setFont('Helvetica', 7)
    canvas.drawString(42, 27, f'FASTHOME · {ref} · Document contractuel')
    canvas.drawRightString(w - 42, 27, f'Page {doc.page}')


def generate_contract_pdf(contract):
    case = contract.rental_case
    prop = contract.property
    owner = case.owner
    tenant = case.tenant
    is_owner = contract.contract_type == 'owner_agreement'
    party = owner if is_owner else tenant
    party_role = 'PROPRIÉTAIRE' if is_owner else 'LOCATAIRE / SOUS-LOCATAIRE'
    title = 'CONTRAT DE MISE EN LOCATION — FASTHOME / PROPRIÉTAIRE' if is_owner else 'CONTRAT DE SOUS-LOCATION — FASTHOME / LOCATAIRE'
    ref = contract.reference

    amount_value = contract.amount or 0
    deposit_value = contract.deposit or 0
    margin_value = getattr(prop, 'margin', 0) or 0
    amount = f'{amount_value:,.0f} CDF'.replace(',', ' ')
    deposit = f'{deposit_value:,.0f} CDF'.replace(',', ' ')
    margin = f'{margin_value:,.0f} CDF'.replace(',', ' ')

    styles = _styles()
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=21*mm, rightMargin=21*mm,
        topMargin=27*mm, bottomMargin=18*mm, title=title, author='FASTHOME'
    )
    story = []

    story += [
        _p(title, styles['title']),
        _p(f'Ref. {ref} · Dossier {case.reference} · Monnaie contractuelle : FRANC CONGOLAIS (CDF)', styles['sub'])
    ]
    story.append(_table([
        ('Nature du document', 'Contrat de mise en location du bien au profit de FASTHOME, avec autorisation expresse de sous-location' if is_owner else 'Contrat de sous-location à usage résidentiel conclu entre FASTHOME et le locataire'),
        ('Partie contractante', party.get_full_name() or party.username),
        ('Date d’établissement', str(contract.created_at.date())),
        ('Entrée en vigueur', str(contract.start_date or prop.availability_date or 'À définir')),
        ('Échéance', str(contract.end_date or 'À définir')),
    ], styles))

    story.append(Spacer(1, 7))
    story.append(Paragraph('I. IDENTIFICATION COMPLÈTE DES PARTIES', styles['section']))
    story.append(_table([
        ('FASTHOME', 'Agence gestionnaire et partie contractante. Dénomination, siège, téléphone, représentant légal et qualité : à compléter dans le dossier officiel FASTHOME.'),
        *_identity_rows(party, party_role),
        ('Autre partie au dossier', (tenant.get_full_name() or tenant.username) if is_owner else (owner.get_full_name() or owner.username)),
    ], styles))

    story.append(Spacer(1, 7))
    story.append(Paragraph('II. IDENTIFICATION PRÉCISE ET LOCALISATION DU BIEN', styles['section']))
    story.append(_p(
        'Avant la signature, les parties doivent se présenter en personne et vérifier contradictoirement l’identité, la qualité et l’adresse réelle du bien. La localisation précise doit être constatée sur place. Si elle n’est pas encore vérifiée, les champs concernés restent volontairement vierges et sont complétés manuscritement ou dans le dossier avant signature.',
        styles['body']
    ))
    story.append(_table([
        ('Référence interne', prop.reference),
        ('Désignation du bien', prop.title),
        ('Adresse précise constatée sur place', '________________________________________________________________________________'),
        ('Quartier / avenue / numéro', '________________________________________________________________________________'),
        ('Point de repère / localisation complémentaire', '________________________________________________________________________________'),
        ('Coordonnées GPS / Plus Code, si relevés', '________________________________________________________________________________'),
        ('Province / ville / commune', f'{prop.province} / {prop.city} / {prop.commune or "________________________"}'),
    ], styles))

    story.append(Spacer(1, 7))
    story.append(_table(_property_rows(prop), styles))

    story.append(Spacer(1, 7))
    story.append(_table([
        ('Loyer mensuel contractuel', amount),
        ('Garantie locative', deposit),
        ('Montant revenant au propriétaire', margin if is_owner else 'Non applicable dans ce contrat'),
        ('Modalité de paiement', 'Paiement en francs congolais, selon échéancier et reçus FASTHOME enregistrés au dossier.'),
        ('Preuve de paiement', 'Chaque paiement doit être matérialisé par un reçu ou une preuve conservée dans le dossier.'),
    ], styles))

    story.append(PageBreak())
    story += [_p('III. OBJET DU CONTRAT ET VOLONTÉ DES PARTIES', styles['title'])]

    if is_owner:
        clauses = [
            ('Article 1 — Nature du contrat', 'Le présent document est un CONTRAT DE MISE EN LOCATION conclu entre le PROPRIÉTAIRE et FASTHOME. Il ne constitue ni une vente, ni une promesse de vente, ni une cession de propriété. Le propriétaire met le bien à la disposition de FASTHOME contre le loyer convenu.'),
            ('Article 2 — Autorisation de sous-location', 'Le propriétaire autorise expressément FASTHOME à utiliser le bien dans le cadre de son activité de sous-location résidentielle et à conclure, gérer et suivre un contrat distinct avec l’occupant final, dans les limites du présent contrat et du droit applicable.'),
            ('Article 3 — Identification et vérification en personne', 'La signature intervient après vérification de l’identité du propriétaire et de sa qualité à mettre le bien en location. Les parties se rencontrent physiquement. La pièce d’identité, les justificatifs du droit sur le bien et les autres documents exigés sont référencés dans le dossier.'),
            ('Article 4 — Déclarations du propriétaire', 'Le propriétaire déclare disposer du droit nécessaire pour mettre le bien en location et autoriser sa sous-location. Il déclare également que les informations communiquées à FASTHOME sont exactes et signale tout litige, copropriété, mandat, hypothèque, restriction, occupation ou autre situation susceptible d’affecter la mise en location.'),
            ('Article 5 — Obligations de FASTHOME', 'FASTHOME prend en charge l’intermédiation et la gestion convenues : sélection administrative de l’occupant, préparation du contrat de sous-location, état des lieux, suivi des paiements, conservation des documents et gestion des incidents selon les procédures de l’agence.'),
            ('Article 6 — Loyer et rémunération', 'Le montant convenu avec le propriétaire est celui indiqué dans les conditions financières. Les éventuels frais, marges ou rémunérations de FASTHOME doivent être clairement identifiés dans le dossier et ne peuvent être modifiés unilatéralement sans base contractuelle.'),
            ('Article 7 — État et remise du bien', 'La remise du bien est constatée par un état des lieux détaillé, photographies, relevés de compteurs, inventaire éventuel du mobilier et remise des clés. Ces éléments constituent des annexes de référence.'),
            ('Article 8 — Accès et interventions', 'Les visites, contrôles, travaux et interventions sont organisés conformément au contrat, aux droits de l’occupant et aux règles applicables, sauf urgence nécessitant une intervention immédiate.'),
        ]
    else:
        clauses = [
            ('Article 1 — Nature du contrat', 'Le présent document est un CONTRAT DE SOUS-LOCATION À USAGE RÉSIDENTIEL conclu entre FASTHOME et le LOCATAIRE. Il ne constitue ni une vente, ni une promesse de vente, ni un transfert de propriété.'),
            ('Article 2 — Parties contractantes', 'FASTHOME est le cocontractant du locataire dans la sous-location. Le locataire ne contracte pas directement avec le propriétaire au titre du présent document. Les relations avec le propriétaire relèvent du contrat distinct conclu entre le propriétaire et FASTHOME.'),
            ('Article 3 — Vérification en personne', 'Avant la signature, FASTHOME et le locataire se rencontrent en personne pour vérifier l’identité, les coordonnées et les documents nécessaires. Le locataire reconnaît avoir eu la possibilité de visiter et d’examiner le logement.'),
            ('Article 4 — Désignation du logement', 'Le logement loué est celui décrit et localisé dans le présent contrat et dans l’état des lieux. Toute différence entre les informations déclarées et la réalité constatée doit être signalée avant signature et consignée au dossier.'),
            ('Article 5 — Prise d’effet et durée', 'Le contrat prend effet à la date indiquée dans le dossier et se poursuit jusqu’au terme convenu ou jusqu’à sa cessation selon les règles contractuelles et légales applicables.'),
            ('Article 6 — Loyer', f'Le loyer mensuel dû à FASTHOME est fixé à {amount}. Il est payable exclusivement selon les modalités convenues et documentées. Tout paiement doit être justifié par un reçu FASTHOME ou une preuve conservée au dossier.'),
            ('Article 7 — Garantie locative', f'La garantie locative est fixée à {deposit}. Toute retenue doit être justifiée par une dette, une dégradation ou une autre obligation établie et traitée conformément aux règles applicables.'),
            ('Article 8 — Destination et occupation', 'Le logement est destiné exclusivement à l’habitation. Le locataire respecte la capacité du logement, les règles de voisinage, la sécurité, l’usage normal des installations et les obligations prévues par le contrat.'),
            ('Article 9 — Entretien et réparations', 'Le locataire assure l’entretien courant et signale sans délai les incidents. Les responsabilités relatives aux réparations sont déterminées selon leur cause, l’état des lieux, le contrat et le droit applicable.'),
            ('Article 10 — Interdiction de sous-sous-location', 'Le locataire ne peut céder le présent contrat ni sous-louer à un tiers sans autorisation écrite de FASTHOME et sans respecter les exigences légales.'),
            ('Article 11 — État des lieux', 'L’état des lieux signé constitue la référence pour l’état du logement, les compteurs, les clés, le mobilier, les équipements et les réserves constatées à l’entrée.'),
        ]

    for h, b in clauses:
        _section(story, h, b, styles)

    story.append(PageBreak())
    story += [_p('IV. IMPAYÉS, PRÉAVIS, RÉSILIATION ET LITIGES', styles['title'])]
    legal = [
        ('Article 12 — Paiements et impayés', 'Tout impayé est constaté et documenté. Les relances, mises en demeure et éventuelles procédures sont conduites conformément au droit applicable. Aucune expulsion forcée ou reprise irrégulière des lieux ne peut être pratiquée.'),
        ('Article 13 — Préavis', 'Pour un bail résidentiel à durée indéterminée, le délai légal de préavis applicable est de trois mois, sous réserve des textes en vigueur et de la situation précise du dossier. La procédure et les formalités réellement applicables doivent être respectées.'),
        ('Article 14 — Résiliation', 'Le contrat peut prendre fin notamment par expiration du terme, accord écrit, préavis, inexécution suffisamment établie, perte du bien, force majeure rendant le logement inhabitable ou autre cause légalement admise.'),
        ('Article 15 — Manquements graves', 'Sont notamment documentés comme manquements graves les impayés atteignant le seuil légal applicable, la sous-location non autorisée, le changement de destination, les dégradations volontaires, la fraude documentaire, les activités illicites et les troubles graves ou répétés.'),
        ('Article 16 — Dossier de preuve', 'Le dossier contractuel peut comprendre les pièces d’identité, justificatifs du droit sur le bien, contrats, états des lieux, photographies datées, relevés de compteurs, inventaires, reçus, preuves de paiement, notifications, mises en demeure, rapports d’incident, demandes de réparation, avenants, documents de sortie et journaux de validation FASTHOME.'),
        ('Article 17 — Règlement des différends', 'Tout différend est d’abord documenté et, lorsque cela est possible et approprié, recherché à l’amiable. Les formalités administratives ou procédures préalables prévues par le droit applicable sont respectées avant toute saisine de la juridiction compétente.'),
        ('Article 18 — Force majeure et perte du bien', 'Les parties appliquent les règles légales relatives à la force majeure, à la perte ou à l’inhabitabilité du bien et prennent les mesures nécessaires pour limiter les préjudices.'),
    ]
    for h, b in legal:
        _section(story, h, b, styles)

    story.append(PageBreak())
    story += [_p('V. PIÈCES CONTRACTUELLES, DÉCLARATIONS ET SIGNATURES', styles['title'])]
    story.append(_table([
        ('Pièces obligatoires à vérifier', 'Pièces d’identité des parties · justificatif du droit du propriétaire sur le bien · contrat correspondant · état des lieux · photographies · relevés de compteurs · inventaire éventuel · documents complémentaires requis.'),
        ('Rencontre des parties', 'Les parties attestent s’être présentées physiquement pour l’identification et la signature, sauf procédure exceptionnelle expressément documentée par FASTHOME.'),
        ('Localisation du bien', 'L’adresse précise et la localisation réelle du bien doivent être vérifiées sur place. Les champs non encore vérifiés restent vierges et sont complétés avant signature.'),
        ('Déclaration', 'Les parties déclarent avoir lu le document, compris leurs obligations et pouvoir demander toute clarification avant de signer.'),
        ('Corrections', 'Toute correction manuscrite ou ajout doit être approuvé et paraphé par les parties concernées. Les pages peuvent être paraphées afin de prévenir toute substitution.'),
        ('Annexes', 'Les annexes identifiées par référence et signées ou validées selon la procédure FASTHOME font partie intégrante du dossier contractuel.'),
    ], styles))

    story.append(Spacer(1, 10))
    story.append(Paragraph('SIGNATURES — APRÈS VÉRIFICATION EN PERSONNE', styles['section']))
    sign_party = 'LE PROPRIÉTAIRE' if is_owner else 'LE LOCATAIRE / SOUS-LOCATAIRE'
    sign = Table([
        [_p(sign_party, styles['label']), _p('FASTHOME — REPRÉSENTANT HABILITÉ', styles['label'])],
        [_p(
            f'Nom : {party.get_full_name() or party.username}<br/>Téléphone : {party.username or ""}<br/><br/>'
            'Pièce vérifiée : ___________________________<br/>'
            'Lieu de signature : __________________________<br/><br/>'
            'Lu et approuvé<br/><br/>Signature : ___________________________<br/>'
            'Date : ____ / ____ / ______', styles['value']),
         _p(
            'Nom : _________________________________<br/>Qualité : ______________________________<br/>'
            'Pièce / mandat vérifié : __________________<br/>'
            'Lieu de signature : _______________________<br/><br/>'
            'Lu et approuvé<br/><br/>Signature / cachet : ___________________<br/>'
            'Date : ____ / ____ / ______', styles['value'])]
    ], colWidths=[84*mm, 84*mm])
    sign.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), LIGHT),
        ('BOX', (0, 0), (-1, -1), 0.6, MID),
        ('INNERGRID', (0, 0), (-1, -1), 0.4, MID),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 14),
    ]))
    story.append(sign)
    story.append(Spacer(1, 9))
    story.append(_p(
        'Le présent document est conçu comme une pièce contractuelle structurée et traçable. Sa valeur dans un litige dépend notamment de l’identité des parties, des signatures, des justificatifs, des annexes, des preuves conservées et des formalités légalement requises. Pour un dossier atypique ou contentieux, une validation par un professionnel du droit en République démocratique du Congo est recommandée.',
        styles['small']
    ))

    doc.build(
        story,
        onFirstPage=lambda c, d: _page_header(c, d, title, ref),
        onLaterPages=lambda c, d: _page_header(c, d, title, ref),
    )
    buf.seek(0)
    return buf.getvalue()
