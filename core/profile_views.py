from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages

from .models import Contract, Notification, Property, VerificationDossier, Visit, Payment


@login_required
def profile(request):
    user = request.user

    if request.method == 'POST' and request.POST.get('action') == 'update_name':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        if not first_name or not last_name:
            messages.error(request, 'Veuillez renseigner votre prénom et votre nom.')
        else:
            user.first_name = first_name
            user.last_name = last_name
            user.save(update_fields=['first_name', 'last_name'])
            messages.success(request, 'Votre nom complet a été enregistré.')
            return redirect('profile')

    dossier = VerificationDossier.objects.filter(user=user).first()
    status = dossier.status if dossier else 'not_started'
    status_map = {
        'not_started': ('Identité non certifiée', 'Complétez votre vérification pour renforcer la confiance de votre compte.'),
        'pending': ('Dossier envoyé', 'Votre dossier complet est en attente de traitement par FASTHOME.'),
        'review': ('Vérification en cours', 'FASTHOME examine actuellement votre dossier d’identité.'),
        'approved': ('Identité certifiée', 'Votre dossier d’identité a été validé par FASTHOME.'),
        'rejected': ('Vérification refusée', 'Votre dossier doit être corrigé ou renvoyé.'),
        'needs_info': ('Informations requises', 'FASTHOME demande des informations ou documents supplémentaires.'),
    }
    verification_label, verification_message = status_map.get(status, status_map['not_started'])

    favorite_ids = request.session.get('favorites', [])
    stats = {
        'favorites': Property.objects.filter(pk__in=favorite_ids, status='published').count(),
        'properties': Property.objects.filter(owner=user).count(),
        'published': Property.objects.filter(owner=user, status='published').count(),
        'visits': Visit.objects.filter(requester=user).count(),
        'contracts': Contract.objects.filter(user=user).count(),
        'payments': Payment.objects.filter(contract__user=user).count(),
        'notifications': Notification.objects.filter(user=user, read=False).count(),
    }

    completion = 50 if user.email else 30
    if user.first_name:
        completion += 15
    if user.last_name:
        completion += 15
    if status == 'approved':
        completion += 20
    elif dossier:
        completion += 10
    completion = min(completion, 100)

    return render(request, 'profile.html', {
        'dossier': dossier,
        'documents': [],
        'latest_documents': {},
        'verification_status': status,
        'verification_label': verification_label,
        'verification_message': verification_message,
        'stats': stats,
        'profile_completion': completion,
        'has_email': bool(user.email),
        'has_name': bool(user.first_name and user.last_name),
    })
