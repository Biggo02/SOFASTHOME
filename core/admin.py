from django.contrib import admin
from .models import Property, Visit, Contract, Payment, Notification

admin.site.site_header = 'FASTHOME — Administration'
admin.site.site_title = 'FASTHOME Admin'
admin.site.index_title = 'Centre de gestion immobilière'

@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ('reference','title','owner','city','neighborhood','status','views','updated_at')
    list_filter = ('status','property_type','city','furnished','security')
    search_fields = ('reference','title','city','commune','neighborhood','owner__username','owner__first_name','owner__last_name')
    readonly_fields = ('reference','views','created_at','updated_at')
    list_per_page = 30

@admin.register(Visit)
class VisitAdmin(admin.ModelAdmin):
    list_display = ('id','property','requester','preferred_date','preferred_time','status','created_at')
    list_filter = ('status','preferred_date')
    search_fields = ('property__reference','property__title','requester__username','requester__first_name')

@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ('reference','property','user','role','amount','status','start_date','end_date')
    list_filter = ('status','role')
    search_fields = ('reference','property__reference','property__title','user__username','user__first_name')
    readonly_fields = ('reference','created_at')

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('contract','amount_due','amount_paid','due_date','paid_date','status','reference')
    list_filter = ('status','due_date')
    search_fields = ('reference','contract__reference','contract__property__title')

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user','title','read','created_at')
    list_filter = ('read','created_at')
    search_fields = ('user__username','user__first_name','title','message')
