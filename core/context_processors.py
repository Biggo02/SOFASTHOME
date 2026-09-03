from .models import Notification, VerificationDossier


def user_ui(request):
    if not request.user.is_authenticated:
        return {'unread_notifications_count': 0, 'profile_selfie': None}

    dossier = VerificationDossier.objects.filter(user=request.user, status='approved').only('selfie').first()
    selfie = dossier.selfie.url if dossier and dossier.selfie else None

    return {
        'unread_notifications_count': Notification.objects.filter(user=request.user, read=False).count(),
        'profile_selfie': selfie,
    }
