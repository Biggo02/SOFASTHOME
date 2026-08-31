from django.contrib import admin
from django.urls import path
from core import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.home, name='home'),
    path('rechercher/', views.search, name='search'),
    path('bien/<int:pk>/', views.property_detail, name='property_detail'),
    path('inscription/', views.register, name='register'),
    path('connexion/', views.login_view, name='login'),
    path('deconnexion/', views.logout_view, name='logout'),
    path('espace-personnel/', views.dashboard, name='dashboard'),
    path('mes-publications/', views.publications, name='publications'),
    path('ajouter-un-bien/', views.add_property, name='add_property'),
    path('mes-visites/', views.visits, name='visits'),
    path('mes-contrats/', views.contracts, name='contracts'),
    path('mes-paiements/', views.payments, name='payments'),
    path('mes-echeances/', views.due_dates, name='due_dates'),
    path('notifications/', views.notifications, name='notifications'),
    path('messages/', views.messages_page, name='messages'),
    path('a-propos/', views.about, name='about'),
    path('comment-ca-marche/', views.how_it_works, name='how_it_works'),
    path('contact/', views.contact, name='contact'),
    path('verification-contrat/<str:reference>/', views.contract_verify, name='contract_verify'),
    path('404/', views.error_404, name='error_404'),
]
