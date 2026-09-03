from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from core import views
from core import search_views
from core import contract_views
from core import how_it_works_views
from core import about_views
from core import contact_views

urlpatterns = [
    path('admin/', admin.site.urls), path('', views.home, name='home'), path('rechercher/', search_views.search, name='search'),
    path('bien/<int:pk>/', search_views.property_detail, name='property_detail'), path('bien/<int:pk>/visite/', views.request_visit, name='request_visit'),
    path('bien/<int:pk>/favori/', views.toggle_favorite, name='toggle_favorite'), path('bien/<int:pk>/photos/', views.upload_property_images, name='upload_property_images'),
    path('inscription/', views.register, name='register'), path('connexion/', views.login_view, name='login'), path('deconnexion/', views.logout_view, name='logout'),
    path('mot-de-passe-oublie/', auth_views.PasswordResetView.as_view(template_name='password_reset.html'), name='password_reset'),
    path('mot-de-passe-oublie/envoye/', auth_views.PasswordResetDoneView.as_view(template_name='password_reset_done.html'), name='password_reset_done'),
    path('reinitialisation/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='password_reset_confirm.html'), name='password_reset_confirm'),
    path('reinitialisation/terminee/', auth_views.PasswordResetCompleteView.as_view(template_name='password_reset_complete.html'), name='password_reset_complete'),
    path('espace-personnel/', views.dashboard, name='dashboard'), path('mon-profil/', views.profile, name='profile'), path('mes-favoris/', views.favorites, name='favorites'),
    path('mes-publications/', views.publications, name='publications'), path('ajouter-un-bien/', views.add_property, name='add_property'), path('mes-visites/', views.visits, name='visits'),
    path('mes-contrats/', views.contracts, name='contracts'), path('mes-paiements/', views.payments, name='payments'), path('paiement/<int:pk>/preuve/', views.payment_proof, name='payment_proof'),
    path('mes-echeances/', views.due_dates, name='due_dates'), path('notifications/', views.notifications, name='notifications'), path('messages/', views.messages_page, name='messages'),
    path('verification-documents/', views.verification_upload, name='verification_upload'), path('contrat/<str:reference>/pdf/', contract_views.contract_pdf, name='contract_pdf'),
    path('a-propos/', about_views.about, name='about'), path('comment-ca-marche/', how_it_works_views.how_it_works, name='how_it_works'), path('contact/', contact_views.contact, name='contact'),
    path('verification-contrat/<str:reference>/', views.contract_verify, name='contract_verify'), path('gestion/', views.admin_dashboard, name='admin_dashboard'),
    path('gestion/publication/<int:pk>/', views.review_publication, name='review_publication'), path('gestion/visite/<int:pk>/', views.manage_visit, name='manage_visit'),
    path('gestion/visite/<int:pk>/etat-des-lieux/', views.inspection, name='inspection'),
]
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT) if settings.DEBUG else []
handler403 = 'core.views.error_403'; handler404 = 'core.views.error_404'; handler500 = 'core.views.error_500'
