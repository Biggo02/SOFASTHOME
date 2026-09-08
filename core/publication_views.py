from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone
from .forms import PropertyForm
from .models import Notification, Property, PropertyImage
from .views import audit, require_verified


def _save_partial_draft(request, form):
    """Conserve les données déjà saisies même si la soumission finale est invalide."""
    data = form.cleaned_data
    obj = Property(
        owner=request.user,
        property_type=data.get('property_type') or form.data.get('property_type') or 'Autre',
        title=data.get('title') or form.data.get('title') or 'Publication inachevée',
        status='draft',
    )

    # Reprendre uniquement les valeurs valides déjà nettoyées par le formulaire.
    model_fields = {
        field.name for field in Property._meta.fields
        if field.name not in {'id', 'reference', 'owner', 'title', 'property_type', 'status', 'created_at', 'updated_at'}
    }
    for name, value in data.items():
        if name in model_fields and value not in (None, ''):
            try:
                setattr(obj, name, value)
            except (TypeError, ValueError):
                pass

    # Une publication inachevée ne doit jamais être considérée comme soumise.
    obj.status = 'draft'
    obj.owner = request.user
    obj.save()

    for index, uploaded in enumerate(form.cleaned_data.get('photos') or []):
        PropertyImage.objects.create(
            property=obj,
            image=uploaded,
            order=index,
            is_cover=index == 0,
        )

    audit(request, 'property.draft_saved_after_invalid_submission', obj, {
        'status': 'draft',
        'form_errors': list(form.errors.keys()),
        'photos': len(form.cleaned_data.get('photos') or []),
    })
    return obj


@login_required
def add_property(request):
    form = PropertyForm(request.POST or None, request.FILES or None)
    template = 'property_form_clean.html'

    if request.method == 'POST':
        submitting = 'submit' in request.POST

        if form.is_valid():
            if submitting:
                if not require_verified(request, 'soumettre une publication'):
                    messages.warning(
                        request,
                        'Votre publication n’a pas été perdue. Elle est conservée dans « Brouillons ». Validez votre identité, puis reprenez-la pour la soumettre.'
                    )
                    # Le formulaire est valide : on peut conserver exactement ce qui a été saisi.
                    obj = form.save(commit=False)
                    obj.owner = request.user
                    obj.title = obj.title or f"{obj.get_property_type_display()} — {obj.city or obj.province or 'Bien'}"
                    obj.status = 'draft'
                    obj.save()
                    for index, uploaded in enumerate(form.cleaned_data.get('photos') or []):
                        PropertyImage.objects.create(property=obj, image=uploaded, order=index, is_cover=index == 0)
                    audit(request, 'property.draft_saved_verification_required', obj, {'status': 'draft'})
                    return redirect('publications')

                if not form.cleaned_data.get('owner_authorized_publication'):
                    form.add_error('owner_authorized_publication', 'Cette autorisation est obligatoire pour soumettre le bien.')
                if not form.cleaned_data.get('owner_authorized_subletting'):
                    form.add_error('owner_authorized_subletting', 'Vous devez autoriser FASTHOME à exploiter le bien en sous-location.')
                if form.errors:
                    obj = _save_partial_draft(request, form)
                    messages.error(
                        request,
                        f'La publication n’a pas été soumise. Elle a été conservée dans « Brouillons » ({obj.reference}). Corrigez les erreurs puis soumettez-la à nouveau.'
                    )
                    return redirect('publications')

            obj = form.save(commit=False)
            obj.owner = request.user
            obj.title = obj.title or f"{obj.get_property_type_display()} — {obj.city or obj.province or 'Bien'}"
            obj.status = 'review' if submitting else 'draft'
            if submitting:
                obj.authorization_confirmed_at = timezone.now()
            obj.save()

            for index, uploaded in enumerate(form.cleaned_data.get('photos') or []):
                PropertyImage.objects.create(property=obj, image=uploaded, order=index, is_cover=index == 0)

            audit(request, 'property.created', obj, {
                'status': obj.status,
                'photos': len(form.cleaned_data.get('photos') or []),
                'publication_authorized': obj.owner_authorized_publication,
                'subletting_authorized': obj.owner_authorized_subletting,
            })

            if obj.status == 'review':
                Notification.objects.create(
                    user=request.user,
                    title='Publication en vérification',
                    message=f'{obj.reference} a été transmise à FASTHOME avec les autorisations requises.'
                )
                messages.success(request, f'{obj.reference} a bien été transmis à FASTHOME et apparaît maintenant dans « En vérification ».')
            else:
                messages.success(request, 'Brouillon enregistré.')

            return redirect('publications')

        # Une soumission invalide est conservée comme brouillon au lieu de disparaître.
        if submitting:
            obj = _save_partial_draft(request, form)
            messages.error(
                request,
                f'La publication n’a pas été soumise. Elle a été conservée dans « Brouillons » ({obj.reference}). Corrigez les erreurs puis reprenez-la.'
            )
            return redirect('publications')

        messages.warning(request, 'Le brouillon n’a pas pu être enregistré. Vérifiez les champs signalés.')

    return render(request, template, {'form': form})
