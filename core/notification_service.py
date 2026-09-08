from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta

from .models import Notification


def notify(user, title, message):
    if not user or not getattr(user, 'is_authenticated', True):
        return None
    return Notification.objects.create(user=user, title=title[:180], message=message)


def notify_once(user, title, message, seconds=5):
    if not user or not getattr(user, 'is_authenticated', True):
        return None
    since = timezone.now() - timedelta(seconds=seconds)
    if Notification.objects.filter(user=user, title=title[:180], message=message, created_at__gte=since).exists():
        return None
    return notify(user, title, message)


def notify_staff(title, message):
    for staff in User.objects.filter(is_staff=True, is_active=True):
        notify_once(staff, title, message)


def notify_staff_once(title, message):
    for staff in User.objects.filter(is_staff=True, is_active=True):
        notify_once(staff, title, message)
