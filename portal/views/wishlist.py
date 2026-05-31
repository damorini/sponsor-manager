"""
API endpoints per la wishlist nel portale sponsor.
"""
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import csrf_protect
from catalog.models import Service
from portal.models import Wishlist
from portal.views.dashboard import sponsor_required
import json


@sponsor_required
@require_http_methods(["GET"])
def wishlist_view(request):
    """
    Ritorna la wishlist dell'utente loggato.
    GET /portal/api/wishlist/
    """
    try:
        wishlist = request.user.wishlist_obj
    except Wishlist.DoesNotExist:
        wishlist = Wishlist.objects.create(user=request.user)
    
    services = wishlist.services.all().values(
        'id', 'name', 'description', 'base_price', 'category'
    )
    
    return JsonResponse({
        'count': wishlist.services.count(),
        'services': list(services)
    })


@sponsor_required
@require_POST
@csrf_protect
def wishlist_add_api(request):
    """
    Aggiungi un servizio alla wishlist.
    POST /portal/api/wishlist/add/
    Body: {"service_id": "..."}
    """
    try:
        data = json.loads(request.body)
        service_id = data.get('service_id')
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    
    if not service_id:
        return JsonResponse({'error': 'service_id required'}, status=400)
    
    try:
        service = Service.objects.get(id=service_id)
    except Service.DoesNotExist:
        return JsonResponse({'error': 'Service not found'}, status=404)
    
    wishlist, _ = Wishlist.objects.get_or_create(user=request.user)
    wishlist.add_service(service)
    
    return JsonResponse({
        'status': 'added',
        'service_id': str(service.id),
        'wishlist_count': wishlist.services.count()
    })


@sponsor_required
@require_POST
@csrf_protect
def wishlist_remove_api(request):
    """
    Rimuovi un servizio dalla wishlist.
    POST /portal/api/wishlist/remove/
    Body: {"service_id": "..."}
    """
    try:
        data = json.loads(request.body)
        service_id = data.get('service_id')
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    
    if not service_id:
        return JsonResponse({'error': 'service_id required'}, status=400)
    
    try:
        service = Service.objects.get(id=service_id)
    except Service.DoesNotExist:
        return JsonResponse({'error': 'Service not found'}, status=404)
    
    try:
        wishlist = request.user.wishlist_obj
    except Wishlist.DoesNotExist:
        return JsonResponse({'error': 'Wishlist not found'}, status=404)
    
    wishlist.remove_service(service)
    
    return JsonResponse({
        'status': 'removed',
        'service_id': str(service.id),
        'wishlist_count': wishlist.services.count()
    })


@sponsor_required
@require_http_methods(["GET"])
def wishlist_check_api(request):
    """
    Controlla se un servizio è nella wishlist.
    GET /portal/api/wishlist/check/?service_id=...
    """
    service_id = request.GET.get('service_id')
    
    if not service_id:
        return JsonResponse({'error': 'service_id required'}, status=400)
    
    try:
        service = Service.objects.get(id=service_id)
    except Service.DoesNotExist:
        return JsonResponse({'error': 'Service not found'}, status=404)
    
    try:
        wishlist = request.user.wishlist_obj
        in_wishlist = wishlist.has_service(service)
    except Wishlist.DoesNotExist:
        in_wishlist = False
    
    return JsonResponse({
        'service_id': str(service.id),
        'in_wishlist': in_wishlist
    })


@sponsor_required
@require_http_methods(["GET"])
def wishlist_page(request):
    """
    Pagina HTML per visualizzare la wishlist dell'utente.
    GET /portal/wishlist/
    """
    try:
        wishlist = request.user.wishlist_obj
        services = list(wishlist.services.all())
    except Wishlist.DoesNotExist:
        wishlist = None
        services = []

    # Mostra solo i servizi di eventi dove lo sponsor ha un contratto attivo (non annullato).
    # Il dato resta nel database: e' solo un filtro di visualizzazione.
    if services:
        from contracts.models import Contract, ContractStatus
        eventi_validi = set(
            Contract.objects
            .filter(sponsor=request.sponsor, deleted_at__isnull=True)
            .exclude(status=ContractStatus.CANCELLED)
            .values_list('event_id', flat=True)
        )
        services = [s for s in services if s.event_id in eventi_validi]
    
    context = {
        'wishlist': wishlist,
        'services': services,
        'service_count': len(services),
    }
    
    return render(request, 'portal/wishlist/list.html', context)
