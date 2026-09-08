import json
from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm
from .models import Property, UserProfile

class RegisterForm(forms.ModelForm):
    postnom=forms.CharField(label='Postnom',max_length=100,required=False)
    profession=forms.ChoiceField(label='Profession',choices=[('', 'Sélectionnez votre profession')]+UserProfile.PROFESSIONS,required=True)
    date_of_birth=forms.DateField(label='Date de naissance',required=True,widget=forms.DateInput(attrs={'type':'date','autocomplete':'bday'}))
    password=forms.CharField(widget=forms.PasswordInput(attrs={'autocomplete':'new-password'}),label='Mot de passe')
    password2=forms.CharField(widget=forms.PasswordInput(attrs={'autocomplete':'new-password'}),label='Confirmation du mot de passe')
    class Meta:
        model=User; fields=['last_name','postnom','first_name','username','email','password']
        labels={'last_name':'Nom','first_name':'Prénom','username':'Téléphone','email':'Adresse électronique'}
        widgets={'last_name':forms.TextInput(attrs={'placeholder':'Votre nom'}),'first_name':forms.TextInput(attrs={'placeholder':'Votre prénom'}),'username':forms.TextInput(attrs={'placeholder':'Ex. 0812345678','autocomplete':'tel'}),'email':forms.EmailInput(attrs={'placeholder':'exemple@domaine.com','autocomplete':'email'})}
    def clean(self):
        data=super().clean()
        if data.get('password')!=data.get('password2'): self.add_error('password2','Les mots de passe ne correspondent pas.')
        return data
    def save(self,commit=True):
        user=super().save(commit=commit); profile_data={'postnom':self.cleaned_data.get('postnom','').strip(),'profession':self.cleaned_data.get('profession',''),'date_of_birth':self.cleaned_data.get('date_of_birth')}
        if commit: UserProfile.objects.update_or_create(user=user,defaults=profile_data)
        else: user._registration_profile_data=profile_data
        return user

class PropertyForm(forms.ModelForm):
    room_details_json=forms.CharField(required=False,widget=forms.HiddenInput())
    photos=forms.FileField(required=False,widget=forms.ClearableFileInput(attrs={'accept':'image/*','capture':'environment'}))
    owner_authorized_publication=forms.BooleanField(required=False,label='Je confirme être autorisé à publier ce bien.')
    owner_authorized_subletting=forms.BooleanField(required=False,label='J’autorise FASTHOME à utiliser ce bien pour son activité de sous-location.')
    title=forms.CharField(required=False,widget=forms.HiddenInput())
    YES_NO=[('', 'Sélectionnez'),(True,'Oui'),(False,'Non')]
    PROVINCES=[('', 'Sélectionnez la province'),*[(x,x) for x in ['Bas-Uele','Équateur','Haut-Katanga','Haut-Lomami','Haut-Uele','Ituri','Kasaï','Kasaï-Central','Kasaï-Oriental','Kinshasa','Kongo-Central','Kwango','Kwilu','Lomami','Lualaba','Mai-Ndombe','Maniema','Mongala','Nord-Kivu','Nord-Ubangi','Sankuru','Sud-Kivu','Sud-Ubangi','Tanganyika','Tshopo','Tshuapa']]]
    CITIES=[('', 'Sélectionnez la ville')]+[(x,x) for x in ['Lubumbashi','Likasi','Kolwezi','Kinshasa','Matadi','Boma','Kananga','Mbuji-Mayi','Kisangani','Goma','Bukavu','Kindu','Kalemie','Isiro','Bunia','Butembo','Bandundu','Kikwit','Tshikapa','Boende','Gemena','Lisala','Mbandaka','Inongo','Kabinda','Mwene-Ditu','Autre ville']]
    furnished=forms.TypedChoiceField(label='Bien meublé ?',choices=YES_NO,coerce=lambda v:v=='True',empty_value=None)
    parking=forms.TypedChoiceField(label='Parking disponible ?',choices=YES_NO,coerce=lambda v:v=='True',empty_value=None)
    security=forms.TypedChoiceField(label='Sécurité disponible ?',choices=YES_NO,coerce=lambda v:v=='True',empty_value=None)
    water=forms.TypedChoiceField(label='Eau disponible ?',choices=YES_NO,coerce=lambda v:v=='True',empty_value=None)
    electricity=forms.TypedChoiceField(label='Courant disponible ?',choices=YES_NO,coerce=lambda v:v=='True',empty_value=None)
    available_now=forms.TypedChoiceField(label='Le bien est-il disponible maintenant ?',choices=YES_NO,coerce=lambda v:v=='True',empty_value=None)
    fence=forms.TypedChoiceField(label='Clôture',choices=[('', 'Sélectionnez'),(True,'Oui'),(False,'Non')],coerce=lambda v:v=='True',empty_value=None)
    fence_type=forms.ChoiceField(label='Type de clôture',choices=[('', 'Sélectionnez'),*Property.FENCE_TYPES],required=False)
    fence_condition=forms.ChoiceField(label='État de la clôture',choices=[('', 'Sélectionnez'),('bon','Bon état'),('moyen','État moyen'),('mauvais','Mauvais état')],required=False)
    water_source=forms.ChoiceField(label='Provenance de l’eau',choices=[('', 'Sélectionnez'),*Property.WATER_SOURCES],required=False)
    electricity_source=forms.ChoiceField(label='Source du courant',choices=[('', 'Sélectionnez'),*Property.ELECTRICITY_SOURCES],required=False)
    floor_type=forms.ChoiceField(label='Type de sol',choices=[('', 'Sélectionnez'),*Property.FLOOR_TYPES],required=False)
    ceiling_type=forms.ChoiceField(label='Type de plafond',choices=[('', 'Sélectionnez'),*Property.CEILING_TYPES],required=False)
    condition=forms.ChoiceField(label='État général du bien',choices=[('', 'Sélectionnez'),('neuf','Neuf'),('tres_bon','Très bon état'),('bon','Bon état'),('a_rafraichir','À rafraîchir'),('a_rehabiliter','À réhabiliter')],required=False)
    furnished_type=forms.ChoiceField(label='Niveau de mobilier',choices=[('', 'Sélectionnez'),('simple','Meublé simple'),('confort','Meublé confort'),('haut_gamme','Meublé haut de gamme')],required=False)
    class Meta:
        model=Property
        exclude=['owner','reference','status','views','created_at','updated_at','margin','room_details','shower_count','floors','floor_number']
        widgets={'description':forms.Textarea(attrs={'rows':3,'placeholder':'Quelques précisions utiles sur le bien…'}),'commune':forms.TextInput(),'neighborhood':forms.TextInput(),'avenue':forms.TextInput(),'number':forms.TextInput(),'geolocation_link':forms.URLInput(),'availability_date':forms.DateInput(attrs={'type':'date'}),'water_days_per_week':forms.NumberInput(attrs={'min':0,'max':7,'step':1}),'electricity_days_per_week':forms.NumberInput(attrs={'min':0,'max':7,'step':1}),'max_occupants':forms.NumberInput(attrs={'min':1,'max':20,'step':1}),'bedrooms':forms.NumberInput(attrs={'min':0,'max':15,'step':1}),'salons':forms.NumberInput(attrs={'min':0,'max':10,'step':1}),'kitchens':forms.NumberInput(attrs={'min':0,'max':5,'step':1}),'bathrooms':forms.NumberInput(attrs={'min':0,'max':10,'step':1}),'toilets':forms.NumberInput(attrs={'min':0,'max':10,'step':1}),'parking_spaces':forms.NumberInput(attrs={'min':0,'max':10,'step':1}),'rent':forms.NumberInput(attrs={'min':1,'step':'1'}),'deposit':forms.NumberInput(attrs={'min':0,'step':'1'}),'water_details':forms.Textarea(attrs={'rows':2,'placeholder':'Ex. eau disponible le matin, pression faible, réservoir…'}),'electricity_details':forms.Textarea(attrs={'rows':2,'placeholder':'Ex. coupures fréquentes, compteur individuel, autonomie…'})}
        labels={'property_type':'Type de bien','description':'Description','commune':'Commune','neighborhood':'Quartier','avenue':'Avenue / rue / boulevard','number':'Numéro','geolocation_link':'Lien de géolocalisation','bedrooms':'Chambres','salons':'Salons','kitchens':'Cuisines','bathrooms':'Salles de bain','toilets':'Toilettes','rent':'Loyer mensuel','deposit':'Garantie / dépôt','max_occupants':'Nombre maximum d’habitants'}
    def clean_room_details_json(self):
        raw=self.cleaned_data.get('room_details_json','')
        if not raw:return []
        try:value=json.loads(raw)
        except (TypeError,ValueError,json.JSONDecodeError):raise forms.ValidationError('Les caractéristiques détaillées sont invalides.')
        if not isinstance(value,list):raise forms.ValidationError('Les caractéristiques détaillées sont invalides.')
        return value[:100]
    def clean_photos(self):
        files=self.files.getlist('photos')
        if len(files)>40:raise forms.ValidationError('Maximum 40 photos pour un bien.')
        for uploaded in files:
            if not uploaded.content_type or not uploaded.content_type.startswith('image/'):raise forms.ValidationError('Seules les images sont acceptées.')
        return files
    def clean(self):
        data=super().clean()
        for field in ('water_days_per_week','electricity_days_per_week'):
            if data.get(field,0)>7:self.add_error(field,'Maximum 7 jours par semaine.')
        if data.get('max_occupants',0)<1:self.add_error('max_occupants','Le nombre maximum d’habitants doit être au moins 1.')
        if data.get('rent') is None or data.get('rent',0)<=0:self.add_error('rent','Le loyer mensuel doit être supérieur à 0 FC.')
        if data.get('deposit',0)<0:self.add_error('deposit','La garantie ne peut pas être négative.')
        # Les détails conditionnels (source d'eau, source du courant, clôture)
        # restent facultatifs à la soumission. FASTHOME pourra les compléter
        # lors de la vérification sur place plutôt que bloquer la publication.
        return data
    def save(self,commit=True):
        obj=super().save(commit=False);obj.room_details=self.cleaned_data.get('room_details_json',[])
        if commit:obj.save();self.save_m2m()
        return obj

class LoginForm(AuthenticationForm):
    username=forms.CharField(label='Adresse électronique ou téléphone')
