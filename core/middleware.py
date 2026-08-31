from django.contrib import messages
from django.shortcuts import redirect
from .models import VerificationDocument

class VerifiedIdentityMiddleware:
    """Only users with an approved ID front, ID back and selfie may publish or request visits."""
    PROTECTED_PREFIXES=('/mes-publications/ajouter/', '/bien/')

    def __init__(self,get_response): self.get_response=get_response

    def __call__(self,request):
        path=request.path
        needs_verification=path.startswith('/mes-publications/ajouter/') or path.startswith('/bien/') and path.endswith('/visite/')
        if needs_verification and request.user.is_authenticated and not request.user.is_staff:
            kinds=set(VerificationDocument.objects.filter(user=request.user,status='approved').values_list('kind',flat=True))
            if not {'id_front','id_back','selfie'}.issubset(kinds):
                messages.warning(request,'Votre identité doit être vérifiée (pièce recto, verso et selfie) avant de publier un bien ou de demander une visite.')
                return redirect('verification_upload')
        return self.get_response(request)
