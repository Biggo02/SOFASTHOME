from django.db import models
from django.contrib.auth.models import User


class RentalCase(models.Model):
    STATUS = [
        ('preparing', 'Dossier à préparer'),
        ('owner_contract', 'Contrat propriétaire à valider'),
        ('tenant_contract', 'Contrat locataire à valider'),
        ('signing', 'En attente des signatures'),
        ('payment', 'En attente du paiement'),
        ('inspection', 'État des lieux'),
        ('active', 'Location active'),
        ('cancelled', 'Dossier annulé'),
    ]

    reference = models.CharField(max_length=40, unique=True, blank=True)
    visit = models.OneToOneField('core.Visit', on_delete=models.PROTECT, related_name='rental_case')
    property = models.ForeignKey('core.Property', on_delete=models.PROTECT, related_name='rental_cases')
    owner = models.ForeignKey(User, on_delete=models.PROTECT, related_name='owned_rental_cases')
    tenant = models.ForeignKey(User, on_delete=models.PROTECT, related_name='tenant_rental_cases')
    status = models.CharField(max_length=30, choices=STATUS, default='preparing')
    owner_contract = models.OneToOneField('core.RentalContract', on_delete=models.SET_NULL, null=True, blank=True, related_name='owner_case')
    tenant_contract = models.OneToOneField('core.RentalContract', on_delete=models.SET_NULL, null=True, blank=True, related_name='tenant_case')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.reference:
            super().save(*args, **kwargs)
            self.reference = f'FAST-DOS-{self.pk:06d}'
            return super().save(update_fields=['reference'])
        return super().save(*args, **kwargs)


class RentalContract(models.Model):
    TYPES = [
        ('owner_agreement', 'FASTHOME ↔ Propriétaire'),
        ('tenant_sublease', 'FASTHOME ↔ Locataire'),
    ]
    STATUS = [
        ('draft', 'Brouillon'),
        ('prepared', 'Préparé'),
        ('pending_signature', 'À signer'),
        ('signed', 'Signé'),
        ('validated', 'Validé'),
        ('cancelled', 'Annulé'),
    ]

    reference = models.CharField(max_length=40, unique=True, blank=True)
    rental_case = models.ForeignKey(RentalCase, on_delete=models.CASCADE, related_name='contracts')
    property = models.ForeignKey('core.Property', on_delete=models.PROTECT, related_name='rental_contracts')
    contract_type = models.CharField(max_length=30, choices=TYPES)
    party = models.ForeignKey(User, on_delete=models.PROTECT, related_name='rental_contracts')
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    deposit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=30, choices=STATUS, default='draft')
    signed_at = models.DateTimeField(null=True, blank=True)
    validated_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.reference:
            super().save(*args, **kwargs)
            prefix = 'PRO' if self.contract_type == 'owner_agreement' else 'LOC'
            self.reference = f'FAST-{prefix}-{self.pk:06d}'
            return super().save(update_fields=['reference'])
        return super().save(*args, **kwargs)


class RentalDocument(models.Model):
    TYPES = [
        ('identity', 'Pièce d’identité'),
        ('owner_contract', 'Contrat FASTHOME – Propriétaire'),
        ('tenant_contract', 'Contrat FASTHOME – Locataire'),
        ('inspection', 'État des lieux'),
        ('payment_proof', 'Preuve de paiement'),
        ('other', 'Autre document'),
    ]
    STATUS = [
        ('required', 'À préparer'),
        ('prepared', 'Préparé'),
        ('validated', 'Validé'),
        ('rejected', 'À corriger'),
    ]

    rental_case = models.ForeignKey(RentalCase, on_delete=models.CASCADE, related_name='documents')
    document_type = models.CharField(max_length=30, choices=TYPES)
    label = models.CharField(max_length=180)
    file = models.FileField(upload_to='rental/%Y/%m/', blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default='required')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
