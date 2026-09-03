from django.contrib import messages
from django.shortcuts import redirect

from .models import VerificationDossier


class VerifiedIdentityMiddleware:
    """Bloque publication/visite uniquement si le dossier FASTHOME n'est pas approuvé."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        needs_verification = (
            path == '/ajouter-un-bien/'
            or (path.startswith('/bien/') and path.endswith('/visite/'))
        )

        if (
            needs_verification
            and request.user.is_authenticated
            and not request.user.is_staff
        ):
            dossier = VerificationDossier.objects.filter(user=request.user).only('status').first()
            is_verified = bool(dossier and dossier.status == 'approved')

            if not is_verified:
                messages.warning(
                    request,
                    'Votre identité doit être validée par FASTHOME avant de publier un bien ou demander une visite.'
                )
                return redirect('verification_upload')

        return self.get_response(request)
