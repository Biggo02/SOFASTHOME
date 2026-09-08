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
        labels = {'last_name': 'Nom', 'first_name': 'Prénom', 'username': 'Téléphone', 'email': 'Adresse électronique'}
        widgets = {'last_name': forms.TextInput(attrs={'placeholder': 'Votre nom'}), 'first_name': forms.TextInput(attrs={'placeholder': 'Votre prénom'}), 'username': forms.TextInput(attrs={'placeholder': 'Ex. 0812345678', 'autocomplete': 'tel'}), 'email': forms.EmailInput(attrs={'placeholder': 'exemple@domaine.com', 'autocomplete': 'email'})}
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

    YES_NO = [(True, 'Oui'), (False, 'Non')]
    PRIVACY_CHOICES = [('', 'Sélectionnez'), ('privees', 'Privées'), ('communes', 'Communes'), ('les_deux', 'Les deux')]
    LOCATION_CHOICES = [('', 'Sélectionnez'), ('interieure', 'Intérieure'), ('exterieure', 'Extérieure'), ('les_deux', 'Les deux')]
    TANK_CHOICES = [('', 'Sélectionnez'), ('aucune', 'Sans réservoir'), ('petite', 'Petit réservoir'), ('moyenne', 'Réservoir moyen'), ('grande', 'Grand réservoir'), ('citerne', 'Citerne')]
    CONDITION_CHOICES = [('', 'Sélectionnez'), ('neuf', 'Neuf'), ('tres_bon', 'Très bon état'), ('bon', 'Bon état'), ('a_rafraichir', 'À rafraîchir'), ('a_rehabiliter', 'À réhabiliter')]
    FURNISHED_TYPE_CHOICES = [('', 'Sélectionnez'), ('simple', 'Meublé simple'), ('confort', 'Meublé confort'), ('haut_gamme', 'Meublé haut de gamme')]
    PROVINCES = [('Bas-Uele','Bas-Uele'),('Équateur','Équateur'),('Haut-Katanga','Haut-Katanga'),('Haut-Lomami','Haut-Lomami'),('Haut-Uele','Haut-Uele'),('Ituri','Ituri'),('Kasaï','Kasaï'),('Kasaï-Central','Kasaï-Central'),('Kasaï-Oriental','Kasaï-Oriental'),('Kinshasa','Kinshasa'),('Kongo-Central','Kongo-Central'),('Kwango','Kwango'),('Kwilu','Kwilu'),('Lomami','Lomami'),('Lualaba','Lualaba'),('Mai-Ndombe','Mai-Ndombe'),('Maniema','Maniema'),('Mongala','Mongala'),('Nord-Kivu','Nord-Kivu'),('Nord-Ubangi','Nord-Ubangi'),('Sankuru','Sankuru'),('Sud-Kivu','Sud-Kivu'),('Sud-Ubangi','Sud-Ubangi'),('Tanganyika','Tanganyika'),('Tshopo','Tshopo'),('Tshuapa','Tshuapa')]
    CITIES = [('', 'Sélectionnez la ville'),('Lubumbashi','Lubumbashi'),('Likasi','Likasi'),('Kolwezi','Kolwezi'),('Kinshasa','Kinshasa'),('Matadi','Matadi'),('Boma','Boma'),('Kananga','Kananga'),('Mbuji-Mayi','Mbuji-Mayi'),('Kisangani','Kisangani'),('Goma','Goma'),('Bukavu','Bukavu'),('Kindu','Kindu'),('Kalemie','Kalemie'),('Isiro','Isiro'),('Bunia','Bunia'),('Butembo','Butembo'),('Bandundu','Bandundu'),('Kikwit','Kikwit'),('Tshikapa','Tshikapa'),('Boende','Boende'),('Gemena','Gemena'),('Lisala','Lisala'),('Mbandaka','Mbandaka'),('Inongo','Inongo'),('Kabinda','Kabinda'),('Mwene-Ditu','Mwene-Ditu'),('Autre','Autre ville')]

    furnished = forms.TypedChoiceField(label='Bien meublé ?', choices=YES_NO, coerce=lambda v: v == 'True', empty_value=None, widget=forms.Select())
    parking = forms.TypedChoiceField(label='Parking disponible ?', choices=YES_NO, coerce=lambda v: v == 'True', empty_value=None, widget=forms.Select())
    security = forms.TypedChoiceField(label='Sécurité disponible ?', choices=YES_NO, coerce=lambda v: v == 'True', empty_value=None, widget=forms.Select())
    water = forms.TypedChoiceField(label='Eau disponible ?', choices=YES_NO, coerce=lambda v: v == 'True', empty_value=None, widget=forms.Select())
    electricity = forms.TypedChoiceField(label='Courant disponible ?', choices=YES_NO, coerce=lambda v: v == 'True', empty_value=None, widget=forms.Select())
    available_now = forms.TypedChoiceField(label='Le bien est-il disponible maintenant ?', choices=YES_NO, coerce=lambda v: v == 'True', empty_value=None, widget=forms.Select())
    shower_privacy = forms.ChoiceField(label='Les douches sont', choices=PRIVACY_CHOICES, required=False)
    shower_location = forms.ChoiceField(label='Les douches se trouvent', choices=LOCATION_CHOICES, required=False)
    shower_tank_type = forms.ChoiceField(label='Alimentation de la douche', choices=TANK_CHOICES, required=False)
    condition = forms.ChoiceField(label='État général du bien', choices=CONDITION_CHOICES, required=False)
    furnished_type = forms.ChoiceField(label='Niveau de mobilier', choices=FURNISHED_TYPE_CHOICES, required=False)
    water_source = forms.ChoiceField(label='Provenance de l’eau', choices=[('', 'Sélectionnez'), *Property.WATER_SOURCES], required=False)
    electricity_source = forms.ChoiceField(label='Source du courant', choices=[('', 'Sélectionnez'), *Property.ELECTRICITY_SOURCES], required=False)
    floor_type = forms.ChoiceField(label='Type de sol', choices=[('', 'Sélectionnez'), *Property.FLOOR_TYPES], required=False)
    ceiling_type = forms.ChoiceField(label='Type de plafond', choices=[('', 'Sélectionnez'), *Property.CEILING_TYPES], required=False)
    province = forms.ChoiceField(label='Province', choices=PROVINCES, required=True)
    city = forms.ChoiceField(label='Ville', choices=CITIES, required=True)

    class Meta:
        model = Property
        exclude = ['owner', 'reference', 'status', 'views', 'created_at', 'updated_at', 'margin', 'room_details']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Quelques précisions utiles sur le bien…'}),
            'commune': forms.TextInput(attrs={'placeholder': 'Nom de la commune'}), 'neighborhood': forms.TextInput(attrs={'placeholder': 'Nom du quartier'}), 'avenue': forms.TextInput(attrs={'placeholder': 'Nom de l’avenue / rue / boulevard'}), 'number': forms.TextInput(attrs={'placeholder': 'Numéro de la parcelle ou de la maison'}),
            'geolocation_link': forms.URLInput(attrs={'placeholder': 'Collez ici le lien de localisation'}), 'availability_date': forms.DateInput(attrs={'type': 'date'}),
            'water_days_per_week': forms.Select(choices=[(i, str(i)) for i in range(8)]), 'electricity_days_per_week': forms.Select(choices=[(i, str(i)) for i in range(8)]), 'max_occupants': forms.Select(choices=[(i, str(i)) for i in range(1, 21)]),
            'bedrooms': forms.Select(choices=[(i, str(i)) for i in range(0, 16)]), 'salons': forms.Select(choices=[(i, str(i)) for i in range(0, 11)]), 'kitchens': forms.Select(choices=[(i, str(i)) for i in range(0, 6)]), 'bathrooms': forms.Select(choices=[(i, str(i)) for i in range(0, 11)]), 'toilets': forms.Select(choices=[(i, str(i)) for i in range(0, 11)]), 'shower_count': forms.Select(choices=[(i, str(i)) for i in range(0, 11)]), 'floors': forms.Select(choices=[(i, str(i)) for i in range(1, 11)]), 'floor_number': forms.Select(choices=[(i, str(i)) for i in range(0, 11)]), 'parking_spaces': forms.Select(choices=[(i, str(i)) for i in range(0, 11)]),
            'rent': forms.NumberInput(attrs={'min': 1, 'step': '1', 'placeholder': 'Ex. 500000'}), 'deposit': forms.NumberInput(attrs={'min': 0, 'step': '1', 'placeholder': 'Ex. 1500000'}),
        }
        labels = {'property_type':'Type de bien','description':'Description','commune':'Commune','neighborhood':'Quartier','avenue':'Avenue / rue / boulevard','number':'Numéro','geolocation_link':'Lien de géolocalisation','bedrooms':'Chambres','salons':'Salons','kitchens':'Cuisines','bathrooms':'Salles de bain','toilets':'Toilettes','rent':'Loyer mensuel','deposit':'Garantie / dépôt','max_occupants':'Nombre maximum d’habitants','parking':'Parking disponible ?','security':'Sécurité disponible ?','water':'Eau disponible ?','electricity':'Courant disponible ?','available_now':'Disponibilité'}

    def clean_room_details_json(self):
        raw = self.cleaned_data.get('room_details_json', '')
        if not raw: return []
        try: value = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError): raise forms.ValidationError('Les caractéristiques détaillées sont invalides.')
        if not isinstance(value, list): raise forms.ValidationError('Les caractéristiques détaillées sont invalides.')
        return value[:100]
    def clean_photos(self):
        files = self.files.getlist('photos')
        if len(files) > 40: raise forms.ValidationError('Maximum 40 photos pour un bien.')
        for uploaded in files:
            if not uploaded.content_type or not uploaded.content_type.startswith('image/'): raise forms.ValidationError('Seules les images sont acceptées.')
        return files
    def clean(self):
        data = super().clean()
        for field in ('water_days_per_week','electricity_days_per_week'):
            if data.get(field,0)>7: self.add_error(field,'Maximum 7 jours par semaine.')
        if data.get('max_occupants',0)<1: self.add_error('max_occupants','Le nombre maximum d’habitants doit être au moins 1.')
        if data.get('rent') is None or data.get('rent',0)<=0: self.add_error('rent','Le loyer mensuel doit être supérieur à 0 FC.')
        if data.get('deposit',0)<0: self.add_error('deposit','La garantie ne peut pas être négative.')
        if data.get('water') and not data.get('water_source'): self.add_error('water_source','Précisez la provenance de l’eau.')
        if data.get('electricity') and not data.get('electricity_source'): self.add_error('electricity_source','Précisez la source du courant.')
        if data.get('furnished') and not data.get('furniture_details'): self.add_error('furniture_details','Décrivez les meubles et équipements fournis.')
        if data.get('shower_count',0)>0:
            if not data.get('shower_location'): self.add_error('shower_location','Précisez où se trouvent les douches.')
            if not data.get('shower_privacy'): self.add_error('shower_privacy','Précisez si elles sont privées, communes ou les deux.')
            if not data.get('shower_tank_type'): self.add_error('shower_tank_type','Précisez l’alimentation de la douche.')
        if data.get('available_now') is False and not data.get('availability_date'): self.add_error('availability_date','Indiquez la date de disponibilité.')
        return data
    def save(self, commit=True):
        obj=super().save(commit=False); obj.room_details=self.cleaned_data.get('room_details_json',[])
        if commit: obj.save(); self.save_m2m()
        return obj


class LoginForm(AuthenticationForm):
    username=forms.CharField(label='Adresse électronique ou téléphone')
