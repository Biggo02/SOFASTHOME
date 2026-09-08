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
    template = 'property_form_clean.html'

    if request.method == 'POST':
        submitting = 'submit' in request.POST

        if form.is_valid():
            if submitting:
                if not require_verified(request, 'soumettre une publication'):
                    # Never discard a user's completed form when identity verification is missing.
                    messages.warning(
                        request,
                        'Votre publication n’a pas été perdue. Validez d’abord votre identité, puis revenez ici pour la soumettre à FASTHOME.'
                    )
                    return render(request, template, {'form': form, 'submission_blocked': 'verification'})

                if not form.cleaned_data.get('owner_authorized_publication'):
                    form.add_error(
                        'owner_authorized_publication',
                        'Cette autorisation est obligatoire pour soumettre le bien.'
                    )
                if not form.cleaned_data.get('owner_authorized_subletting'):
                    form.add_error(
                        'owner_authorized_subletting',
                        'Vous devez autoriser FASTHOME à exploiter le bien en sous-location.'
                    )
                if form.errors:
                    messages.error(
                        request,
                        'La publication n’a pas été envoyée. Corrigez les champs signalés puis cliquez de nouveau sur « Soumettre à FASTHOME ». '
                    )
                    return render(request, template, {'form': form, 'submission_blocked': 'form'})

            obj = form.save(commit=False)
            obj.owner = request.user
            obj.title = f"{obj.get_property_type_display()} — {obj.city or obj.province or 'Bien'}"
            obj.status = 'review' if submitting else 'draft'
            if submitting:
                obj.authorization_confirmed_at = timezone.now()
            obj.save()

            for index, uploaded in enumerate(form.cleaned_data.get('photos') or []):
                PropertyImage.objects.create(
                    property=obj,
                    image=uploaded,
                    order=index,
                    is_cover=index == 0,
                )

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
                messages.success(
                    request,
                    f'{obj.reference} a bien été transmis à FASTHOME et apparaît maintenant dans « En vérification ». '
                )
            else:
                messages.success(request, 'Brouillon enregistré.')

            return redirect('publications')

        # Important: Django can reject the complete 9-step form even though the
        # browser-side step validation passed. Make the failure explicit instead
        # of silently returning the user to the same page.
        if submitting:
            messages.error(
                request,
                'La publication n’a pas été enregistrée. Certains champs obligatoires ou conditionnels sont invalides. Consultez les erreurs affichées dans le formulaire.'
            )
        else:
            messages.warning(request, 'Le brouillon n’a pas pu être enregistré. Vérifiez les champs signalés.')

    return render(request, template, {'form': form})
