from django.contrib import admin
from .models import Property,Visit,Contract,Payment,Notification
admin.site.register([Property,Visit,Contract,Payment,Notification])
