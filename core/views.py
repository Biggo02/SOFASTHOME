from django.contrib import messages
from django.contrib.auth import authenticate,login,logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q
from django.shortcuts import get_object_or_404,redirect,render
from .forms import RegisterForm,PropertyForm
from .models import Property,Visit,Contract,Payment,Notification

def home(request):
    properties=Property.objects.filter(status='published').order_by('-created_at')[:8]
    return render(request,'home.html',{'properties':properties})

def search(request):
    qs=Property.objects.filter(status='published')
    q=request.GET.get('q','').strip()
    ptype=request.GET.get('type','')
    if q: qs=qs.filter(Q(title__icontains=q)|Q(city__icontains=q)|Q(commune__icontains=q)|Q(neighborhood__icontains=q))
    if ptype: qs=qs.filter(property_type=ptype)
    return render(request,'search.html',{'properties':qs,'q':q,'types':Property.TYPES})

def property_detail(request,pk):
    prop=get_object_or_404(Property,pk=pk,status='published'); prop.views+=1; prop.save(update_fields=['views'])
    return render(request,'property_detail.html',{'property':prop})

def register(request):
    form=RegisterForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        user=form.save(commit=False); user.set_password(form.cleaned_data['password']); user.save(); login(request,user); return redirect('dashboard')
    return render(request,'auth.html',{'form':form,'mode':'register'})

def login_view(request):
    if request.user.is_authenticated: return redirect('dashboard')
    if request.method=='POST':
        username=request.POST.get('username',''); password=request.POST.get('password','')
        user=authenticate(request,username=username,password=password)
        if user: login(request,user); return redirect('dashboard')
        messages.error(request,'Identifiants incorrects.')
    return render(request,'auth.html',{'mode':'login'})

def logout_view(request): logout(request); return redirect('home')

@login_required
def dashboard(request):
    user=request.user
    return render(request,'dashboard.html',{'properties':Property.objects.filter(owner=user),'visits':Visit.objects.filter(requester=user).order_by('-created_at')[:5],'contracts':Contract.objects.filter(user=user),'payments':Payment.objects.filter(contract__user=user).order_by('due_date')[:5],'notifications':Notification.objects.filter(user=user).order_by('-created_at')[:5]})

@login_required
def publications(request):
    return render(request,'list.html',{'title':'Mes publications','items':Property.objects.filter(owner=request.user),'kind':'property'})

@login_required
def add_property(request):
    form=PropertyForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        obj=form.save(commit=False); obj.owner=request.user; obj.status='review' if 'submit' in request.POST else 'draft'; obj.save(); messages.success(request,'Votre publication a été enregistrée.'); return redirect('publications')
    return render(request,'property_form.html',{'form':form})

@login_required
def visits(request):
    return render(request,'list.html',{'title':'Mes demandes de visite','items':Visit.objects.filter(requester=request.user).select_related('property').order_by('-created_at'),'kind':'visit'})

@login_required
def contracts(request):
    return render(request,'list.html',{'title':'Mes contrats','items':Contract.objects.filter(user=request.user).select_related('property'),'kind':'contract'})

@login_required
def payments(request):
    return render(request,'list.html',{'title':'Mes paiements','items':Payment.objects.filter(contract__user=request.user).select_related('contract__property').order_by('due_date'),'kind':'payment'})

@login_required
def due_dates(request):
    return render(request,'list.html',{'title':'Mes échéances','items':Payment.objects.filter(contract__user=request.user).select_related('contract__property').order_by('due_date'),'kind':'due'})

@login_required
def notifications(request):
    return render(request,'list.html',{'title':'Notifications','items':Notification.objects.filter(user=request.user).order_by('-created_at'),'kind':'notification'})

@login_required
def messages_page(request):
    return render(request,'placeholder.html',{'title':'Messagerie','text':'Votre messagerie FASTHOME est prête pour les échanges sécurisés avec l’agence.'})

def about(request): return render(request,'placeholder.html',{'title':'À propos','text':'FASTHOME simplifie la recherche, la visite et la gestion locative en RDC.'})
def how_it_works(request): return render(request,'placeholder.html',{'title':'Comment ça marche ?','text':'Recherchez, comparez, demandez une visite, signez et suivez votre location depuis un seul compte.'})
def contact(request): return render(request,'placeholder.html',{'title':'Contact','text':'L’équipe FASTHOME vous accompagne à chaque étape.'})

def contract_verify(request,reference):
    contract=get_object_or_404(Contract,reference=reference)
    return render(request,'verify.html',{'contract':contract})
def error_404(request): return render(request,'404.html',status=404)
