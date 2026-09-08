from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from .models import Notification
from .rental_models import RentalContract, RentalContractRequest

@login_required
def submit_contract_request(request, pk):
    contract=get_object_or_404(RentalContract.objects.select_related('rental_case','property','party'),pk=pk,contract_type='tenant_sublease')
    if request.user.pk != contract.party_id:
        return HttpResponseForbidden('Cette action est réservée au locataire concerné.')
    if contract.rental_case.status != 'active':
        messages.error(request,'Cette action est disponible uniquement pour une location active.')
        return redirect('rental_contract_detail',pk=pk)
    if request.method != 'POST':
        return redirect('rental_contract_detail',pk=pk)
    request_type=request.POST.get('request_type','').strip()
    description=request.POST.get('description','').strip()
    requested_date=request.POST.get('requested_date','').strip() or None
    if request_type not in {'problem','notice'} or not description:
        messages.error(request,'Veuillez préciser le type de demande et fournir une description.')
        return redirect('rental_contract_detail',pk=pk)
    if request_type == 'notice' and not requested_date:
        messages.error(request,'Veuillez indiquer la date souhaitée de départ avec préavis.')
        return redirect('rental_contract_detail',pk=pk)
    obj=RentalContractRequest.objects.create(contract=contract,rental_case=contract.rental_case,requester=request.user,request_type=request_type,description=description,requested_date=requested_date)
    label='Signalement de problème' if request_type=='problem' else 'Demande de départ avec préavis'
    Notification.objects.create(user=request.user,title='Demande enregistrée',message=f'{label} enregistrée sous la référence #{obj.pk}. FASTHOME va traiter votre demande.')
    for staff in __import__('django.contrib.auth',fromlist=['get_user_model']).get_user_model().objects.filter(is_staff=True,is_active=True):
        Notification.objects.create(user=staff,title=label,message=f'Demande #{obj.pk} pour le contrat {contract.reference}, logement {contract.property.title}.')
    messages.success(request,f'{label} enregistrée auprès de FASTHOME.')
    return redirect('rental_contract_detail',pk=pk)
