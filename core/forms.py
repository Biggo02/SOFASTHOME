import json

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm
from .models import Property, UserProfile


class RegisterForm(forms.ModelForm):
    postnom = forms.CharField(label='Postnom', max_length=100, required=False)
    profession = forms.ChoiceField(label='Profession', choices=[('', 'Sélectionnez votre profession')] + UserProfile.PROFESSIONS, required=True)
    date_of_birth = forms.DateField(label='Date de naissance', required=True, widget=forms.DateInput(attrs={'type': 'date', 'autocomplete': 'bday'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}), label='Mot de passe')
    password2 = forms.CharField(widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}), label='Confirmation du mot de passe')

    class Meta:
        model = User
        fields = ['last_name', 'postnom', 'first_name', 'username', 'email', 'password']
        labels = {'last_name': 'Nom', 'first_name': 'Prénom', 'username': 'Téléphone', 'email': 'Email'}
        widgets = {'last_name': forms.TextInput(attrs={'placeholder': 'Votre nom'}), 'first_name': forms.TextInput(attrs={'placeholder': 'Votre prénom'}), 'username': forms.TextInput(attrs={'placeholder': 'Ex. 0812345678', 'autocomplete': 'tel'}), 'email': forms.EmailInput(attrs={'placeholder': 'exemple@email.com', 'autocomplete': 'email'})}

    def clean(self):
        data = super().clean()
        if data.get('password') != data.get('password2'):
            self.add_error('password2', 'Les mots de passe ne correspondent pas.')
        return data

    def save(self, commit=True):
        user = super().save(commit=commit)
        profile_data = {'postnom': self.cleaned_data.get('postnom', '').strip(), 'profession': self.cleaned_data.get('profession', ''), 'date_of_birth': self.cleaned_data.get('date_of_birth')}
        if commit:
            UserProfile.objects.update_or_create(user=user, defaults=profile_data)
        else:
            user._registration_profile_data = profile_data
        return user


class PropertyForm(forms.ModelForm):
    room_details_json = forms.CharField(required=False, widget=forms.HiddenInput())
    photos = forms.FileField(required=False, widget=forms.ClearableFileInput(attrs={'accept': 'image/*', 'capture': 'environment'}))
    owner_authorized_publication = forms.BooleanField(required=False, label='Je suis autorisé à publier ce bien.')
    owner_authorized_subletting = forms.BooleanField(required=False, label='J’autorise FASTHOME à utiliser ce bien dans le cadre de son activité de sous-location.')
    title = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = Property
        exclude = ['owner', 'reference', 'status', 'views', 'created_at', 'updated_at', 'margin', 'room_details']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Décrivez simplement le bien et ses particularités…'}),
            'province': forms.TextInput(attrs={'placeholder': 'Ex. Haut-Katanga'}),
            'city': forms.TextInput(attrs={'placeholder': 'Ex. Lubumbashi'}),
            'commune': forms.TextInput(attrs={'placeholder': 'Ex. Lubumbashi'}),
            'neighborhood': forms.TextInput(attrs={'placeholder': 'Ex. Golf'}),
            'avenue': forms.TextInput(attrs={'placeholder': 'Ex. Avenue des Écoles'}),
            'number': forms.TextInput(attrs={'placeholder': 'Ex. 12A'}),
            'geolocation_link': forms.URLInput(attrs={'placeholder': 'Collez le lien Google Maps ici'}),
            'availability_date': forms.DateInput(attrs={'type': 'date'}),
            'water_days_per_week': forms.NumberInput(attrs={'min': 0, 'max': 7}),
            'electricity_days_per_week': forms.NumberInput(attrs={'min': 0, 'max': 7}),
            'max_occupants': forms.NumberInput(attrs={'min': 1, 'max': 100}),
            'bedrooms': forms.NumberInput(attrs={'min': 0}),
            'salons': forms.NumberInput(attrs={'min': 0}),
            'kitchens': forms.NumberInput(attrs={'min': 0}),
            'bathrooms': forms.NumberInput(attrs={'min': 0}),
            'toilets': forms.NumberInput(attrs={'min': 0}),
            'shower_count': forms.NumberInput(attrs={'min': 0}),
            'rent': forms.NumberInput(attrs={'min': 1, 'step': '1', 'placeholder': 'Ex. 500000'}),
            'deposit': forms.NumberInput(attrs={'min': 0, 'step': '1', 'placeholder': 'Ex. 1500000'}),
        }
        labels = {
            'property_type': 'Type de bien', 'description': 'Description', 'province': 'Province', 'city': 'Ville', 'commune': 'Commune', 'neighborhood': 'Quartier', 'avenue': 'Avenue / rue / boulevard', 'number': 'Numéro', 'geolocation_link': 'Lien de géolocalisation',
            'bedrooms': 'Chambres', 'salons': 'Salons', 'kitchens': 'Cuisines', 'bathrooms': 'Salles de bain', 'toilets': 'Toilettes', 'rent': 'Loyer mensuel (FC)', 'deposit': 'Garantie / dépôt (FC)', 'max_occupants': 'Nombre maximum d’habitants',
            'furnished': 'Bien meublé ?', 'parking': 'Parking disponible ?', 'security': 'Sécurité disponible ?', 'water': 'Eau disponible ?', 'electricity': 'Courant disponible ?',
        }

    def clean_room_details_json(self):
        raw = self.cleaned_data.get('room_details_json', '')
        if not raw:
            return []
        try:
            value = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            raise forms.ValidationError('Les caractéristiques détaillées des pièces sont invalides.')
        if not isinstance(value, list):
            raise forms.ValidationError('Les caractéristiques détaillées des pièces sont invalides.')
        return value[:100]

    def clean_photos(self):
        files = self.files.getlist('photos')
        if len(files) > 40:
            raise forms.ValidationError('Maximum 40 photos pour un bien, avec un maximum recommandé de 5 photos par zone.')
        for uploaded in files:
            if not uploaded.content_type or not uploaded.content_type.startswith('image/'):
                raise forms.ValidationError('Seules les images sont acceptées.')
        return files

    def clean(self):
        data = super().clean()
        for field in ('water_days_per_week', 'electricity_days_per_week'):
            if data.get(field, 0) > 7:
                self.add_error(field, 'Maximum 7 jours par semaine.')
        if data.get('max_occupants', 0) < 1:
            self.add_error('max_occupants', 'Le nombre maximum d’habitants doit être au moins 1.')
        if data.get('rent') is None or data.get('rent', 0) <= 0:
            self.add_error('rent', 'Le loyer mensuel doit être supérieur à 0 FC.')
        if data.get('deposit', 0) < 0:
            self.add_error('deposit', 'La garantie ne peut pas être négative.')
        if data.get('bedrooms', 0) > 0 and data.get('furnished') and data.get('furnished_bedrooms', 0) > data.get('bedrooms', 0):
            self.add_error('furnished_bedrooms', 'Ne peut pas dépasser le nombre de chambres.')
        if data.get('water') and not data.get('water_source'):
            self.add_error('water_source', 'Précisez la provenance de l’eau.')
        if data.get('electricity') and not data.get('electricity_source'):
            self.add_error('electricity_source', 'Précisez la provenance du courant.')
        if data.get('furnished') and not data.get('furniture_details'):
            self.add_error('furniture_details', 'Décrivez les équipements et meubles fournis.')
        if data.get('shower_count', 0) > 0:
            if not data.get('shower_location'):
                self.add_error('shower_location', 'Précisez intérieur ou extérieur.')
            if not data.get('shower_privacy'):
                self.add_error('shower_privacy', 'Précisez privé ou public/commun.')
            if not data.get('shower_tank_type'):
                self.add_error('shower_tank_type', 'Précisez le type de cuve/réservoir.')
        if data.get('available_now') is False and not data.get('availability_date'):
            self.add_error('availability_date', 'Indiquez la date de disponibilité.')
        return data

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.room_details = self.cleaned_data.get('room_details_json', [])
        if commit:
            obj.save()
            self.save_m2m()
        return obj


class LoginForm(AuthenticationForm):
    username = forms.CharField(label='Email ou téléphone')
