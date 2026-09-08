from django.db import models
from django.contrib.auth.models import User


class RentalCase(models.Model):
    STATUS = [
        ('preparing', 'Dossier à préparer'),
        ('signing', 'Contrats et états des lieux à signer'),
        ('active', 'Location active'),
        ('cancelled', 'Dossier annulé'),
    ]
    reference = models.CharField(max_length=40, unique=True, blank=True)
    visit = models.OneToOneField('core.Visit', on_delete=models.PROTECT, related_name='rental_case')
    property = models.ForeignKey('core.Property', on_delete=models.PROTECT, related_name='rental_cases')
    owner = models.ForeignKey(User, on_delete=models.PROTECT, related_name='owned_rental_cases')
    tenant = models.ForeignKey(User, on_delete=models.PROTECT, related_name='tenant_rental_cases')
    status = models.CharField(max_length=30, choices=STATUS, default='preparing')
    rent_payment_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    rent_payment_date = models.DateField(null=True, blank=True)
    guarantee_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
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
    TYPES = [('owner_agreement', 'FASTHOME ↔ Propriétaire'), ('tenant_sublease', 'FASTHOME ↔ Locataire')]
    STATUS = [('draft', 'Brouillon'), ('prepared', 'Préparé'), ('pending_signature', 'À signer'), ('signed', 'Signé'), ('validated', 'Validé'), ('cancelled', 'Annulé')]
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
        ('owner_inspection', 'État des lieux FASTHOME – Propriétaire'),
        ('tenant_inspection', 'État des lieux FASTHOME – Locataire'),
        ('inspection', 'État des lieux — ancien format'),
        ('payment_proof', 'Preuve de paiement'),
        ('other', 'Autre document'),
    ]
    STATUS = [
        ('required', 'À préparer'),
        ('prepared', 'Préparé'),
        ('pending_review', 'À vérifier'),
        ('validated', 'Signé / vérifié'),
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


class OwnerRemittance(models.Model):
    """Versement effectué par FASTHOME au propriétaire pour un bien loué."""
    rental_case = models.ForeignKey(RentalCase, on_delete=models.PROTECT, related_name='owner_remittances')
    property = models.ForeignKey('core.Property', on_delete=models.PROTECT, related_name='owner_remittances')
    owner = models.ForeignKey(User, on_delete=models.PROTECT, related_name='owner_remittances')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_date = models.DateField()
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    reference = models.CharField(max_length=60, unique=True, blank=True)
    payment_method = models.CharField(max_length=40, blank=True, default='')
    proof = models.FileField(upload_to='owner_remittances/%Y/%m/', blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.reference:
            super().save(*args, **kwargs)
            self.reference = f'FAST-VERS-{self.pk:06d}'
            return super().save(update_fields=['reference'])
        return super().save(*args, **kwargs)
