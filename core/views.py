from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import RegisterForm, PropertyForm
from .models import AuditLog, Contract, Notification, Payment, PaymentProof, Property, PropertyImage, VerificationDocument, VerificationDossier, Visit, VisitInspection


def audit(request, action, obj=None, details=None):
    AuditLog.objects.create(actor=request.user if request.user.is_authenticated else None, action=action, object_type=obj.__class__.__name__ if obj else '', object_id=str(getattr(obj, 'pk', '')), ip_address=request.META.get('REMOTE_ADDR'), details=details or {})


def is_identity_verified(user):
    if not user or not user.is_authenticated: return False
    return VerificationDossier.objects.filter(user=user, status='approved').exists()


def require_verified(request, action):
    if is_identity_verified(request.user): return True
    messages.warning(request, f'Votre identité doit être validée par FASTHOME avant {action}.'); return False


def match_score(prop, request):
    score = 0; q = request.GET.get('q', '').strip().lower(); ptype = request.GET.get('type', ''); bedroom_value = request.GET.get('bedrooms', '')
    if q:
        hay = f'{prop.title} {prop.province} {prop.city} {prop.commune}'.lower().replace('-', ' '); score += 25 if q.replace('-', ' ') in hay else 15 if any(part in hay for part in q.replace('-', ' ').split()) else 5
    else: score += 20
    score += 20 if not ptype or prop.property_type == ptype else 0
    try: requested_bedrooms = int(bedroom_value or 0)
    except (TypeError, ValueError): requested_bedrooms = 0
    score += 15 if prop.bedrooms >= requested_bedrooms else 5; score += 10 if prop.water else 0; score += 10 if prop.electricity else 0; score += 10 if prop.security else 0; score += 10 if prop.parking else 5
    return min(score, 100)


def home(request): return render(request, 'home.html', {'properties': Property.objects.filter(status='published').prefetch_related('images').order_by('-created_at')[:8], 'types': Property.TYPES})

def search(request):
    qs = Property.objects.filter(status='published').prefetch_related('images'); q = request.GET.get('q', '').strip(); ptype = request.GET.get('type', ''); bedrooms = request.GET.get('bedrooms', ''); commune = request.GET.get('commune', '').strip()
    if q:
        query = Q()
        for term in q.replace('-', ' ').split(): query |= Q(title__icontains=term) | Q(province__icontains=term) | Q(city__icontains=term) | Q(commune__icontains=term)
        qs = qs.filter(query)
    if ptype: qs = qs.filter(property_type=ptype)
    if bedrooms:
        try: qs = qs.filter(bedrooms__gte=int(bedrooms))
        except (TypeError, ValueError): pass
    if commune: qs = qs.filter(commune__icontains=commune)
    properties = list(qs)
    for prop in properties: prop.ui_score = match_score(prop, request)
    properties.sort(key=lambda p: p.ui_score, reverse=True); return render(request, 'search.html', {'properties': properties, 'q': q, 'types': Property.TYPES})

def property_detail(request, pk):
    prop = get_object_or_404(Property.objects.prefetch_related('images'), pk=pk, status='published'); prop.views += 1; prop.save(update_fields=['views']); context = {'property': prop, 'images': prop.images.all()}
    if request.GET.get('matching') == '1' or request.GET.get('from_matching') == '1': context['score'] = match_score(prop, request)
    return render(request, 'property_detail.html', context)

def register(request):
    if request.user.is_authenticated: return redirect('dashboard')
    form = RegisterForm(request.POST or None)
    if request.method == 'POST' and form.is_valid(): user = form.save(commit=False); user.set_password(form.cleaned_data['password']); user.save(); login(request, user); audit(request, 'account.created', user); messages.success(request, 'Bienvenue sur FASTHOME. Votre compte unique est prêt.'); return redirect('dashboard')
    return render(request, 'auth.html', {'form': form, 'mode': 'register'})

def login_view(request):
    if request.user.is_authenticated: return redirect('dashboard')
    if request.method == 'POST':
        identifier = request.POST.get('username', '').strip(); user_for_auth = User.objects.filter(Q(username__iexact=identifier) | Q(email__iexact=identifier)).first(); user = authenticate(request, username=user_for_auth.username if user_for_auth else identifier, password=request.POST.get('password', ''))
        if user: login(request, user); audit(request, 'account.login', user); return redirect('dashboard')
        messages.error(request, 'Email, téléphone ou mot de passe incorrect.')
    return render(request, 'auth.html', {'mode': 'login'})

def logout_view(request): logout(request); return redirect('home')
def _links(): return [('⌂', 'Tableau de bord', 'dashboard'), ('⌕', 'Rechercher', 'search'), ('♡', 'Mes favoris', 'favorites'), ('▣', 'Mes publications', 'publications'), ('◷', 'Mes demandes de visite', 'visits'), ('▤', 'Mes contrats', 'contracts'), ('◉', 'Mes paiements', 'payments'), ('◴', 'Mes échéances', 'due_dates'), ('●', 'Messages', 'messages'), ('♢', 'Notifications', 'notifications'), ('⚙', 'Mon profil', 'profile')]

@login_required
def dashboard(request):
    user = request.user; return render(request, 'dashboard.html', {'links': _links(), 'properties': Property.objects.filter(owner=user).order_by('-updated_at'), 'visits': Visit.objects.filter(requester=user).select_related('property').order_by('-created_at')[:5], 'contracts': Contract.objects.filter(user=user).select_related('property'), 'payments': Payment.objects.filter(contract__user=user).select_related('contract__property').order_by('due_date')[:5], 'notifications': Notification.objects.filter(user=user).order_by('-created_at')[:6]})

@login_required
def publications(request): return render(request, 'list.html', {'title': 'Mes publications', 'items': Property.objects.filter(owner=request.user).order_by('-updated_at'), 'kind': 'property'})
@login_required
def add_property(request):
    form = PropertyForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        submitting = 'submit' in request.POST
        if submitting and not require_verified(request, 'soumettre une publication'): return render(request, 'property_form.html', {'form': form})
        obj = form.save(commit=False); obj.owner = request.user; obj.status = 'review' if submitting else 'draft'; obj.save(); audit(request, 'property.created', obj, {'status': obj.status})
        if obj.status == 'review': Notification.objects.create(user=request.user, title='Publication en vérification', message=f'{obj.reference} a été transmise à FASTHOME.')
        messages.success(request, 'Publication soumise à vérification.' if obj.status == 'review' else 'Brouillon enregistré.'); return redirect('publications')
    return render(request, 'property_form.html', {'form': form})

@login_required
def upload_property_images(request, pk):
    prop = get_object_or_404(Property, pk=pk, owner=request.user)
    if request.method != 'POST': return redirect('publications')
    files = request.FILES.getlist('images'); existing = prop.images.count()
    if existing + len(files) > 10: messages.error(request, 'Un bien peut contenir au maximum 10 photos.'); return redirect('publications')
    for i, uploaded in enumerate(files): PropertyImage.objects.create(property=prop, image=uploaded, order=existing + i, is_cover=(existing == 0 and i == 0))
    audit(request, 'property.images_uploaded', prop, {'count': len(files)}); messages.success(request, f'{len(files)} photo(s) ajoutée(s).'); return redirect('publications')

@login_required
def request_visit(request, pk):
    prop = get_object_or_404(Property, pk=pk, status='published')
    if request.method == 'POST':
        if not require_verified(request, 'demander une visite'): return redirect('property_detail', pk=prop.pk)
        visit = Visit.objects.create(property=prop, requester=request.user, preferred_date=request.POST.get('preferred_date') or None, preferred_time=request.POST.get('preferred_time') or None, comment=request.POST.get('comment', ''))
        Notification.objects.create(user=request.user, title='Demande de visite envoyée', message=f'Votre demande pour {prop.title} est en attente de validation.')
        Notification.objects.create(user=prop.owner, title='Nouvelle demande de visite', message=f'La demande #{visit.pk} concerne votre bien {prop.reference}.')
        audit(request, 'visit.requested', visit); messages.success(request, 'Votre demande de visite a été envoyée.'); return redirect('visits')
    return render(request, 'visit_form.html', {'property': prop})

@login_required
def visits(request): return render(request, 'list.html', {'title': 'Mes demandes de visite', 'items': Visit.objects.filter(requester=request.user).select_related('property').order_by('-created_at'), 'kind': 'visit'})
@login_required
def contracts(request): return render(request, 'list.html', {'title': 'Mes contrats', 'items': Contract.objects.filter(user=request.user).select_related('property').order_by('-created_at'), 'kind': 'contract'})
@login_required
def payments(request): return render(request, 'list.html', {'title': 'Mes paiements', 'items': Payment.objects.filter(contract__user=request.user).select_related('contract__property').order_by('due_date'), 'kind': 'payment'})
@login_required
def due_dates(request): return render(request, 'list.html', {'title': 'Mes échéances', 'items': Payment.objects.filter(contract__user=request.user).select_related('contract__property').order_by('due_date'), 'kind': 'due'})
@login_required
def payment_proof(request, pk):
    payment = get_object_or_404(Payment, pk=pk, contract__user=request.user)
    if request.method == 'POST' and request.FILES.get('file'):
        proof = PaymentProof.objects.create(payment=payment, file=request.FILES['file'], note=request.POST.get('note', ''), uploaded_by=request.user); audit(request, 'payment.proof_uploaded', payment, {'proof_id': proof.pk}); messages.success(request, 'Preuve de paiement envoyée à FASTHOME.'); return redirect('payments')
    return render(request, 'payment_proof.html', {'payment': payment})
@login_required
def notifications(request):
    qs = Notification.objects.filter(user=request.user).order_by('-created_at'); qs.filter(read=False).update(read=True); return render(request, 'list.html', {'title': 'Notifications', 'items': qs, 'kind': 'notification'})
@login_required
def favorites(request): return render(request, 'list.html', {'title': 'Mes favoris', 'items': Property.objects.filter(pk__in=request.session.get('favorites', []), status='published'), 'kind': 'favorite'})
@login_required
def toggle_favorite(request, pk):
    get_object_or_404(Property, pk=pk, status='published'); ids = request.session.get('favorites', [])
    if pk in ids: ids.remove(pk); messages.info(request, 'Bien retiré des favoris.')
    else: ids.append(pk); messages.success(request, 'Bien ajouté aux favoris.')
    request.session['favorites'] = ids; return HttpResponseRedirect(request.META.get('HTTP_REFERER') or redirect('property_detail', pk=pk).url)
@login_required
def messages_page(request): return render(request, 'placeholder.html', {'title': 'Messagerie sécurisée', 'text': 'Contactez uniquement FASTHOME. Les coordonnées privées des propriétaires restent masquées.'})
@login_required
def profile(request): return render(request, 'profile.html', {'documents': VerificationDocument.objects.filter(user=request.user).order_by('-created_at')})
def about(request): return render(request, 'placeholder.html', {'title': 'À propos', 'text': 'FASTHOME simplifie la recherche, la visite et la gestion locative en RDC.'})
def how_it_works(request): return render(request, 'placeholder.html', {'title': 'Comment ça marche ?', 'text': 'Recherchez, comparez, demandez une visite, recevez la confirmation, visitez, puis suivez votre location depuis un seul compte.'})
def contact(request): return render(request, 'placeholder.html', {'title': 'Contact', 'text': 'L’équipe FASTHOME vous accompagne à chaque étape.'})
def contract_verify(request, reference): return render(request, 'verify.html', {'contract': get_object_or_404(Contract, reference=reference)})

@login_required
def verification_upload(request):
    if request.method == 'POST':
        for kind in ('id_front', 'id_back', 'selfie'):
            uploaded = request.FILES.get(kind)
            if uploaded: VerificationDocument.objects.create(user=request.user, kind=kind, file=uploaded); audit(request, 'verification.document_uploaded', details={'kind': kind})
        messages.success(request, 'Vos documents de vérification ont été envoyés à FASTHOME.'); return redirect('profile')
    return render(request, 'verification_upload.html')

def staff_required(user): return user.is_staff

@login_required
@user_passes_test(staff_required)
def admin_dashboard(request):
    today = timezone.localdate(); pending_visits = Visit.objects.filter(status='pending').select_related('property', 'requester', 'agent').order_by('preferred_date', 'preferred_time')[:10]; confirmed_visits = Visit.objects.filter(status='confirmed').select_related('property', 'requester', 'agent').order_by('scheduled_date', 'scheduled_time', '-created_at')[:15]; today_confirmed = Visit.objects.filter(status='confirmed', scheduled_date=today).select_related('property', 'requester').order_by('scheduled_time')
    return render(request, 'admin_dashboard.html', {'users': User.objects.count(), 'properties': Property.objects.count(), 'review': Property.objects.filter(status='review').count(), 'published': Property.objects.filter(status='published').count(), 'visits': Visit.objects.count(), 'today_visits': Visit.objects.filter(preferred_date=today).count(), 'today_confirmed_count': today_confirmed.count(), 'contracts': Contract.objects.count(), 'late': Payment.objects.filter(status='late').count(), 'payments': Payment.objects.count(), 'properties_review': Property.objects.filter(status='review').order_by('-created_at')[:10], 'visits_pending': pending_visits, 'visits_confirmed': confirmed_visits, 'visits_today_confirmed': today_confirmed[:10], 'audit_logs': AuditLog.objects.select_related('actor')[:12]})

@login_required
@user_passes_test(staff_required)
def review_publication(request, pk):
    prop = get_object_or_404(Property, pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action'); allowed = {'review': {'publish', 'reject'}, 'published': set(), 'rented': {'archive'}, 'archived': set(), 'rejected': set()}; current = prop.status
        if action not in allowed.get(current, set()): messages.error(request, f'Action impossible pour le statut « {prop.get_status_display()} ».'); return redirect('review_publication', pk=prop.pk)
        if action == 'publish': prop.status = 'published'; prop.rejection_reason = ''; notice = 'Publication mise en ligne. Le bien peut maintenant recevoir des demandes de visite.'
        elif action == 'reject':
            reason = request.POST.get('rejection_reason', '').strip()
            if not reason: messages.error(request, 'Le motif de refus est obligatoire.'); return render(request, 'review_publication.html', {'property': prop})
            prop.status = 'rejected'; prop.rejection_reason = reason; notice = 'Publication refusée. Le propriétaire doit la corriger puis la soumettre à nouveau.'
        else: prop.status = 'archived'; notice = 'Bien archivé. Il n’est plus proposé publiquement.'
        prop.save(update_fields=['status', 'rejection_reason', 'updated_at']); audit(request, 'property.workflow_transition', prop, {'from': current, 'to': prop.status}); Notification.objects.create(user=prop.owner, title='Statut de publication mis à jour', message=f'{prop.reference} : {prop.get_status_display()}.'); messages.success(request, notice); return redirect('admin_dashboard')
    return render(request, 'review_publication.html', {'property': prop})

@login_required
@user_passes_test(staff_required)
def manage_visit(request, pk):
    visit = get_object_or_404(Visit, pk=pk)
    return render(request, 'manage_visit.html', {'visit': visit})

@login_required
@user_passes_test(staff_required)
def verification_review(request, pk):
    doc = get_object_or_404(VerificationDocument, pk=pk)
    if request.method == 'POST':
        doc.status = request.POST.get('status', 'pending'); doc.note = request.POST.get('note', ''); doc.save(update_fields=['status', 'note']); audit(request, 'verification.reviewed', doc, {'status': doc.status}); Notification.objects.create(user=doc.user, title='Vérification mise à jour', message=f'Votre document {doc.get_kind_display()} est : {doc.status}.'); messages.success(request, 'Document mis à jour.'); return redirect('admin_dashboard')
    return render(request, 'verification_upload.html', {'document': doc})

@login_required
@user_passes_test(staff_required)
def inspection(request, pk):
    visit = get_object_or_404(Visit.objects.select_related('property', 'requester'), pk=pk); inspection_obj, _ = VisitInspection.objects.get_or_create(visit=visit)
    if request.method == 'POST':
        inspection_obj.condition = request.POST.get('condition', '').strip(); inspection_obj.meter_readings = request.POST.get('meter_readings', '').strip()
        try: inspection_obj.keys_received = max(0, int(request.POST.get('keys_received') or 0))
        except (TypeError, ValueError): inspection_obj.keys_received = 0
        inspection_obj.notes = request.POST.get('notes', '').strip(); inspection_obj.signed_by_tenant = request.POST.get('signed_by_tenant') == 'on'; inspection_obj.signed_by_agent = request.POST.get('signed_by_agent') == 'on'; inspection_obj.save(); audit(request, 'visit.inspection_updated', inspection_obj, {'visit_id': visit.pk}); messages.success(request, 'État des lieux enregistré.'); return redirect('manage_visit', pk=visit.pk)
    return render(request, 'inspection.html', {'visit': visit, 'inspection': inspection_obj})

def error_403(request, exception=None): return render(request, '403.html', status=403)
def error_404(request, exception=None): return render(request, '404.html', status=404)
def error_500(request): return render(request, '500.html', status=500)