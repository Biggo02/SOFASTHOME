from django.shortcuts import render


def contact(request):
    return render(request, 'contact.html', {
        'phone': '0995562693',
        'phone_international': '+243995562693',
        'email': 'elitentambwe01@gmail.com',
        'whatsapp_number': '243995562693',
        'whatsapp_message': "Bonjour FASTHOME, je souhaite obtenir des informations concernant vos services.",
    })
