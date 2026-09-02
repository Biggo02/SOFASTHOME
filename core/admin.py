import json

from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from .models import Property, PropertyImage, Visit, VisitInspection, Contract, ContractDocument, Payment, PaymentProof, VerificationDocument, AuditLog, Notification

admin.site.site_header='FASTHOME — Administration'; admin.site.site_title='FASTHOME Admin'; admin.site.index_title='Centre de gestion immobilière'

@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display=('reference','title','owner_identity','city','neighborhood','status_badge','workflow_action','views','updated_at'); list_filter=('status','property_type','city','furnished','security'); search_fields=('reference','title','city','commune','neighborhood','owner__username','owner__first_name','owner__last_name','owner__email'); readonly_fields=('reference','status_display','views','created_at','updated_at','owner_identity_detail','workflow_action_detail','room_details_display'); list_per_page=30
    def get_queryset(self, request): return super().get_queryset(request).exclude(status='draft')
    @admin.display(description='Propriétaire',ordering='owner__last_name')
    def owner_identity(self,obj):
        u=obj.owner; name=u.get_full_name().strip() or 'Nom non renseigné'; return f'{name} · ID {u.pk}'
    @admin.display(description='Identité du propriétaire')
    def owner_identity_detail(self,obj):
        u=obj.owner; name=u.get_full_name().strip() or 'Nom non renseigné'; phone=u.username or 'Non renseigné'; email=u.email or 'Non renseigné'
        return format_html('<div style="line-height:1.8"><strong>{}</strong><br>ID utilisateur : <strong>{}</strong><br>Téléphone : <strong>{}</strong><br>Email : <strong>{}</strong></div>',name,u.pk,phone,email)
    @admin.display(description='Caractéristiques détaillées des pièces')
    def room_details_display(self,obj):
        details=obj.room_details or []
        if not details: return format_html('<span style="color:#888">Aucune caractéristique détaillée enregistrée.</span>')
        rows=[]
        for item in details:
            label=f"{item.get('kind','Pièce')} {item.get('index','')}"
            values=[]
            for key,title in [('floor','Sol'),('ceiling','Plafond'),('condition','État'),('furnished','Meublée'),('equipment','Équipements'),('details','Caractéristiques'),('photo','Photo à fournir')]:
                value=item.get(key,'')
                if value: values.append(f'<strong>{title} :</strong> {value}')
            rows.append(f'<div style="padding:10px 0;border-bottom:1px solid #eee"><strong>{label}</strong><br>{"<br>".join(values) if values else "Aucun détail renseigné."}</div>')
        return format_html(''.join(rows))
    @admin.display(description='État')
    def status_badge(self,obj): return obj.get_status_display()
    @admin.display(description='État actuel')
    def status_display(self,obj): return format_html('<strong>{}</strong><br><small>Ce champ est informatif. Utilisez le bouton d’action FASTHOME ci-dessous.</small>',obj.get_status_display())
    @admin.display(description='Action FASTHOME')
    def workflow_action(self,obj):
        url=reverse('review_publication',kwargs={'pk':obj.pk})
        if obj.status=='review': return format_html('<a class="button" href="{}">Vérifier → Publier / Refuser</a>',url)
        if obj.status=='published': return format_html('<a class="button" href="{}">Gérer</a>',url)
        if obj.status=='rented': return format_html('<a class="button" href="{}">Archiver</a>',url)
        return '—'
    @admin.display(description='Action de workflow')
    def workflow_action_detail(self,obj):
        url=reverse('review_publication',kwargs={'pk':obj.pk})
        if obj.status=='review': return format_html('<a class="button" href="{}">Ouvrir la vérification</a><p><strong>Décision :</strong> si tout est conforme, <strong>Publier</strong>. Sinon, <strong>Refuser</strong> avec un motif.</p>',url)
        if obj.status=='published': return format_html('<a class="button" href="{}">Ouvrir la gestion FASTHOME</a>',url)
        if obj.status=='rented': return format_html('<a class="button" href="{}">Archiver ce bien</a>',url)
        return 'Aucune action de workflow disponible à cette étape.'
    fieldsets=(
        ('Identification',{'fields':('reference','owner_identity_detail','title','property_type','description')}),
        ('Localisation',{'fields':('province','city','commune','neighborhood','full_address','latitude','longitude')}),
        ('Composition et capacité',{'fields':('bedrooms','salons','kitchens','bathrooms','toilets','max_occupants','floors','floor_number','parking','parking_spaces','security')}),
        ('Caractéristiques détaillées des pièces',{'fields':('room_details_display',)}),
        ('Mobilier et sanitaires',{'fields':('furnished','furnished_type','furniture_details','furnished_bedrooms','furnished_salons','furnished_kitchens','furnished_bathrooms','shower_count','shower_location','shower_privacy','shower_tank_type','bathroom_details','toilet_details')}),
        ('Services',{'fields':('water','water_days_per_week','water_source','water_details','electricity','electricity_days_per_week','electricity_source','electricity_details')}),
        ('État et disponibilité',{'fields':('floor_type','ceiling_type','condition','available_now','availability_date')}),
        ('Finances privées',{'fields':('rent','deposit','margin')}),
        ('Workflow FASTHOME',{'fields':('status_display','rejection_reason','workflow_action_detail')}),
        ('Suivi',{'fields':('views','created_at','updated_at')}),
    )

@admin.register(PropertyImage)
class PropertyImageAdmin(admin.ModelAdmin):
    list_display=('property','image','is_cover','order','created_at'); list_filter=('is_cover',); search_fields=('property__reference','property__title')
@admin.register(Visit)
class VisitAdmin(admin.ModelAdmin):
    list_display=('id','property','requester','preferred_date','preferred_time','scheduled_date','status','owner_approved','agent_approved'); list_filter=('status','owner_approved','agent_approved','preferred_date'); search_fields=('property__reference','property__title','requester__username','requester__first_name','requester__last_name')
@admin.register(VisitInspection)
class VisitInspectionAdmin(admin.ModelAdmin):
    list_display=('visit','keys_received','signed_by_tenant','signed_by_agent','updated_at'); list_filter=('signed_by_tenant','signed_by_agent')
@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display=('reference','property','user','role','amount','status','start_date','end_date'); list_filter=('status','role'); search_fields=('reference','property__reference','property__title','user__username','user__first_name','user__last_name','user__email'); readonly_fields=('reference','created_at')
@admin.register(ContractDocument)
class ContractDocumentAdmin(admin.ModelAdmin):
    list_display=('contract','label','document','created_at'); search_fields=('contract__reference','label')
@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display=('contract','amount_due','amount_paid','due_date','paid_date','status','reference'); list_filter=('status','due_date'); search_fields=('reference','contract__reference','contract__property__title')
@admin.register(PaymentProof)
class PaymentProofAdmin(admin.ModelAdmin):
    list_display=('payment','uploaded_by','file','created_at'); search_fields=('payment__contract__reference','uploaded_by__username')
@admin.register(VerificationDocument)
class VerificationDocumentAdmin(admin.ModelAdmin):
    list_display=('user','kind','status','created_at'); list_filter=('kind','status'); search_fields=('user__username','user__first_name','user__last_name','user__email')
@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display=('created_at','actor','action','object_type','object_id','ip_address'); list_filter=('action','object_type','created_at'); search_fields=('actor__username','action','object_type','object_id'); readonly_fields=('created_at',)
@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display=('user','title','read','created_at'); list_filter=('read','created_at'); search_fields=('user__username','title','message')
