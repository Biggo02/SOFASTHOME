from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from .models import Property, PropertyImage, Visit, VisitInspection, Contract, ContractDocument, Payment, PaymentProof, VerificationDocument, VerificationDossier, AuditLog, Notification
from .rental_models import RentalCase, RentalContract, RentalDocument, OwnerRemittance, RentalPayment, RentalContractRequest
admin.site.site_header='FASTHOME — Administration'; admin.site.site_title='FASTHOME Admin'; admin.site.index_title='Centre de gestion immobilière'
# Existing admin registrations are kept; rental operational records below are exposed for FASTHOME staff.
for model in (Property,PropertyImage,Visit,VisitInspection,Contract,ContractDocument,Payment,PaymentProof,VerificationDocument,VerificationDossier,AuditLog,Notification):
    try: admin.site.unregister(model)
    except admin.sites.NotRegistered: pass
@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display=('reference','title','owner','city','commune','status','updated_at'); list_filter=('status','property_type','city','commune'); search_fields=('reference','title','province','city','commune','owner__username','owner__first_name','owner__last_name')
@admin.register(PropertyImage)
class PropertyImageAdmin(admin.ModelAdmin): list_display=('property','image','is_cover','order','created_at')
@admin.register(Visit)
class VisitAdmin(admin.ModelAdmin): list_display=('id','property','requester','preferred_date','preferred_time','scheduled_date','status','final_decision'); list_filter=('status','final_decision')
@admin.register(VisitInspection)
class VisitInspectionAdmin(admin.ModelAdmin): list_display=('visit','keys_received','signed_by_tenant','signed_by_agent','updated_at')
@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin): list_display=('reference','property','user','role','amount','status','start_date','end_date'); search_fields=('reference','property__reference','user__username')
@admin.register(ContractDocument)
class ContractDocumentAdmin(admin.ModelAdmin): list_display=('contract','label','document','created_at')
@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin): list_display=('contract','amount_due','amount_paid','due_date','paid_date','status','reference')
@admin.register(PaymentProof)
class PaymentProofAdmin(admin.ModelAdmin): list_display=('payment','uploaded_by','file','created_at')
@admin.register(VerificationDocument)
class VerificationDocumentAdmin(admin.ModelAdmin): list_display=('user','kind','status','created_at'); list_filter=('kind','status')
@admin.register(VerificationDossier)
class VerificationDossierAdmin(admin.ModelAdmin): list_display=('user','status','created_at','updated_at'); list_filter=('status',)
@admin.register(RentalCase)
class RentalCaseAdmin(admin.ModelAdmin): list_display=('reference','property','tenant','owner','status','created_at'); list_filter=('status',); search_fields=('reference','property__reference','tenant__username','owner__username'); readonly_fields=('reference','created_at','updated_at')
@admin.register(RentalContract)
class RentalContractAdmin(admin.ModelAdmin): list_display=('reference','rental_case','contract_type','party','amount','deposit','status','start_date','end_date'); list_filter=('contract_type','status'); search_fields=('reference','rental_case__reference','party__username'); readonly_fields=('reference','created_at','updated_at')
@admin.register(RentalDocument)
class RentalDocumentAdmin(admin.ModelAdmin): list_display=('rental_case','document_type','label','status','file','updated_at'); list_filter=('document_type','status')
@admin.register(OwnerRemittance)
class OwnerRemittanceAdmin(admin.ModelAdmin): list_display=('reference','property','owner','amount','payment_date','period_start','period_end','payment_method'); list_filter=('payment_date','payment_method'); search_fields=('reference','property__reference','owner__username'); readonly_fields=('reference','created_at','updated_at')
@admin.register(RentalPayment)
class RentalPaymentAdmin(admin.ModelAdmin): list_display=('reference','rental_case','contract','tenant','payment_type','amount','payment_date','payment_method'); list_filter=('payment_type','payment_date','payment_method'); search_fields=('reference','rental_case__reference','contract__reference','tenant__username'); readonly_fields=('reference','created_at','updated_at')
@admin.register(RentalContractRequest)
class RentalContractRequestAdmin(admin.ModelAdmin):
    list_display=('id','request_type','contract','requester','requested_date','status','created_at')
    list_filter=('request_type','status','created_at')
    search_fields=('contract__reference','rental_case__reference','requester__username','requester__first_name','requester__last_name','description')
    readonly_fields=('created_at','updated_at')
    fieldsets=(('Demande',{'fields':('contract','rental_case','requester','request_type','description','requested_date')}),('Traitement FASTHOME',{'fields':('status','response')}),('Suivi',{'fields':('created_at','updated_at')}))
@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin): list_display=('created_at','actor','action','object_type','object_id','ip_address'); list_filter=('action','object_type')
@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin): list_display=('user','title','read','created_at'); list_filter=('read','created_at'); search_fields=('user__username','title','message')
