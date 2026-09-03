from django.db import migrations


def sync_legacy_verification(apps, schema_editor):
    VerificationDocument = apps.get_model('core', 'VerificationDocument')
    VerificationDossier = apps.get_model('core', 'VerificationDossier')

    kinds = ('id_front', 'id_back', 'selfie')
    approved_users = set(
        VerificationDocument.objects
        .filter(kind__in=kinds, status__in=('approved', 'verified'))
        .values_list('user_id', 'kind')
    )

    by_user = {}
    for user_id, kind in approved_users:
        by_user.setdefault(user_id, set()).add(kind)

    for user_id, user_kinds in by_user.items():
        if not set(kinds).issubset(user_kinds):
            continue

        docs = {
            kind: VerificationDocument.objects
            .filter(user_id=user_id, kind=kind, status__in=('approved', 'verified'))
            .order_by('-created_at')
            .first()
            for kind in kinds
        }
        dossier, _ = VerificationDossier.objects.get_or_create(user_id=user_id)
        dossier.status = 'approved'
        if docs['id_front'] and docs['id_front'].file:
            dossier.id_front = docs['id_front'].file.name
        if docs['id_back'] and docs['id_back'].file:
            dossier.id_back = docs['id_back'].file.name
        if docs['selfie'] and docs['selfie'].file:
            dossier.selfie = docs['selfie'].file.name
        dossier.save()


def reverse_sync(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [('core', '0010_verification_dossier')]

    operations = [migrations.RunPython(sync_legacy_verification, reverse_sync)]
