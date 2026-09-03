from django.db import models
from django.contrib.auth.models import User

class Property(models.Model):
    TYPES=[('Appartement','Appartement'),('Maison','Maison'),('Studio','Studio'),('Villa','Villa')]
    STATUSES=[('draft','Brouillon'),('review','En vérification'),('published','Publiée'),('rented','Louée'),('archived','Archivée'),('rejected','Refusée')]
    WATER_SOURCES=[('regideso','REGIDESO'),('forage','Forage'),('puits','Puits'),('citerne','Citerne'),('source','Source naturelle'),('other','Autre')]
    ELECTRICITY_SOURCES=[('snél','SNEL'),('solaire','Solaire'),('generateur','Générateur'),('batterie','Batterie / onduleur'),('other','Autre')]
    FLOOR_TYPES=[('carrelage','Carrelage'),('ciment','Ciment'),('parquet','Parquet'),('vinyle','Vinyle'),('terre','Terre battue'),('other','Autre')]
    CEILING_TYPES=[('dalle','Dalle béton'),('plafond','Plafond classique'),('staff','Staff'),('lambris','Lambris'),('tôle','Tôle'),('other','Autre')]
    reference=models.CharField(max_length=40,unique=True,blank=True)
    owner=models.ForeignKey(User,on_delete=models.CASCADE,related_name='properties')
    title=models.CharField(max_length=180); property_type=models.CharField(max_length=30,choices=TYPES); description=models.TextField(blank=True)
    province=models.CharField(max_length=100,default='Haut-Katanga'); city=models.CharField(max_length=100,default='Lubumbashi'); commune=models.CharField(max_length=100,blank=True); full_address=models.CharField(max_length=255,blank=True)
    bedrooms=models.PositiveIntegerField(default=1); salons=models.PositiveIntegerField(default=1); kitchens=models.PositiveIntegerField(default=1); bathrooms=models.PositiveIntegerField(default=1); toilets=models.PositiveIntegerField(default=1); max_occupants=models.PositiveIntegerField(default=1); floors=models.PositiveIntegerField(default=1); floor_number=models.PositiveIntegerField(default=0); parking=models.BooleanField(default=False); parking_spaces=models.PositiveIntegerField(default=0); security=models.BooleanField(default=True)
    furnished=models.BooleanField(default=False); furniture_details=models.TextField(blank=True); furnished_bedrooms=models.PositiveIntegerField(default=0); furnished_salons=models.PositiveIntegerField(default=0); furnished_kitchens=models.PositiveIntegerField(default=0); furnished_bathrooms=models.PositiveIntegerField(default=0); shower_count=models.PositiveIntegerField(default=0); shower_location=models.CharField(max_length=20,blank=True); shower_privacy=models.CharField(max_length=20,blank=True); shower_tank_type=models.CharField(max_length=80,blank=True); bathroom_details=models.TextField(blank=True); toilet_details=models.TextField(blank=True)
    water=models.BooleanField(default=True); water_days_per_week=models.PositiveIntegerField(default=7); water_source=models.CharField(max_length=30,choices=WATER_SOURCES,blank=True); water_details=models.TextField(blank=True); electricity=models.BooleanField(default=True); electricity_days_per_week=models.PositiveIntegerField(default=7); electricity_source=models.CharField(max_length=30,choices=ELECTRICITY_SOURCES,blank=True); electricity_details=models.TextField(blank=True); floor_type=models.CharField(max_length=30,choices=FLOOR_TYPES,blank=True); ceiling_type=models.CharField(max_length=30,choices=CEILING_TYPES,blank=True); condition=models.CharField(max_length=120,blank=True); furnished_type=models.CharField(max_length=100,blank=True)
    rent=models.DecimalField(max_digits=10,decimal_places=2,default=0); deposit=models.DecimalField(max_digits=10,decimal_places=2,default=0); margin=models.DecimalField(max_digits=10,decimal_places=2,default=0); availability_date=models.DateField(null=True,blank=True); available_now=models.BooleanField(default=True); rejection_reason=models.TextField(blank=True); status=models.CharField(max_length=20,choices=STATUSES,default='draft'); views=models.PositiveIntegerField(default=0); created_at=models.DateTimeField(auto_now_add=True); updated_at=models.DateTimeField(auto_now=True)
    room_details=models.JSONField(default=list,blank=True)
    def save(self,*args,**kwargs):
        if not self.reference:
            super().save(*args,**kwargs); self.reference=f'FAST-BIEN-{self.pk:06d}'; return super().save(update_fields=['reference'])
        return super().save(*args,**kwargs)

class PropertyImage(models.Model):
    property=models.ForeignKey(Property,on_delete=models.CASCADE,related_name='images'); image=models.ImageField(upload_to='properties/%Y/%m/'); caption=models.CharField(max_length=160,blank=True); is_cover=models.BooleanField(default=False); order=models.PositiveIntegerField(default=0); created_at=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=['order','id']
class Visit(models.Model):
    STATUS=[('pending','En attente'),('confirmed','Confirmée'),('rejected','Refusée'),('done','Effectuée'),('cancelled','Annulée')]
    FINAL_DECISIONS=[('interested','Je suis intéressé'),('thinking','Je souhaite réfléchir'),('not_interested','Je ne suis pas intéressé')]
    property=models.ForeignKey(Property,on_delete=models.CASCADE,related_name='visits'); requester=models.ForeignKey(User,on_delete=models.CASCADE,related_name='visits'); preferred_date=models.DateField(null=True,blank=True); preferred_time=models.TimeField(null=True,blank=True); scheduled_date=models.DateField(null=True,blank=True); scheduled_time=models.TimeField(null=True,blank=True); owner_approved=models.BooleanField(default=False); agent_approved=models.BooleanField(default=False); agent=models.ForeignKey(User,on_delete=models.SET_NULL,null=True,blank=True,related_name='assigned_visits'); observation=models.TextField(blank=True); status=models.CharField(max_length=20,default='pending'); comment=models.TextField(blank=True); final_decision=models.CharField(max_length=30,choices=FINAL_DECISIONS,blank=True); final_decision_comment=models.TextField(blank=True); final_decision_at=models.DateTimeField(null=True,blank=True); created_at=models.DateTimeField(auto_now_add=True)
class VisitInspection(models.Model):
    visit=models.OneToOneField(Visit,on_delete=models.CASCADE,related_name='inspection'); condition=models.TextField(blank=True); meter_readings=models.TextField(blank=True); keys_received=models.PositiveIntegerField(default=0); notes=models.TextField(blank=True); signed_by_tenant=models.BooleanField(default=False); signed_by_agent=models.BooleanField(default=False); created_at=models.DateTimeField(auto_now_add=True); updated_at=models.DateTimeField(auto_now=True)
class Contract(models.Model):
    reference=models.CharField(max_length=40,unique=True,blank=True); property=models.ForeignKey(Property,on_delete=models.PROTECT,related_name='contracts'); user=models.ForeignKey(User,on_delete=models.PROTECT,related_name='contracts'); role=models.CharField(max_length=20,choices=[('tenant','Locataire'),('owner','Propriétaire')]); amount=models.DecimalField(max_digits=10,decimal_places=2); status=models.CharField(max_length=20,default='active'); start_date=models.DateField(null=True,blank=True); end_date=models.DateField(null=True,blank=True); created_at=models.DateTimeField(auto_now_add=True)
    def save(self,*args,**kwargs):
        if not self.reference:
            super().save(*args,**kwargs); self.reference=f'FAST-CTR-{self.created_at.year if self.created_at else 2026}-{self.pk:06d}'; return super().save(update_fields=['reference'])
        return super().save(*args,**kwargs)
class ContractDocument(models.Model):
    contract=models.ForeignKey(Contract,on_delete=models.CASCADE,related_name='documents'); document=models.FileField(upload_to='contracts/%Y/%m/'); label=models.CharField(max_length=160,default='Document contractuel'); created_at=models.DateTimeField(auto_now_add=True)
class Payment(models.Model):
    STATUS=[('upcoming','À venir'),('paid','Payé'),('partial','Partiellement payé'),('late','En retard'),('cancelled','Annulé')]
    contract=models.ForeignKey(Contract,on_delete=models.CASCADE,related_name='payments'); amount_due=models.DecimalField(max_digits=10,decimal_places=2); amount_paid=models.DecimalField(max_digits=10,decimal_places=2,default=0); due_date=models.DateField(); paid_date=models.DateField(null=True,blank=True); reference=models.CharField(max_length=80,blank=True); status=models.CharField(max_length=20,default='upcoming')
class PaymentProof(models.Model):
    payment=models.ForeignKey(Payment,on_delete=models.CASCADE,related_name='proofs'); file=models.FileField(upload_to='payments/%Y/%m/'); note=models.CharField(max_length=200,blank=True); uploaded_by=models.ForeignKey(User,on_delete=models.PROTECT); created_at=models.DateTimeField(auto_now_add=True)
class VerificationDocument(models.Model):
    KINDS=[('id_front','Pièce identité — recto'),('id_back','Pièce identité — verso'),('selfie','Selfie de vérification'),('other','Autre')]
    user=models.ForeignKey(User,on_delete=models.CASCADE,related_name='verification_documents'); kind=models.CharField(max_length=20); file=models.FileField(upload_to='verification/%Y/%m/'); status=models.CharField(max_length=20,default='pending'); note=models.TextField(blank=True); created_at=models.DateTimeField(auto_now_add=True)
class VerificationDossier(models.Model):
    STATUS=[('pending','En attente'),('review','En cours de vérification'),('approved','Vérification validée'),('rejected','Vérification refusée'),('needs_info','Informations supplémentaires requises')]
    user=models.OneToOneField(User,on_delete=models.CASCADE,related_name='verification_dossier'); id_front=models.FileField(upload_to='verification/%Y/%m/',blank=True); id_back=models.FileField(upload_to='verification/%Y/%m/',blank=True); selfie=models.FileField(upload_to='verification/%Y/%m/',blank=True); status=models.CharField(max_length=20,choices=STATUS,default='pending'); note=models.TextField(blank=True); created_at=models.DateTimeField(auto_now_add=True); updated_at=models.DateTimeField(auto_now=True)
class AuditLog(models.Model):
    actor=models.ForeignKey(User,on_delete=models.SET_NULL,null=True,blank=True,related_name='audit_logs'); action=models.CharField(max_length=120); object_type=models.CharField(max_length=80,blank=True); object_id=models.CharField(max_length=80,blank=True); ip_address=models.GenericIPAddressField(null=True,blank=True); details=models.JSONField(default=dict,blank=True); created_at=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=['-created_at']
class Notification(models.Model):
    user=models.ForeignKey(User,on_delete=models.CASCADE,related_name='notifications'); title=models.CharField(max_length=180); message=models.TextField(); read=models.BooleanField(default=False); created_at=models.DateTimeField(auto_now_add=True)
