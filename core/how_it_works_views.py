from django.shortcuts import render


def how_it_works(request):
    return render(request, 'how_it_works.html')
