from io import BytesIO
from pathlib import Path

from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle

PAGE_W, PAGE_H = A4
NAVY = colors.HexColor('#10243E')
GOLD = colors.HexColor('#F1B90B')
LIGHT = colors.HexColor('#F5F7FA')
MID = colors.HexColor('#D9E0E8')
TEXT = colors.HexColor('#253247')
MUTED = colors.HexColor('#667085')


def _logo_path():
    return Path(settings.BASE_DIR) / 'static' / 'images' / 'logo.png'


def _draw_logo(c):
    path = _logo_path()
    if path.exists():
        try:
            c.drawImage(ImageReader(str(path)), 42, PAGE_H - 62, width=100, height=38, preserveAspectRatio=True, mask='auto', anchor='sw')
            return
        except Exception:
            pass
    c.setFillColor(NAVY)
    c.setFont('Helvetica-Bold', 16)
    c.drawString(45, PAGE_H - 48, 'FASTHOME')


def _header(c, contract, page_title, page_no):
    _draw_logo(c)
    c.setStrokeColor(MID)
    c.setLineWidth(0.6)
    c.line(42, PAGE_H - 72, PAGE_W - 42, PAGE_H - 72)
    c.setFillColor(NAVY)
    c.setFont('Helvetica-Bold', 8.5)
    c.drawRightString(PAGE_W - 42, PAGE_H - 55, page_title.upper())
    c.setStrokeColor(MID)
    c.line(42, 43, PAGE_W - 42, 43)
    c.setFillColor(MUTED)
    c.setFont('Helvetica', 7.2)
    c.drawString(42, 28, f'FASTHOME · {contract.reference}')
    c.drawCentredString(PAGE_W / 2, 28, 'Document contractuel · À conserver')
    c.drawRightString(PAGE_W - 42, 28, f'Page {page_no} / 5')


def _title(c, contract, text, page_no):
    _header(c, contract, 'Contrat de sous-location à usage résidentiel', page_no)
    c.setFillColor(NAVY)
    c.setFont('Helvetica-Bold', 17)
    c.drawString(45, PAGE_H - 101, text)
    c.setFillColor(MUTED)
    c.setFont('Helvetica', 8.5)
    c.drawString(45, PAGE_H - 116, f'Référence contrat : {contract.reference} · Dossier : {contract.rental_case.reference}')
    c.setStrokeColor(GOLD)
    c.setLineWidth(2)
    c.line(45, PAGE_H - 126, 115, PAGE_H - 126)


def _wrap(c, text, x, y, width, font='Helvetica', size=9, leading=12.5):
    from reportlab.pdfbase.pdfmetrics import stringWidth
    c.setFont(font, size)
    words = str(text).split()
    line = ''
    for word in words:
        candidate = f'{line} {word}'.strip()
        if stringWidth(candidate, font, size) <= width:
            line = candidate
        else:
            if line:
                c.drawString(x, y, line)
                y -= leading
            line = word
    if line:
        c.drawString(x, y, line)
        y -= leading
    return y


def _section(c, heading, body, y, size=9, leading=12.5):
    c.setFillColor(NAVY)
    c.setFont('Helvetica-Bold', 10)
    c.drawString(48, y, heading)
    y -= 15
    c.setFillColor(TEXT)
    y = _wrap(c, body, 48, y, PAGE_W - 96, size=size, leading=leading)
    return y - 8


def _info_card(c, rows, y):
    data = []
    for label, value in rows:
        data.append([label.upper(), str(value)])
    table = Table(data, colWidths=[45 * mm, 119 * mm], rowHeights=None)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), LIGHT),
        ('TEXTCOLOR', (0, 0), (0, -1), MUTED),
        ('TEXTCOLOR', (1, 0), (1, -1), TEXT),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 8.2),
        ('LEADING', (0, 0), (-1, -1), 10.5),
        ('GRID', (0, 0), (-1, -1), 0.35, MID),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 7),
        ('RIGHTPADDING', (0, 0), (-1, -1), 7),
        ('TOPPADDING', (0, 0), (-1, -1), 5.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5.5),
    ]))
    _, h = table.wrapOn(c, PAGE_W - 90, y)
    table.drawOn(c, 45, y - h)
    return y - h - 12


def _signature_boxes(c, contract, y):
    c.setFillColor(NAVY)
    c.setFont('Helvetica-Bold', 10)
    c.drawString(48, y, 'SIGNATURES')
    y -= 14
    left = [
        ['PARTIE CONTRACTANTE', ''],
        ['Nom', contract.rental_case.owner.get_full_name() or contract.rental_case.owner.username if contract.contract_type == 'owner_agreement' else contract.rental_case.tenant.get_full_name() or contract.rental_case.tenant.username],
        ['Lu et approuvé', '________________________'],
        ['Signature', '________________________'],
        ['Date', '____ / ____ / ______'],
    ]
    right = [
        ['FASTHOME', ''],
        ['Représentant', '________________________'],
        ['Qualité', '________________________'],
        ['Signature / cachet', '________________________'],
        ['Date', '____ / ____ / ______'],
    ]
    data = []
    for a, b in zip(left, right):
        data.append([a[0] if a[1] == '' else f'{a[0]} : {a[1]}', b[0] if b[1] == '' else f'{b[0]} : {b[1]}'])
    table = Table(data, colWidths=[82 * mm, 82 * mm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), LIGHT),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 8.2),
        ('TEXTCOLOR', (0, 0), (-1, -1), TEXT),
        ('BOX', (0, 0), (-1, -1), 0.6, MID),
        ('INNERGRID', (0, 0), (-1, -1), 0.35, MID),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 9),
    ]))
    _, h = table.wrapOn(c, PAGE_W - 90, y)
    table.drawOn(c, 45, y - h)


def _contract_pdf(contract):
    case = contract.rental_case
    prop = contract.property
    owner = case.owner
    tenant = case.tenant
    owner_name = owner.get_full_name() or owner.username
    tenant_name = tenant.get_full_name() or tenant.username
    party_name = owner_name if contract.contract_type == 'owner_agreement' else tenant_name
    amount = contract.amount
    location = f'{prop.commune} — {prop.city} — {prop.province}'

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setTitle(f'FASTHOME — {contract.reference}')
    c.setAuthor('FASTHOME')

    # PAGE 1 — identification
    _title(c, contract, 'IDENTIFICATION ET OBJET', 1)
    y = PAGE_H - 151
    y = _info_card(c, [
        ('Dossier', case.reference), ('Bien', f'{prop.title} — {prop.reference}'), ('Localisation', location),
        ('Adresse', prop.full_address or 'Non précisée'), ('Propriétaire', owner_name), ('Locataire', tenant_name),
        ('Partie au contrat', party_name),
        ('Nature', 'Convention FASTHOME ↔ Propriétaire' if contract.contract_type == 'owner_agreement' else 'Contrat FASTHOME ↔ Locataire / sous-location'),
        ('Loyer mensuel', f'{amount} USD'), ('Garantie', f'{contract.deposit} USD'),
        ('Début', str(contract.start_date or prop.availability_date or 'À définir')), ('Fin', str(contract.end_date or 'À définir')),
    ], y)
    y = _section(c, 'ARTICLE 1 — OBJET', 'Le présent document formalise la relation contractuelle entre FASTHOME et la partie identifiée ci-dessus pour le logement indiqué. Les informations particulières enregistrées dans le dossier FASTHOME complètent le présent contrat.', y)
    _section(c, 'ARTICLE 2 — DÉSIGNATION DU LOGEMENT', f'Le logement est désigné par la référence {prop.reference}, situé dans la commune de {prop.commune}, ville/territoire de {prop.city}, province de {prop.province}. Il comprend {prop.salons} salon(s), {prop.bedrooms} chambre(s), {prop.kitchens} cuisine(s), {prop.bathrooms} salle(s) de bain et {prop.toilets} toilette(s). Capacité maximale enregistrée : {prop.max_occupants} occupant(s).', y)
    c.showPage()

    # PAGE 2
    _title(c, contract, 'CONDITIONS DE LA LOCATION', 2)
    y = PAGE_H - 151
    sections = [
        ('ARTICLE 3 — DURÉE', 'La durée, la date de prise d’effet et, lorsqu’elle est déterminée, la date de fin sont celles figurant dans les conditions particulières du dossier.'),
        ('ARTICLE 4 — LOYER', f'Le loyer mensuel applicable à la partie concernée est fixé à {amount} USD, sous réserve des conditions particulières enregistrées dans le dossier.'),
        ('ARTICLE 5 — GARANTIE', f'La garantie indiquée au dossier est de {contract.deposit} USD. Toute retenue éventuelle doit être justifiée conformément aux règles applicables.'),
        ('ARTICLE 6 — DESTINATION', 'Le logement est destiné exclusivement à un usage résidentiel. Toute utilisation contraire à cette destination ou aux règles applicables est interdite.'),
        ('ARTICLE 7 — OCCUPATION', f'Le logement est enregistré pour une capacité maximale de {prop.max_occupants} occupant(s). La composition déclarée dans le dossier constitue la référence administrative de la location.'),
        ('ARTICLE 8 — ENTRETIEN', 'La partie occupante utilise normalement les lieux, installations et équipements et signale sans délai les dégradations ou incidents importants.'),
        ('ARTICLE 9 — TRAVAUX ET MODIFICATIONS', 'Aucune modification substantielle du logement ne doit être entreprise sans l’accord requis et sans respecter les règles applicables.'),
        ('ARTICLE 10 — SOUS-LOCATION OU CESSION', 'La cession ou sous-sous-location clandestine est interdite. Toute opération autorisée doit respecter les conditions du contrat et les règles applicables.'),
        ('ARTICLE 11 — EAU, ÉLECTRICITÉ ET ÉQUIPEMENTS', f'Le logement est enregistré avec eau {"disponible" if prop.water else "non disponible"} et électricité {"disponible" if prop.electricity else "non disponible"}. Les équipements et leur état sont précisés dans le procès-verbal lorsqu’il est établi.'),
        ('ARTICLE 12 — ÉTAT DES LIEUX', 'Un état des lieux contradictoire peut être établi et signé. Il sert de référence pour l’état du logement, les équipements, les compteurs et les clés.'),
    ]
    for heading, body in sections:
        y = _section(c, heading, body, y, size=8.9)
    c.showPage()

    # PAGE 3
    _title(c, contract, 'OBLIGATIONS ET RÈGLES D’OCCUPATION', 3)
    y = PAGE_H - 151
    sections = [
        ('ARTICLE 13 — OBLIGATIONS DU PROPRIÉTAIRE', 'Le propriétaire fournit à FASTHOME les informations et documents nécessaires à la relation contractuelle et respecte les engagements convenus avec FASTHOME.'),
        ('ARTICLE 14 — OBLIGATIONS DE FASTHOME', 'FASTHOME assure la gestion de la relation avec le locataire dans le cadre de ses droits et obligations contractuels et organise les formalités prévues au dossier.'),
        ('ARTICLE 15 — OBLIGATIONS DU LOCATAIRE', 'Le locataire paie les sommes dues selon les modalités convenues, utilise paisiblement le logement, respecte sa destination et signale les incidents importants.'),
        ('ARTICLE 16 — ENTRETIEN COURANT', 'L’entretien courant et les obligations qui incombent à l’occupant sont exécutés conformément au contrat, au règlement intérieur et aux règles applicables.'),
        ('ARTICLE 17 — VISITES ET INTERVENTIONS', 'Les interventions nécessaires peuvent être organisées par FASTHOME dans les conditions prévues au contrat, avec information préalable lorsqu’elle est requise et hors urgence.'),
        ('ARTICLE 18 — RÈGLEMENT INTÉRIEUR', 'Le locataire respecte les règles de tranquillité, de sécurité, d’hygiène et d’usage des parties communes qui lui sont communiquées.'),
        ('ARTICLE 19 — DOCUMENTS ET NOTIFICATIONS', 'Les parties conservent les documents contractuels et utilisent des moyens permettant de prouver les notifications importantes.'),
        ('ARTICLE 20 — PAIEMENTS', 'Les paiements sont effectués hors ligne selon les modalités retenues par FASTHOME. Une preuve ou un reçu peut être enregistré dans le dossier.'),
        ('ARTICLE 21 — BONNE FOI', 'Les parties s’engagent à exécuter leurs obligations de bonne foi et à informer l’autre partie de tout événement important affectant l’exécution du contrat.'),
    ]
    for heading, body in sections:
        y = _section(c, heading, body, y, size=9)
    c.showPage()

    # PAGE 4
    _title(c, contract, 'SÉCURITÉ, IMPAYÉS, PRÉAVIS ET RÉSILIATION', 4)
    y = PAGE_H - 151
    sections = [
        ('ARTICLE 22 — TRANQUILLITÉ ET VOISINAGE', 'Le locataire respecte la tranquillité des voisins. Sont notamment prohibés : nuisances sonores excessives, violences ou menaces, activités illégales, détériorations volontaires, stockage interdit de produits dangereux et occupation abusive des parties communes.'),
        ('ARTICLE 23 — SÉCURITÉ', 'Le logement est utilisé normalement. Toute fuite d’eau, court-circuit, incendie, infiltration, fissure importante, effraction, dégradation importante ou danger sérieux doit être signalé sans délai.'),
        ('ARTICLE 24 — ACCÈS AU LOGEMENT', 'FASTHOME peut accéder au logement pour un motif légitime : réparation, maintenance, urgence, inspection nécessaire ou état des lieux. Sauf urgence, le locataire est informé au préalable et l’accès est organisé à un moment raisonnable.'),
        ('ARTICLE 25 — IMPAYÉS', 'En cas de non-paiement, FASTHOME applique les procédures légales de recouvrement et de résiliation. Aucune expulsion forcée n’est effectuée en dehors des procédures légales.'),
        ('ARTICLE 26 — PRÉAVIS', 'Le délai et la procédure de préavis du bail résidentiel sont ceux prévus par la réglementation applicable. Lorsque le délai légal applicable est de 3 mois, le locataire le respecte ainsi que la procédure requise. Le préavis est donné dans une forme permettant d’en rapporter la preuve.'),
        ('ARTICLE 27 — PROROGATION', 'Lorsque la réglementation applicable permet au locataire sans nouveau logement de bénéficier d’une prorogation après préavis, celle-ci est traitée conformément aux conditions légales et administratives.'),
        ('ARTICLE 28 — RÉSILIATION', 'Le contrat prend fin à son terme, par accord écrit, par préavis légal, pour manquement grave ou dans les autres cas prévus par la loi. Toute résiliation pour faute suit les procédures applicables.'),
        ('ARTICLE 29 — MANQUEMENTS GRAVES', 'Constituent notamment des manquements graves : falsification de documents, impayés persistants, sous-sous-location clandestine, dommage majeur intentionnel, activité illégale, trouble grave ou répété du voisinage et refus répété d’obligations essentielles.'),
        ('ARTICLE 30 — DÉCÈS OU ABANDON', 'En cas de décès du locataire, les règles légales relatives à la continuation ou à la fin du contrat s’appliquent. En cas de suspicion d’abandon, FASTHOME agit avec prudence et conformément aux procédures légales avant toute récupération des biens.'),
    ]
    for heading, body in sections:
        y = _section(c, heading, body, y, size=8.55, leading=11.5)
    c.showPage()

    # PAGE 5
    _title(c, contract, 'FIN DU CONTRAT, GARANTIE, LITIGES ET SIGNATURES', 5)
    y = PAGE_H - 151
    sections = [
        ('ARTICLE 31 — DÉPART ET RESTITUTION', 'Le locataire libère les lieux, restitue les clés et équipements, règle les sommes légalement dues et participe à l’état des lieux de sortie. L’usure normale est prise en compte.'),
        ('ARTICLE 32 — ÉTAT DES LIEUX DE SORTIE', 'L’état des lieux de sortie est contradictoire. Sont notamment comparés : murs, sols, plafonds, portes, fenêtres, installations, sanitaires, équipements, compteurs et clés. L’usure normale n’est pas facturée.'),
        ('ARTICLE 33 — GARANTIE ET RETENUES', 'Après le départ, FASTHOME vérifie les loyers, charges, clés, équipements et dommages imputables. Toute retenue est justifiée. Le solde de la garantie est traité conformément au droit applicable.'),
        ('ARTICLE 34 — FIN DU CONTRAT PRINCIPAL', 'Le locataire reconnaît que FASTHOME ne peut conférer des droits supérieurs à ceux dont elle dispose légalement sur le bien. Si un événement affectant le contrat principal modifie matériellement l’occupation, FASTHOME informe le locataire et prend les mesures légales nécessaires.'),
        ('ARTICLE 35 — FORCE MAJEURE', 'Aucune partie n’est responsable d’un manquement directement causé par un cas de force majeure légalement reconnu, sous réserve d’informer l’autre partie et de limiter les dommages.'),
        ('ARTICLE 36 — NOTIFICATIONS', 'FASTHOME : téléphone __________________ ; adresse __________________ ; email __________________. LOCATAIRE : téléphone __________________ ; adresse __________________ ; email __________________. Les notifications importantes sont effectuées dans une forme permettant d’en rapporter la preuve.'),
        ('ARTICLE 37 — RÈGLEMENT DES LITIGES', 'Les parties recherchent d’abord une solution amiable. Si la réglementation impose une conciliation auprès du service compétent de l’Habitat, elle est respectée. À défaut, le litige relève de la juridiction compétente conformément au droit de la RDC.'),
        ('ARTICLE 38 — DÉCLARATION DU LOCATAIRE', 'Le locataire déclare avoir visité le logement, reçu les informations essentielles, connaître son état, avoir lu et compris le présent contrat, avoir reçu ou pouvoir obtenir une copie et accepter les règles d’occupation.'),
    ]
    for heading, body in sections:
        y = _section(c, heading, body, y, size=8.15, leading=10.6)
    y -= 3
    c.setFillColor(NAVY)
    c.setFont('Helvetica-Bold', 9)
    c.drawString(48, y, 'Fait à ______________________________, le ____ / ____ / ______')
    y -= 18
    _signature_boxes(c, contract, y)
    c.save()
    buffer.seek(0)
    return buffer.getvalue()
