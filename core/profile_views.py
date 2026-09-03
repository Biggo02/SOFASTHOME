from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render, redirect
from django.contrib import messages

from .models import Contract, Notification, Payment, Property, VerificationDocument, Visit


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

    documents = list(VerificationDocument.objects.filter(user=user).order_by('-created_at'))

    latest = {}
    for document in documents:
        latest.setdefault(document.kind, document)

    required = ('id_front', 'id_back', 'selfie')
    approved = all(latest.get(kind) and latest[kind].status == 'approved' for kind in required)
    rejected = any(document.status == 'rejected' for document in documents)
    pending = any(document.status == 'pending' for document in documents)

    if approved:
        verification_status = 'verified'
        verification_label = 'Identité certifiée'
        verification_message = 'Votre identité a été validée par FASTHOME.'
    elif rejected:
        verification_status = 'rejected'
        verification_label = 'Vérification à reprendre'
        verification_message = 'Un ou plusieurs documents doivent être remplacés ou renvoyés.'
    elif pending or documents:
        verification_status = 'pending'
        verification_label = 'Vérification en cours'
        verification_message = 'FASTHOME examine actuellement vos documents.'
    else:
        verification_status = 'not_started'
        verification_label = 'Identité non certifiée'
        verification_message = 'Complétez votre vérification pour renforcer la confiance de votre compte.'

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
    if approved:
        completion += 20
    elif documents:
        completion += 10
    completion = min(completion, 100)

    return render(request, 'profile.html', {
        'documents': documents,
        'latest_documents': latest,
        'verification_status': verification_status,
        'verification_label': verification_label,
        'verification_message': verification_message,
        'stats': stats,
        'profile_completion': completion,
        'has_email': bool(user.email),
        'has_name': bool(user.first_name and user.last_name),
    })
