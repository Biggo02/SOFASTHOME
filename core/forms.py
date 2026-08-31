from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm
from .models import Property

class RegisterForm(forms.ModelForm):
    password=forms.CharField(widget=forms.PasswordInput)
    password2=forms.CharField(widget=forms.PasswordInput,label='Confirmation du mot de passe')
    class Meta:
        model=User
        fields=['first_name','username','email','password']
        labels={'first_name':'Nom complet','username':'Téléphone'}
    def clean(self):
        data=super().clean()
        if data.get('password')!=data.get('password2'): raise forms.ValidationError('Les mots de passe ne correspondent pas.')
        return data

class PropertyForm(forms.ModelForm):
    class Meta:
        model=Property
        exclude=['owner','reference','status','views','created_at','updated_at','margin']
        widgets={'description':forms.Textarea(attrs={'rows':4})}

class LoginForm(AuthenticationForm):
    username=forms.CharField(label='Email ou téléphone')
