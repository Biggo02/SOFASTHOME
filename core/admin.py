from django.contrib import admin
from .models import Property, PropertyImage, Visit, VisitInspection, Contract, ContractDocument, Payment, PaymentProof, VerificationDocument, AuditLog, Notification

admin.site.site_header='FASTHOME — Administration'; admin.site.site_title='FASTHOME Admin'; admin.site.index_title='Centre de gestion immobilière'

@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display=('reference','title','owner','city','neighborhood','status','views','updated_at'); list_filter=('status','property_type','city','furnished','security'); search_fields=('reference','title','city','commune','neighborhood','owner__username','owner__first_name','owner__last_name'); readonly_fields=('reference','status','views','created_at','updated_at'); list_per_page=30
    def get_queryset(self, request):
        # Les brouillons appartiennent à l'espace du client. L'administration ne traite que les publications soumises.
        return super().get_queryset(request).exclude(status='draft')
    fieldsets=(
        ('Identification',{'fields':('reference','owner','title','property_type','description')}),
        ('Localisation',{'fields':('province','city','commune','neighborhood','full_address','latitude','longitude')}),
        ('Composition et capacité',{'fields':('bedrooms','salons','kitchens','bathrooms','toilets','max_occupants','floors','floor_number','parking','parking_spaces','security')}),
        ('Mobilier et sanitaires',{'fields':('furnished','furnished_type','furniture_details','furnished_bedrooms','furnished_salons','furnished_kitchens','furnished_bathrooms','shower_count','shower_location','shower_privacy','shower_tank_type','bathroom_details','toilet_details')}),
        ('Services',{'fields':('water','water_days_per_week','water_source','water_details','electricity','electricity_days_per_week','electricity_source','electricity_details')}),
        ('État et disponibilité',{'fields':('floor_type','ceiling_type','condition','available_now','availability_date')}),
        ('Finances privées',{'fields':('rent','deposit','margin')}),
        ('Workflow FASTHOME',{'fields':('status','rejection_reason'),'description':'Le statut n’est jamais modifié directement ici. Ouvrez la fiche de gestion pour appliquer uniquement l’action autorisée par l’étape actuelle.'}),
        ('Suivi',{'fields':('views','created_at','updated_at')}),
    )

@admin.register(PropertyImage)
class PropertyImageAdmin(admin.ModelAdmin):
    list_display=('property','image','is_cover','order','created_at'); list_filter=('is_cover',); search_fields=('property__reference','property__title')
@admin.register(Visit)
class VisitAdmin(admin.ModelAdmin):
    list_display=('id','property','requester','preferred_date','preferred_time','scheduled_date','status','owner_approved','agent_approved'); list_filter=('status','owner_approved','agent_approved','preferred_date'); search_fields=('property__reference','property__title','requester__username')
@admin.register(VisitInspection)
class VisitInspectionAdmin(admin.ModelAdmin):
    list_display=('visit','keys_received','signed_by_tenant','signed_by_agent','updated_at'); list_filter=('signed_by_tenant','signed_by_agent')
@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display=('reference','property','user','role','amount','status','start_date','end_date'); list_filter=('status','role'); search_fields=('reference','property__reference','property__title','user__username'); readonly_fields=('reference','created_at')
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
    list_display=('user','kind','status','created_at'); list_filter=('kind','status'); search_fields=('user__username','user__first_name','user__last_name')
@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display=('created_at','actor','action','object_type','object_id','ip_address'); list_filter=('action','object_type','created_at'); search_fields=('actor__username','action','object_type','object_id'); readonly_fields=('created_at',)
@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display=('user','title','read','created_at'); list_filter=('read','created_at'); search_fields=('user__username','title','message')
