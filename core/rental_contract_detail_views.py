from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from .rental_models import RentalContract, RentalPayment, OwnerRemittance, RentalContractRequest

@login_required
def rental_contract_detail(request, pk):
    contract = get_object_or_404(RentalContract.objects.select_related('rental_case','rental_case__visit','property','party'), pk=pk)
    if request.user.pk != contract.party_id and not request.user.is_staff:
        return HttpResponseForbidden('Ce contrat ne vous est pas destiné.')
    case=contract.rental_case; is_owner_contract=contract.contract_type=='owner_agreement'
    allowed={'owner_contract','owner_inspection'} if is_owner_contract else {'tenant_contract','tenant_inspection'}
    documents=list(case.documents.filter(document_type__in=allowed).order_by('document_type','-updated_at'))
    validated_documents=sum(1 for doc in documents if doc.status=='validated' and bool(doc.file))
    remittances=[]; total_remitted=0; tenant_payments=[]; total_paid=0; contract_requests=[]
    if is_owner_contract:
        remittances=list(OwnerRemittance.objects.filter(rental_case=case,property=contract.property,owner=request.user).order_by('payment_date','id'))
        total_remitted=sum((x.amount or 0) for x in remittances)
    else:
        tenant_payments=list(RentalPayment.objects.filter(contract=contract,rental_case=case,tenant=request.user).order_by('payment_date','id'))
        if not tenant_payments and case.rent_payment_date and case.rent_payment_amount:
            tenant_payments=[{'payment_type':'rent','payment_date':case.rent_payment_date,'reference':'Dossier '+case.reference,'amount':case.rent_payment_amount,'payment_method':''}]
            if case.guarantee_amount: tenant_payments.append({'payment_type':'guarantee','payment_date':case.rent_payment_date,'reference':'Dossier '+case.reference,'amount':case.guarantee_amount,'payment_method':''})
        total_paid=sum((x['amount'] if isinstance(x,dict) else x.amount) or 0 for x in tenant_payments)
        contract_requests=list(RentalContractRequest.objects.filter(contract=contract,requester=request.user).order_by('-created_at'))
    return render(request,'rental_contract_detail.html',{'contract':contract,'case':case,'property':contract.property,'documents':documents,'is_owner_contract':is_owner_contract,'visit':case.visit,'remittances':remittances,'total_remitted':total_remitted,'tenant_payments':tenant_payments,'total_paid':total_paid,'contract_requests':contract_requests,'validated_documents':validated_documents,'document_total':len(documents)})
