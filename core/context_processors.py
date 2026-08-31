from .models import Notification, VerificationDocument

def user_ui(request):
    if not request.user.is_authenticated:
        return {'unread_notifications_count': 0, 'profile_selfie': None}
    selfie = VerificationDocument.objects.filter(user=request.user, kind='selfie', status='approved').order_by('-created_at').first()
    return {
        'unread_notifications_count': Notification.objects.filter(user=request.user, read=False).count(),
        'profile_selfie': selfie.file.url if selfie and selfie.file else None,
    }
