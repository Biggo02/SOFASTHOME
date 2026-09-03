from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .models import VerificationDossier
from .views import audit


@login_required
def verification_upload(request):
    dossier, _ = VerificationDossier.objects.get_or_create(user=request.user)
    if request.method == 'POST':
        front = request.FILES.get('id_front')
        back = request.FILES.get('id_back')
        selfie = request.FILES.get('selfie')
        if not front or not back or not selfie:
            messages.error(request, 'Veuillez joindre le recto, le verso et le selfie avant l’envoi.')
            return render(request, 'verification_upload.html', {'dossier': dossier})
        dossier.id_front = front
        dossier.id_back = back
        dossier.selfie = selfie
        dossier.status = 'pending'
        dossier.note = ''
        dossier.save()
        audit(request, 'verification.dossier_submitted', dossier, {'files': ['id_front', 'id_back', 'selfie']})
        messages.success(request, 'Votre dossier complet de vérification a été envoyé à FASTHOME.')
        return redirect('profile')
    return render(request, 'verification_upload.html', {'dossier': dossier})
