from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.contrib.auth.models import User

from .models import Property, Visit, Payment, PaymentProof, VerificationDossier
from .rental_models import RentalCase, RentalContract, RentalDocument, OwnerRemittance, RentalPayment, RentalContractRequest
from .notification_service import notify_once, notify_staff_once


def _status_label(obj, value):
    choices = getattr(obj, 'STATUS', [])
    return dict(choices).get(value, value)


def _notify_party_and_staff(title, message, party=None):
    if party:
        notify_once(party, title, message)
    notify_staff_once(title, message)


@receiver(post_save, sender=User)
def account_notifications(sender, instance, created, **kwargs):
    if created and not instance.is_staff:
        notify_staff_once('Nouveau compte', f'Un nouveau compte utilisateur a été créé : {instance.get_full_name() or instance.username}.')


@receiver(pre_save, sender=Property)
def property_before_save(sender, instance, **kwargs):
    instance._old_status = sender.objects.filter(pk=instance.pk).values_list('status', flat=True).first() if instance.pk else None


@receiver(post_save, sender=Property)
def property_notifications(sender, instance, created, **kwargs):
    if created:
        if instance.status == 'review':
            _notify_party_and_staff('Publication à vérifier', f'{instance.reference} — {instance.title} a été soumise à vérification.', instance.owner)
        return
    old = getattr(instance, '_old_status', None)
    if old == instance.status:
        return
    if instance.status == 'review':
        _notify_party_and_staff('Publication à vérifier', f'{instance.reference} — {instance.title} a été soumise à vérification.', instance.owner)
    elif instance.status == 'published':
        notify_once(instance.owner, 'Publication validée', f'{instance.reference} — {instance.title} est maintenant publiée.')
    elif instance.status == 'rejected':
        notify_once(instance.owner, 'Publication à corriger', f'{instance.reference} — {instance.title} a été refusée. Consultez le motif et corrigez la publication.')
    elif instance.status == 'rented':
        notify_once(instance.owner, 'Bien loué', f'{instance.reference} — {instance.title} est passé au statut loué.')
    elif instance.status == 'archived':
        notify_once(instance.owner, 'Bien archivé', f'{instance.reference} — {instance.title} a été archivé.')


@receiver(post_save, sender=Visit)
def visit_created_notifications(sender, instance, created, **kwargs):
    if not created:
        return
    notify_staff_once('Nouvelle demande de visite', f'Demande #{instance.pk} pour {instance.property.reference} — action FASTHOME requise.')


@receiver(pre_save, sender=Visit)
def visit_before_save(sender, instance, **kwargs):
    if not instance.pk:
        instance._old_status = None
        instance._old_scheduled = None
        instance._old_agent_id = None
        return
    old = sender.objects.filter(pk=instance.pk).values('status', 'scheduled_date', 'scheduled_time', 'agent_id').first()
    instance._old_status = old['status'] if old else None
    instance._old_scheduled = (old['scheduled_date'], old['scheduled_time']) if old else None
    instance._old_agent_id = old['agent_id'] if old else None


@receiver(post_save, sender=Visit)
def visit_changed_notifications(sender, instance, created, **kwargs):
    if created:
        return
    old_status = getattr(instance, '_old_status', None)
    old_scheduled = getattr(instance, '_old_scheduled', None)
    old_agent_id = getattr(instance, '_old_agent_id', None)
    if old_status != instance.status:
        if instance.status == 'confirmed':
            notify_once(instance.requester, 'Demande de visite validée', 'Votre demande de visite est validée.')
        elif instance.status == 'rejected':
            notify_once(instance.requester, 'Demande de visite refusée', 'Votre demande de visite n’a pas été acceptée.')
        elif instance.status == 'done':
            notify_once(instance.requester, 'Visite effectuée', 'Votre visite a été effectuée.')
        elif instance.status == 'cancelled':
            notify_once(instance.requester, 'Visite annulée', f'Votre visite pour {instance.property.reference} a été annulée.')
    scheduled = (instance.scheduled_date, instance.scheduled_time)
    if old_scheduled != scheduled and instance.scheduled_date and instance.requester:
        when = f'{instance.scheduled_date:%d/%m/%Y}'
        if instance.scheduled_time:
            when += f' à {instance.scheduled_time:%H:%M}'
        notify_once(instance.requester, 'Horaire de visite mis à jour', f'Votre visite pour {instance.property.reference} est prévue le {when}.')
    if instance.agent_id and instance.agent_id != old_agent_id:
        notify_once(instance.agent, 'Visite assignée', f'La visite #{instance.pk} pour {instance.property.reference} vous a été assignée.')
        notify_staff_once('Agent affecté à une visite', f'La visite #{instance.pk} pour {instance.property.reference} a été affectée à un agent.')


@receiver(pre_save, sender=Payment)
def payment_before_save(sender, instance, **kwargs):
    if not instance.pk:
        instance._old_status = None
        instance._old_amount_paid = None
        return
    old = sender.objects.filter(pk=instance.pk).values('status', 'amount_paid').first()
    instance._old_status = old['status'] if old else None
    instance._old_amount_paid = old['amount_paid'] if old else None


@receiver(post_save, sender=Payment)
def payment_notifications(sender, instance, created, **kwargs):
    if created:
        return
    old_status = getattr(instance, '_old_status', None)
    old_paid = getattr(instance, '_old_amount_paid', None)
    user = getattr(instance.contract, 'user', None)
    if old_status != instance.status:
        label = _status_label(instance, instance.status)
        notify_once(user, 'Statut de paiement mis à jour', f'Votre paiement {instance.reference or ""} est maintenant « {label} ».')
        notify_staff_once('Statut de paiement mis à jour', f'Paiement #{instance.pk} — contrat {instance.contract.pk} : « {label} ».')
    if old_paid != instance.amount_paid and instance.amount_paid:
        notify_once(user, 'Paiement mis à jour', f'Le montant payé pour l’échéance #{instance.pk} est maintenant de {instance.amount_paid:,.2f} CDF.')


@receiver(post_save, sender=PaymentProof)
def payment_proof_notifications(sender, instance, created, **kwargs):
    if not created:
        return
    tenant = getattr(instance.payment.contract, 'user', None)
    notify_staff_once('Justificatif de paiement reçu', f'Le justificatif du paiement #{instance.payment.pk} a été déposé et doit être vérifié.')
    if tenant:
        notify_once(tenant, 'Justificatif reçu', f'Votre justificatif pour le paiement #{instance.payment.pk} a bien été transmis à FASTHOME.')


@receiver(pre_save, sender=VerificationDossier)
def verification_before_save(sender, instance, **kwargs):
    instance._old_status = sender.objects.filter(pk=instance.pk).values_list('status', flat=True).first() if instance.pk else None


@receiver(post_save, sender=VerificationDossier)
def verification_notifications(sender, instance, created, **kwargs):
    if created:
        return
    old = getattr(instance, '_old_status', None)
    if old == instance.status:
        return
    if instance.status == 'pending':
        notify_staff_once('Dossier d’identité à vérifier', f'Le dossier de vérification de {instance.user.get_full_name() or instance.user.username} est à traiter.')
    elif instance.status == 'approved':
        notify_once(instance.user, 'Identité validée', 'Votre identité a été validée par FASTHOME. Vous pouvez maintenant accéder aux actions nécessitant une vérification.')
    elif instance.status == 'rejected':
        notify_once(instance.user, 'Vérification refusée', f'Votre vérification a été refusée. {instance.note}'.strip())
    elif instance.status == 'needs_info':
        notify_once(instance.user, 'Informations supplémentaires requises', f'FASTHOME demande des informations supplémentaires pour votre vérification. {instance.note}'.strip())


@receiver(pre_save, sender=RentalCase)
def rental_case_before_save(sender, instance, **kwargs):
    instance._old_status = sender.objects.filter(pk=instance.pk).values_list('status', flat=True).first() if instance.pk else None


@receiver(post_save, sender=RentalCase)
def rental_case_notifications(sender, instance, created, **kwargs):
    if created:
        notify_staff_once('Nouveau dossier de location', f'{instance.reference} — dossier créé pour {instance.property.reference}.')
        return
    old = getattr(instance, '_old_status', None)
    if old == instance.status:
        return
    label = _status_label(instance, instance.status)
    msg = f'Le dossier {instance.reference} est maintenant « {label} ». Bien : {instance.property.reference}.'
    notify_once(instance.owner, 'Dossier de location mis à jour', msg)
    notify_once(instance.tenant, 'Dossier de location mis à jour', msg)
    notify_staff_once('Dossier de location mis à jour', msg)


@receiver(pre_save, sender=RentalContract)
def rental_contract_before_save(sender, instance, **kwargs):
    instance._old_status = sender.objects.filter(pk=instance.pk).values_list('status', flat=True).first() if instance.pk else None


@receiver(post_save, sender=RentalContract)
def rental_contract_notifications(sender, instance, created, **kwargs):
    if created:
        return
    old = getattr(instance, '_old_status', None)
    if old == instance.status:
        return
    label = _status_label(instance, instance.status)
    notify_once(instance.party, 'Statut du contrat mis à jour', f'Votre contrat {instance.reference} est maintenant « {label} ».')
    notify_staff_once('Statut du contrat mis à jour', f'{instance.reference} — « {label} » pour {instance.property.reference}.')


@receiver(pre_save, sender=RentalDocument)
def rental_document_before_save(sender, instance, **kwargs):
    instance._old_status = sender.objects.filter(pk=instance.pk).values_list('status', flat=True).first() if instance.pk else None


@receiver(post_save, sender=RentalDocument)
def rental_document_notifications(sender, instance, created, **kwargs):
    old = getattr(instance, '_old_status', None)
    if created and instance.status not in {'prepared', 'pending_review', 'validated', 'rejected'}:
        return
    if old == instance.status and not created:
        return
    case = instance.rental_case
    party = case.owner if instance.document_type.startswith('owner_') else case.tenant if instance.document_type.startswith('tenant_') else None
    if instance.status == 'prepared' and party:
        notify_once(party, 'Document préparé', f'{instance.label} a été préparé par FASTHOME pour le dossier {case.reference}.')
    elif instance.status == 'pending_review':
        notify_staff_once('Document signé à vérifier', f'{instance.label} — dossier {case.reference} nécessite une vérification FASTHOME.')
    elif instance.status == 'validated':
        if party:
            notify_once(party, 'Document vérifié', f'{instance.label} a été vérifié par FASTHOME et est disponible dans votre dossier.')
        notify_staff_once('Document vérifié', f'{instance.label} — dossier {case.reference}.')
    elif instance.status == 'rejected':
        if party:
            notify_once(party, 'Document à corriger', f'{instance.label} du dossier {case.reference} nécessite une correction.')
        notify_staff_once('Document à corriger', f'{instance.label} — dossier {case.reference}.')


@receiver(pre_save, sender=OwnerRemittance)
def owner_remittance_before_save(sender, instance, **kwargs):
    if not instance.pk:
        instance._old_amount = None
        instance._old_date = None
        return
    old = sender.objects.filter(pk=instance.pk).values('amount', 'payment_date').first()
    instance._old_amount = old['amount'] if old else None
    instance._old_date = old['payment_date'] if old else None


@receiver(post_save, sender=OwnerRemittance)
def owner_remittance_notifications(sender, instance, created, **kwargs):
    if created:
        notify_once(instance.owner, 'Versement FASTHOME enregistré', f'{instance.amount:,.2f} CDF ont été enregistrés comme versement FASTHOME pour {instance.property.reference}. Référence {instance.reference}.')
        notify_staff_once('Versement propriétaire enregistré', f'{instance.reference} — {instance.amount:,.2f} CDF versés pour {instance.property.reference}.')
        return
    if getattr(instance, '_old_amount', None) != instance.amount or getattr(instance, '_old_date', None) != instance.payment_date:
        notify_once(instance.owner, 'Versement FASTHOME modifié', f'Le versement {instance.reference} a été mis à jour dans votre relevé.')
        notify_staff_once('Versement propriétaire modifié', f'{instance.reference} — dossier {instance.rental_case.reference}.')


@receiver(pre_save, sender=RentalPayment)
def rental_payment_before_save(sender, instance, **kwargs):
    if not instance.pk:
        instance._old_amount = None
        instance._old_date = None
        return
    old = sender.objects.filter(pk=instance.pk).values('amount', 'payment_date').first()
    instance._old_amount = old['amount'] if old else None
    instance._old_date = old['payment_date'] if old else None


@receiver(post_save, sender=RentalPayment)
def rental_payment_notifications(sender, instance, created, **kwargs):
    if created:
        notify_once(instance.tenant, 'Paiement enregistré', f'{instance.get_payment_type_display()} de {instance.amount:,.2f} CDF enregistré pour le contrat {instance.contract.reference}. Référence {instance.reference}.')
        notify_staff_once('Paiement locataire enregistré', f'{instance.reference} — {instance.amount:,.2f} CDF — contrat {instance.contract.reference}.')
        return
    if getattr(instance, '_old_amount', None) != instance.amount or getattr(instance, '_old_date', None) != instance.payment_date:
        notify_once(instance.tenant, 'Paiement modifié', f'Le paiement {instance.reference} de votre contrat {instance.contract.reference} a été mis à jour.')
        notify_staff_once('Paiement locataire modifié', f'{instance.reference} — contrat {instance.contract.reference}.')


@receiver(pre_save, sender=RentalContractRequest)
def rental_request_before_save(sender, instance, **kwargs):
    if not instance.pk:
        instance._old_status = None
        instance._old_response = ''
        return
    old = sender.objects.filter(pk=instance.pk).values('status', 'response').first()
    instance._old_status = old['status'] if old else None
    instance._old_response = old['response'] if old else ''


@receiver(post_save, sender=RentalContractRequest)
def rental_request_notifications(sender, instance, created, **kwargs):
    if created:
        kind = 'Signalement de problème' if instance.request_type == 'problem' else 'Demande de fin de contrat'
        notify_once(instance.requester, f'{kind} envoyée', f'Votre demande a été enregistrée pour le contrat {instance.contract.reference} et transmise à FASTHOME.')
        notify_staff_once(f'{kind} à traiter', f'{instance.contract.reference} — dossier {instance.rental_case.reference}. Une action FASTHOME est requise.')
        return
    old_status = getattr(instance, '_old_status', None)
    old_response = getattr(instance, '_old_response', '')
    if old_status != instance.status:
        label = _status_label(instance, instance.status)
        notify_once(instance.requester, 'Demande de contrat mise à jour', f'Votre demande pour le contrat {instance.contract.reference} est maintenant « {label} ».')
        notify_staff_once('Demande de contrat mise à jour', f'{instance.contract.reference} — demande #{instance.pk} : « {label} ».')
    if old_response != instance.response and instance.response:
        notify_once(instance.requester, 'Réponse FASTHOME disponible', f'FASTHOME a répondu à votre demande concernant le contrat {instance.contract.reference}. Consultez votre espace personnel.')
