from io import BytesIO

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .models import Contract


@login_required
def contract_pdf(request, reference):
    contract = get_object_or_404(
        Contract.objects.select_related('property', 'user'),
        reference=reference,
    )
    if contract.user != request.user and not request.user.is_staff:
        return render(request, '403.html', status=403)

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        import qrcode

        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        c.setTitle(f'FASTHOME {contract.reference}')
        c.setFont('Helvetica-Bold', 20)
        c.drawString(50, height - 60, 'FASTHOME — CONTRAT LOCATIF')
        c.setFont('Helvetica', 11)
        y = height - 100
        lines = [
            f'Référence : {contract.reference}',
            f'Bien : {contract.property.title} ({contract.property.reference})',
            f'Localisation : {contract.property.commune} — {contract.property.city} — {contract.property.province}',
            f'Partie : {contract.user.get_full_name() or contract.user.username}',
            f'Rôle : {contract.get_role_display()}',
            f'Montant : {contract.amount} USD',
            f'Début : {contract.start_date or "—"}',
            f'Fin : {contract.end_date or "—"}',
            f'Statut : {contract.status}',
        ]
        for line in lines:
            c.drawString(50, y, line)
            y -= 22

        qr = qrcode.make(f'FASTHOME|{contract.reference}')
        qpath = BytesIO()
        qr.save(qpath, format='PNG')
        qpath.seek(0)
        from reportlab.lib.utils import ImageReader
        c.drawImage(ImageReader(qpath), width - 150, 100, width=90, height=90)
        c.drawString(width - 155, 85, 'Vérification contrat')
        c.setFont('Helvetica', 9)
        c.drawString(50, 50, 'Document généré par FASTHOME. Vérification : référence du contrat.')
        c.showPage()
        c.save()
        buffer.seek(0)
        return HttpResponse(
            buffer.getvalue(),
            content_type='application/pdf',
            headers={'Content-Disposition': f'inline; filename="{contract.reference}.pdf"'},
        )
    except ImportError:
        from django.contrib import messages
        messages.error(request, 'Le module PDF n’est pas installé sur cet environnement.')
        return redirect('contracts')
