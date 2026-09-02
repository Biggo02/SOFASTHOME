from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm
from .models import Property

class RegisterForm(forms.ModelForm):
    password=forms.CharField(widget=forms.PasswordInput)
    password2=forms.CharField(widget=forms.PasswordInput,label='Confirmation du mot de passe')
    class Meta:
        model=User; fields=['first_name','username','email','password']; labels={'first_name':'Nom complet','username':'Téléphone'}
    def clean(self):
        data=super().clean()
        if data.get('password')!=data.get('password2'): raise forms.ValidationError('Les mots de passe ne correspondent pas.')
        return data

class PropertyForm(forms.ModelForm):
    class Meta:
        model=Property
        exclude=['owner','reference','status','views','created_at','updated_at','margin']
        widgets={
            'description':forms.Textarea(attrs={'rows':4,'placeholder':'Décrivez le bien, son environnement et ses particularités…'}),
            'full_address':forms.TextInput(attrs={'placeholder':'Adresse exacte — non affichée publiquement'}),
            'availability_date':forms.DateInput(attrs={'type':'date'}),
            'water_days_per_week':forms.NumberInput(attrs={'min':0,'max':7}),
            'electricity_days_per_week':forms.NumberInput(attrs={'min':0,'max':7}),
            'max_occupants':forms.NumberInput(attrs={'min':1,'max':100}),
            'bedrooms':forms.NumberInput(attrs={'min':0}), 'salons':forms.NumberInput(attrs={'min':0}),
            'kitchens':forms.NumberInput(attrs={'min':0}), 'bathrooms':forms.NumberInput(attrs={'min':0}),
            'toilets':forms.NumberInput(attrs={'min':0}), 'shower_count':forms.NumberInput(attrs={'min':0}),
            'rent':forms.NumberInput(attrs={'min':1,'step':'1','placeholder':'Ex. 500000 FC'}),
            'deposit':forms.NumberInput(attrs={'min':0,'step':'1','placeholder':'Ex. 100000 FC'}),
        }
        labels={'max_occupants':'Nombre maximum d’habitants','bedrooms':'Chambres','salons':'Salons','kitchens':'Cuisines','bathrooms':'Salles de bain','toilets':'Toilettes','rent':'Loyer mensuel (FC)','deposit':'Garantie / dépôt (FC)'}
    def clean(self):
        data=super().clean()
        for field in ('water_days_per_week','electricity_days_per_week'):
            if data.get(field,0)>7: self.add_error(field,'Maximum 7 jours par semaine.')
        if data.get('max_occupants',0)<1: self.add_error('max_occupants','Le nombre maximum d’habitants doit être au moins 1.')
        if data.get('rent') is None or data.get('rent',0)<=0: self.add_error('rent','Le loyer mensuel doit être supérieur à 0 FC.')
        if data.get('deposit',0)<0: self.add_error('deposit','La garantie ne peut pas être négative.')
        if data.get('bedrooms',0)>0 and data.get('furnished') and data.get('furnished_bedrooms',0)>data.get('bedrooms',0): self.add_error('furnished_bedrooms','Ne peut pas dépasser le nombre de chambres.')
        if data.get('water') and not data.get('water_source'): self.add_error('water_source','Précisez la provenance de l’eau.')
        if data.get('electricity') and not data.get('electricity_source'): self.add_error('electricity_source','Précisez la provenance du courant.')
        if data.get('furnished') and not data.get('furniture_details'): self.add_error('furniture_details','Décrivez les équipements et meubles fournis.')
        if data.get('shower_count',0)>0:
            if not data.get('shower_location'): self.add_error('shower_location','Précisez intérieur ou extérieur.')
            if not data.get('shower_privacy'): self.add_error('shower_privacy','Précisez privé ou public/commun.')
            if not data.get('shower_tank_type'): self.add_error('shower_tank_type','Précisez le type de cuve/réservoir.')
        if data.get('available_now') is False and not data.get('availability_date'): self.add_error('availability_date','Indiquez la date de disponibilité.')
        return data

class LoginForm(AuthenticationForm):
    username=forms.CharField(label='Email ou téléphone')
