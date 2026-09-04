from io import BytesIO

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


def _draw_wrapped(c, text, x, y, width, leading=13, font='Helvetica', size=9.5):
    from reportlab.pdfbase.pdfmetrics import stringWidth
    words = str(text).split()
    line = ''
    c.setFont(font, size)
    for word in words:
        candidate = f'{line} {word}'.strip()
        if stringWidth(candidate, font, size) <= width:
            line = candidate
        else:
            c.drawString(x, y, line)
            y -= leading
            line = word
    if line:
        c.drawString(x, y, line)
        y -= leading
    return y


def _contract_pdf(contract):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    import qrcode

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    case = contract.rental_case
    prop = contract.property
    owner = case.owner
    tenant = case.tenant
    owner_name = owner.get_full_name() or owner.username
    tenant_name = tenant.get_full_name() or tenant.username
    party_name = owner_name if contract.contract_type == 'owner_agreement' else tenant_name
    amount = contract.amount
    location = f'{prop.commune} — {prop.city} — {prop.province}'

    def header(page_title, page_no):
        c.setFont('Helvetica-Bold', 15)
        c.drawString(45, height - 48, 'FASTHOME')
        c.setFont('Helvetica-Bold', 12)
        c.drawRightString(width - 45, height - 48, page_title)
        c.setFont('Helvetica', 8)
        c.drawString(45, 28, f'FASTHOME — {contract.reference} — PAGE {page_no}/5')
        c.drawRightString(width - 45, 28, case.reference)

    def title(text, page_no):
        header('CONTRAT DE SOUS-LOCATION À USAGE RÉSIDENTIEL', page_no)
        c.setFont('Helvetica-Bold', 17)
        c.drawString(45, height - 82, text)
        c.setFont('Helvetica', 9)
        c.drawString(45, height - 100, f'Référence : {contract.reference}')

    # Page 1
    title('IDENTIFICATION ET OBJET', 1)
    y = height - 135
    intro = [
        ('DOSSIER', case.reference), ('BIEN', f'{prop.title} — {prop.reference}'), ('LOCALISATION', location),
        ('PROPRIÉTAIRE', owner_name), ('LOCATAIRE', tenant_name), ('PARTIE AU PRÉSENT CONTRAT', party_name),
        ('TYPE DE CONTRAT', 'Convention FASTHOME ↔ Propriétaire' if contract.contract_type == 'owner_agreement' else 'Contrat FASTHOME ↔ Locataire / sous-location'),
        ('LOYER MENSUEL', f'{amount} USD'), ('GARANTIE', f'{contract.deposit} USD'),
        ('DATE DE DÉBUT', str(contract.start_date or prop.availability_date or 'À définir')), ('DATE DE FIN', str(contract.end_date or 'À définir')),
    ]
    for label, value in intro:
        c.setFont('Helvetica-Bold', 9); c.drawString(50, y, f'{label} :')
        c.setFont('Helvetica', 9); y = _draw_wrapped(c, value, 170, y, 350, 12, size=9)
        y -= 5
    y -= 4
    c.setFont('Helvetica-Bold', 11); c.drawString(50, y, 'ARTICLE 1 — OBJET')
    y -= 17
    y = _draw_wrapped(c, 'Le présent document formalise la relation contractuelle entre FASTHOME et la partie identifiée ci-dessus pour le bien indiqué. Les informations particulières sont celles enregistrées dans le dossier de location FASTHOME.', 50, y, width - 100)
    y -= 7
    c.setFont('Helvetica-Bold', 11); c.drawString(50, y, 'ARTICLE 2 — DÉSIGNATION DU LOGEMENT')
    y -= 17
    y = _draw_wrapped(c, f'Le logement est désigné par la référence {prop.reference}, situé dans la commune de {prop.commune}, ville/territoire de {prop.city}, province de {prop.province}. Il comprend notamment {prop.salons} salon(s), {prop.bedrooms} chambre(s), {prop.kitchens} cuisine(s), {prop.bathrooms} salle(s) de bain et {prop.toilets} toilette(s). Capacité maximale enregistrée : {prop.max_occupants} occupant(s).', 50, y, width - 100)
    c.showPage()

    # Page 2
    title('CONDITIONS DE LA LOCATION', 2)
    y = height - 135
    sections = [
        ('ARTICLE 3 — DURÉE', 'La durée, la date de prise d’effet et, lorsqu’elle est déterminée, la date de fin sont celles figurant dans le dossier et dans les champs particuliers du présent contrat.'),
        ('ARTICLE 4 — LOYER', f'Le loyer mensuel applicable à la partie concernée est fixé à {amount} USD, sous réserve des conditions particulières enregistrées dans le dossier.'),
        ('ARTICLE 5 — GARANTIE', f'La garantie indiquée au dossier est de {contract.deposit} USD. Toute retenue éventuelle doit être justifiée conformément aux règles applicables.'),
        ('ARTICLE 6 — DESTINATION', 'Le logement est destiné à un usage résidentiel. Toute utilisation contraire à cette destination ou aux règles applicables est interdite.'),
        ('ARTICLE 7 — OCCUPATION', f'Le logement est enregistré pour une capacité maximale de {prop.max_occupants} occupant(s). La composition déclarée dans le dossier constitue la référence administrative de la location.'),
        ('ARTICLE 8 — ENTRETIEN', 'La partie occupante utilise normalement les lieux, les installations et équipements et signale sans délai les dégradations ou incidents importants.'),
        ('ARTICLE 9 — TRAVAUX ET MODIFICATIONS', 'Aucune modification substantielle du logement ne doit être entreprise sans l’accord requis et sans respecter les règles applicables.'),
        ('ARTICLE 10 — SOUS-LOCATION OU CESSION', 'La cession ou sous-sous-location clandestine est interdite. Toute opération autorisée doit respecter les conditions du contrat et les règles applicables.'),
        ('ARTICLE 11 — EAU, ÉLECTRICITÉ ET ÉQUIPEMENTS', f'Le logement est enregistré avec les informations suivantes : eau {"disponible" if prop.water else "non disponible"}, électricité {"disponible" if prop.electricity else "non disponible"}. Les équipements et leur état sont précisés dans le procès-verbal lorsque celui-ci est établi.'),
        ('ARTICLE 12 — ÉTAT DES LIEUX', 'Un état des lieux contradictoire peut être établi et signé. Il sert de référence pour l’état du logement, les équipements, les compteurs et les clés.'),
    ]
    for heading, body in sections:
        c.setFont('Helvetica-Bold', 10.5); c.drawString(50, y, heading); y -= 16
        y = _draw_wrapped(c, body, 50, y, width - 100, 13, size=9.2); y -= 9
    c.showPage()

    # Page 3
    title('OBLIGATIONS ET RÈGLES D’OCCUPATION', 3)
    y = height - 135
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
        c.setFont('Helvetica-Bold', 10.5); c.drawString(50, y, heading); y -= 16
        y = _draw_wrapped(c, body, 50, y, width - 100, 13, size=9.2); y -= 9
    c.showPage()

    # Page 4 — clauses fournies comme référence
    title('SÉCURITÉ, IMPAYÉS, PRÉAVIS ET RÉSILIATION', 4)
    y = height - 135
    sections = [
        ('ARTICLE 22 — TRANQUILLITÉ ET VOISINAGE', 'Le locataire respecte la tranquillité des voisins. Sont notamment prohibés : nuisances sonores excessives, violences ou menaces, activités illégales, détériorations volontaires, stockage interdit de produits dangereux et occupation abusive des parties communes.'),
        ('ARTICLE 23 — SÉCURITÉ', 'Le logement est utilisé normalement. Toute fuite d’eau, court-circuit, incendie, infiltration, fissure importante, effraction, dégradation importante ou danger sérieux doit être signalé sans délai.'),
        ('ARTICLE 24 — ACCÈS AU LOGEMENT', 'FASTHOME peut accéder au logement pour un motif légitime : réparation, maintenance, urgence, inspection nécessaire ou état des lieux. Sauf urgence, le locataire est informé au préalable et l’accès est organisé à un moment raisonnable.'),
        ('ARTICLE 25 — IMPAYÉS', 'En cas de non-paiement, FASTHOME applique les procédures légales de recouvrement et de résiliation. Le locataire reste redevable des sommes légalement dues jusqu’à la fin régulière du contrat. Aucune expulsion forcée n’est effectuée en dehors des procédures légales.'),
        ('ARTICLE 26 — PRÉAVIS', 'Le délai et la procédure de préavis du bail résidentiel sont ceux prévus par la réglementation applicable. Lorsque le délai légal applicable est de 3 mois, le locataire le respecte ainsi que la procédure requise. Le préavis est donné dans une forme permettant d’en rapporter la preuve. Lorsqu’une procédure administrative auprès du service compétent de l’Habitat est requise, elle est respectée.'),
        ('ARTICLE 27 — PROROGATION', 'Lorsque la réglementation applicable permet au locataire sans nouveau logement de bénéficier d’une prorogation après préavis, celle-ci est traitée conformément aux conditions légales et administratives.'),
        ('ARTICLE 28 — RÉSILIATION', 'Le contrat prend fin à son terme, par accord écrit, par préavis légal, pour manquement grave ou dans les autres cas prévus par la loi. Toute résiliation pour faute suit les procédures applicables.'),
        ('ARTICLE 29 — MANQUEMENTS GRAVES', 'Constituent notamment des manquements graves : falsification de documents, impayés persistants, sous-sous-location clandestine, dommage majeur intentionnel, activité illégale, trouble grave ou répété du voisinage et refus répété d’obligations essentielles.'),
        ('ARTICLE 30 — DÉCÈS OU ABANDON', 'En cas de décès du locataire, les règles légales relatives à la continuation ou à la fin du contrat s’appliquent. En cas de suspicion d’abandon, FASTHOME agit avec prudence et conformément aux procédures légales avant toute récupération des biens.'),
    ]
    for heading, body in sections:
        c.setFont('Helvetica-Bold', 10.5); c.drawString(50, y, heading); y -= 16
        y = _draw_wrapped(c, body, 50, y, width - 100, 12.5, size=8.8); y -= 7
    c.showPage()

    # Page 5 — clauses/signatures fournies comme référence
    title('FIN DU CONTRAT, GARANTIE, LITIGES ET SIGNATURES', 5)
    y = height - 135
    sections = [
        ('ARTICLE 31 — DÉPART ET RESTITUTION', 'Le locataire libère les lieux, restitue les clés et équipements, règle les sommes légalement dues et participe à l’état des lieux de sortie. L’usure normale est prise en compte.'),
        ('ARTICLE 32 — ÉTAT DES LIEUX DE SORTIE', 'L’état des lieux de sortie est contradictoire. Sont notamment comparés : murs, sols, plafonds, portes, fenêtres, installations, sanitaires, équipements, compteurs et clés. L’usure normale n’est pas facturée.'),
        ('ARTICLE 33 — GARANTIE ET RETENUES', 'Après le départ, FASTHOME vérifie les loyers, charges, clés, équipements et dommages imputables. Toute retenue est justifiée. Le solde de la garantie est traité conformément au droit applicable.'),
        ('ARTICLE 34 — FIN DU CONTRAT PRINCIPAL', 'Le locataire reconnaît que FASTHOME ne peut conférer des droits supérieurs à ceux dont elle dispose légalement sur le bien. Si un événement affectant le contrat principal modifie matériellement l’occupation, FASTHOME informe le locataire et prend les mesures légales nécessaires.'),
        ('ARTICLE 35 — FORCE MAJEURE', 'Aucune partie n’est responsable d’un manquement directement causé par un cas de force majeure légalement reconnu, sous réserve d’informer l’autre partie et de limiter les dommages.'),
        ('ARTICLE 36 — NOTIFICATIONS', 'FASTHOME : téléphone __________________ ; adresse __________________ ; email __________________. LOCATAIRE : téléphone __________________ ; adresse __________________ ; email __________________. Les notifications importantes sont effectuées dans une forme permettant d’en rapporter la preuve.'),
        ('ARTICLE 37 — RÈGLEMENT DES LITIGES', 'Les parties recherchent d’abord une solution amiable. Si la réglementation impose une conciliation auprès du service compétent de l’Habitat, elle est respectée. À défaut, le litige relève de la juridiction compétente conformément au droit de la RDC.'),
        ('ARTICLE 38 — DÉCLARATION DU LOCATAIRE', 'Le locataire déclare avoir visité le logement, avoir reçu les informations essentielles, connaître son état, avoir lu et compris le présent contrat, avoir reçu ou pouvoir obtenir une copie, accepter les règles d’occupation et s’engager à respecter ses obligations.'),
    ]
    for heading, body in sections:
        c.setFont('Helvetica-Bold', 10.2); c.drawString(50, y, heading); y -= 15
        y = _draw_wrapped(c, body, 50, y, width - 100, 12, size=8.5); y -= 6

    y -= 3
    c.setFont('Helvetica-Bold', 10); c.drawString(50, y, f'Fait à __________________, le ____/____/________')
    y -= 22
    c.setFont('Helvetica-Bold', 9); c.drawString(50, y, 'LE LOCATAIRE'); c.drawString(310, y, 'FASTHOME')
    y -= 15; c.setFont('Helvetica', 8.5); c.drawString(50, y, f'Nom : {tenant_name}'); c.drawString(310, y, 'Représentant : __________________')
    y -= 13; c.drawString(50, y, 'Lu et approuvé : __________________'); c.drawString(310, y, 'Qualité : _________________________')
    y -= 13; c.drawString(50, y, 'Signature : ________________________'); c.drawString(310, y, 'Lu et approuvé : ___________________')
    y -= 13; c.drawString(310, y, 'Signature / cachet : ________________')
    y -= 20
    c.setFont('Helvetica-Bold', 8.5); c.drawString(50, y, 'PARAPHES')
    y -= 13; c.setFont('Helvetica', 8); c.drawString(50, y, 'Locataire — pages 1 à 5 :  1____  2____  3____  4____  5____')
    y -= 12; c.drawString(50, y, 'FASTHOME — pages 1 à 5 :   1____  2____  3____  4____  5____')
    y -= 20
    c.setFont('Helvetica-Bold', 8.5); c.drawString(50, y, 'ANNEXES')
    y -= 12; c.setFont('Helvetica', 8); c.drawString(50, y, '☐ État des lieux d’entrée    ☐ État des lieux de sortie    ☐ Photographies    ☐ Inventaire')
    y -= 12; c.drawString(50, y, '☐ Relevé des compteurs    ☐ Règlement intérieur    ☐ Copie pièce d’identité    ☐ Reçu de garantie')

    qr = qrcode.make(f'FASTHOME|{contract.reference}|{case.reference}|{prop.reference}')
    qbuf = BytesIO(); qr.save(qbuf, format='PNG'); qbuf.seek(0)
    c.drawImage(ImageReader(qbuf), width - 125, 48, width=70, height=70)
    c.setFont('Helvetica', 7); c.drawRightString(width - 45, 40, 'Vérification FASTHOME')
    c.showPage(); c.save(); buffer.seek(0)
    return buffer.getvalue()


@login_required
def rental_contract_pdf(request, pk):
    contract = get_object_or_404(RentalContract.objects.select_related('rental_case', 'property', 'party'), pk=pk)
    if not (request.user.is_staff or request.user.pk in {contract.rental_case.owner_id, contract.rental_case.tenant_id}):
        return HttpResponseForbidden('Accès refusé.')
    try:
        pdf = _contract_pdf(contract)
        return HttpResponse(pdf, content_type='application/pdf', headers={'Content-Disposition': f'inline; filename="{contract.reference}.pdf"'})
    except ImportError:
        messages.error(request, 'Le module PDF n’est pas installé sur cet environnement.')
        return redirect('rental_case_detail', pk=contract.rental_case_id)
