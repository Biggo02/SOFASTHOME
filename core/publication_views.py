from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone

from .forms import PropertyForm
from .models import Notification, PropertyImage
from .views import audit, require_verified


@login_required
def add_property(request):
    form = PropertyForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        submitting = 'submit' in request.POST
        if submitting:
            if not require_verified(request, 'soumettre une publication'):
                return render(request, 'property_form_v2.html', {'form': form})
            if not form.cleaned_data.get('owner_authorized_publication'):
                form.add_error('owner_authorized_publication', 'Cette autorisation est obligatoire pour soumettre le bien.')
            if not form.cleaned_data.get('owner_authorized_subletting'):
                form.add_error('owner_authorized_subletting', 'Vous devez autoriser FASTHOME à exploiter le bien en sous-location.')
            if form.errors:
                return render(request, 'property_form_v2.html', {'form': form})

        obj = form.save(commit=False)
        obj.owner = request.user
        obj.title = f"{obj.get_property_type_display()} — {obj.city or obj.province or 'Bien'}"
        obj.status = 'review' if submitting else 'draft'
        if submitting:
            obj.authorization_confirmed_at = timezone.now()
        obj.save()

        files = form.cleaned_data.get('photos') or []
        for index, uploaded in enumerate(files):
            PropertyImage.objects.create(property=obj, image=uploaded, order=index, is_cover=(index == 0))

        audit(request, 'property.created', obj, {
            'status': obj.status,
            'photos': len(files),
            'publication_authorized': obj.owner_authorized_publication,
            'subletting_authorized': obj.owner_authorized_subletting,
        })
        if obj.status == 'review':
            Notification.objects.create(user=request.user, title='Publication en vérification', message=f'{obj.reference} a été transmise à FASTHOME avec les autorisations requises.')
        messages.success(request, 'Publication soumise à vérification.' if obj.status == 'review' else 'Brouillon enregistré.')
        return redirect('publications')
    return render(request, 'property_form_v2.html', {'form': form})
