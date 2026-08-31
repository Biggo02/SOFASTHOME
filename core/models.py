from django.db import models
from django.contrib.auth.models import User

class Property(models.Model):
    TYPES=[('Appartement','Appartement'),('Maison','Maison'),('Studio','Studio'),('Villa','Villa')]
    STATUSES=[('draft','Brouillon'),('review','En vérification'),('validated','Validée'),('published','Publiée'),('rented','Louée'),('archived','Archivée'),('rejected','Refusée')]
    reference=models.CharField(max_length=40,unique=True,blank=True)
    owner=models.ForeignKey(User,on_delete=models.CASCADE,related_name='properties')
    title=models.CharField(max_length=180)
    property_type=models.CharField(max_length=30,choices=TYPES)
    description=models.TextField(blank=True)
    province=models.CharField(max_length=100,default='Haut-Katanga')
    city=models.CharField(max_length=100,default='Lubumbashi')
    commune=models.CharField(max_length=100,blank=True)
    neighborhood=models.CharField(max_length=120,blank=True)
    bedrooms=models.PositiveIntegerField(default=1)
    salons=models.PositiveIntegerField(default=1)
    bathrooms=models.PositiveIntegerField(default=1)
    parking=models.BooleanField(default=False)
    water=models.BooleanField(default=True)
    electricity=models.BooleanField(default=True)
    security=models.BooleanField(default=True)
    furnished=models.BooleanField(default=False)
    rent=models.DecimalField(max_digits=10,decimal_places=2,default=0)
    deposit=models.DecimalField(max_digits=10,decimal_places=2,default=0)
    margin=models.DecimalField(max_digits=10,decimal_places=2,default=0)
    rejection_reason=models.TextField(blank=True)
    status=models.CharField(max_length=20,choices=STATUSES,default='draft')
    views=models.PositiveIntegerField(default=0)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)
    def save(self,*args,**kwargs):
        if not self.reference:
            super().save(*args,**kwargs); self.reference=f'FAST-BIEN-{self.pk:06d}'; return super().save(update_fields=['reference'])
        return super().save(*args,**kwargs)
    @property
    def match_score(self):
        score=70; score+=10 if self.security else 0; score+=10 if self.water else 0; score+=5 if self.electricity else 0
        return min(score,100)

class Visit(models.Model):
    STATUS=[('pending','En attente'),('confirmed','Confirmée'),('rejected','Refusée'),('done','Effectuée'),('cancelled','Annulée')]
    property=models.ForeignKey(Property,on_delete=models.CASCADE,related_name='visits')
    requester=models.ForeignKey(User,on_delete=models.CASCADE,related_name='visits')
    preferred_date=models.DateField(null=True,blank=True)
    preferred_time=models.TimeField(null=True,blank=True)
    scheduled_date=models.DateField(null=True,blank=True)
    scheduled_time=models.TimeField(null=True,blank=True)
    owner_approved=models.BooleanField(default=False)
    agent_approved=models.BooleanField(default=False)
    agent=models.ForeignKey(User,on_delete=models.SET_NULL,null=True,blank=True,related_name='assigned_visits')
    observation=models.TextField(blank=True)
    status=models.CharField(max_length=20,choices=STATUS,default='pending')
    comment=models.TextField(blank=True)
    created_at=models.DateTimeField(auto_now_add=True)

class Contract(models.Model):
    reference=models.CharField(max_length=40,unique=True,blank=True)
    property=models.ForeignKey(Property,on_delete=models.PROTECT,related_name='contracts')
    user=models.ForeignKey(User,on_delete=models.PROTECT,related_name='contracts')
    role=models.CharField(max_length=20,choices=[('tenant','Locataire'),('owner','Propriétaire')])
    amount=models.DecimalField(max_digits=10,decimal_places=2)
    status=models.CharField(max_length=20,default='active')
    start_date=models.DateField(null=True,blank=True)
    end_date=models.DateField(null=True,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    def save(self,*args,**kwargs):
        if not self.reference:
            super().save(*args,**kwargs); self.reference=f'FAST-CTR-{self.created_at.year if self.created_at else 2026}-{self.pk:06d}'; return super().save(update_fields=['reference'])
        return super().save(*args,**kwargs)

class Payment(models.Model):
    STATUS=[('upcoming','À venir'),('paid','Payé'),('partial','Partiellement payé'),('late','En retard'),('cancelled','Annulé')]
    contract=models.ForeignKey(Contract,on_delete=models.CASCADE,related_name='payments')
    amount_due=models.DecimalField(max_digits=10,decimal_places=2)
    amount_paid=models.DecimalField(max_digits=10,decimal_places=2,default=0)
    due_date=models.DateField()
    paid_date=models.DateField(null=True,blank=True)
    reference=models.CharField(max_length=80,blank=True)
    status=models.CharField(max_length=20,choices=STATUS,default='upcoming')

class Notification(models.Model):
    user=models.ForeignKey(User,on_delete=models.CASCADE,related_name='notifications')
    title=models.CharField(max_length=180)
    message=models.TextField()
    read=models.BooleanField(default=False)
    created_at=models.DateTimeField(auto_now_add=True)
