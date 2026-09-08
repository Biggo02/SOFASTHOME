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
    if request.method == 'POST' and form.is_valid():
        user = form.save(commit=False); user.set_password(form.cleaned_data['password']); user.save()
        profile_data = getattr(user, '_registration_profile_data', None)
        if profile_data is not None:
            from .models import UserProfile
            UserProfile.objects.update_or_create(user=user, defaults=profile_data)
        login(request, user); audit(request, 'account.created', user); messages.success(request, 'Bienvenue sur FASTHOME. Votre compte unique est prêt.'); return redirect('dashboard')
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
    user = request.user
    owner_properties = Property.objects.filter(owner=user).prefetch_related('images').order_by('-updated_at')
    draft_properties = owner_properties.filter(status__in=['draft', 'rejected'])
    review_properties = owner_properties.filter(status='review')
    available_properties = owner_properties.filter(status='published')
    rented_properties = owner_properties.filter(status='rented')
    return render(request, 'dashboard.html', {
        'links': _links(),
        'properties': owner_properties,
        'draft_properties': draft_properties,
        'review_properties': review_properties,
        'available_properties': available_properties,
        'rented_properties': rented_properties,
        'property_counts': {
            'draft': draft_properties.count(),
            'review': review_properties.count(),
            'available': available_properties.count(),
            'rented': rented_properties.count(),
        },
        'visits': Visit.objects.filter(requester=user).select_related('property').order_by('-created_at')[:5],
        'contracts': Contract.objects.filter(user=user).select_related('property'),
        'payments': Payment.objects.filter(contract__user=user).select_related('contract__property').order_by('due_date')[:5],
        'notifications': Notification.objects.filter(user=user).order_by('-created_at')[:6],
    })

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
    for index, uploaded in enumerate(files): PropertyImage.objects.create(property=prop, image=uploaded, order=existing + index, is_cover=(existing + index == 0))
    messages.success(request, 'Photos ajoutées.'); return redirect('publications')

@login_required
def favorites(request): return render(request, 'list.html', {'title': 'Mes favoris', 'items': [], 'kind': 'favorite'})
@login_required
def visits(request): return render(request, 'list.html', {'title': 'Mes demandes de visite', 'items': Visit.objects.filter(requester=request.user).select_related('property').order_by('-created_at'), 'kind': 'visit'})
@login_required
def contracts(request): return render(request, 'list.html', {'title': 'Mes contrats', 'items': Contract.objects.filter(user=request.user).select_related('property').order_by('-created_at'), 'kind': 'contract'})
@login_required
def payments(request): return render(request, 'list.html', {'title': 'Mes paiements', 'items': Payment.objects.filter(contract__user=request.user).select_related('contract__property').order_by('-due_date'), 'kind': 'payment'})
@login_required
def due_dates(request): return render(request, 'list.html', {'title': 'Mes échéances', 'items': Payment.objects.filter(contract__user=request.user).select_related('contract__property').order_by('due_date'), 'kind': 'due'})
@login_required
def notifications(request): return render(request, 'list.html', {'title': 'Mes notifications', 'items': Notification.objects.filter(user=request.user).order_by('-created_at'), 'kind': 'notification'})
@login_required
def profile(request): return render(request, 'placeholder.html', {'title': 'Mon profil'})
@login_required
def messages_view(request): return render(request, 'placeholder.html', {'title': 'Messagerie sécurisée'})
@login_required
def about(request): return render(request, 'placeholder.html', {'title': 'À propos'})
def how_it_works(request): return render(request, 'placeholder.html', {'title': 'Comment ça marche ?'})
def contact(request): return render(request, 'placeholder.html', {'title': 'Contact'})

@login_required
@user_passes_test(lambda u: u.is_staff)
def admin_dashboard(request): return render(request, 'admin_dashboard.html', {'users_count': User.objects.count(), 'properties_count': Property.objects.count(), 'published_count': Property.objects.filter(status='published').count(), 'visits_count': Visit.objects.count(), 'contracts_count': Contract.objects.count()})

@login_required
@user_passes_test(lambda u: u.is_staff)
def verify_document(request, pk):
    doc = get_object_or_404(VerificationDocument, pk=pk)
    if request.method == 'POST': doc.status = request.POST.get('status', 'pending'); doc.note = request.POST.get('note', '').strip(); doc.save(update_fields=['status','note']); messages.success(request, 'Document mis à jour.'); return redirect('admin_dashboard')
    return render(request, 'verify_document.html', {'doc': doc})

@login_required
@user_passes_test(lambda u: u.is_staff)
def verification_detail(request, pk):
    dossier = get_object_or_404(VerificationDossier.objects.select_related('user'), pk=pk)
    if request.method == 'POST': dossier.status = request.POST.get('status', dossier.status); dossier.note = request.POST.get('note', dossier.note); dossier.save(); messages.success(request, 'Dossier de vérification mis à jour.'); return redirect('admin_dashboard')
    return render(request, 'verification_detail.html', {'dossier': dossier})
