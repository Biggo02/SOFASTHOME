from django.contrib import admin
from .models import Property, PropertyImage, Visit, VisitInspection, Contract, ContractDocument, Payment, PaymentProof, VerificationDocument, AuditLog, Notification

admin.site.site_header='FASTHOME — Administration'; admin.site.site_title='FASTHOME Admin'; admin.site.index_title='Centre de gestion immobilière'

@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display=('reference','title','owner','city','neighborhood','status','views','updated_at'); list_filter=('status','property_type','city','furnished','security'); search_fields=('reference','title','city','commune','neighborhood','owner__username','owner__first_name','owner__last_name'); readonly_fields=('reference','views','created_at','updated_at'); list_per_page=30
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
