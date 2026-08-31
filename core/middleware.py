from django.contrib import messages
from django.shortcuts import redirect
from .models import VerificationDocument

class VerifiedIdentityMiddleware:
    """Require approved ID front, ID back and selfie before publication or visit requests."""
    def __init__(self,get_response): self.get_response=get_response
    def __call__(self,request):
        path=request.path
        needs_verification=(path == '/ajouter-un-bien/' or (path.startswith('/bien/') and path.endswith('/visite/')))
        if needs_verification and request.user.is_authenticated and not request.user.is_staff:
            kinds=set(VerificationDocument.objects.filter(user=request.user,status='approved').values_list('kind',flat=True))
            if not {'id_front','id_back','selfie'}.issubset(kinds):
                messages.warning(request,'Identité non vérifiée. Déposez le recto, le verso et le selfie avant de publier ou demander une visite.')
                return redirect('verification_upload')
        return self.get_response(request)
