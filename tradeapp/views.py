from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import APICredential, Trade, StrategySettings

@login_required
def dashboard(request):
    creds = APICredential.objects.filter(user=request.user).first()
    settings, _ = StrategySettings.objects.get_or_create(user=request.user)
    
    # 1. Open Positions (Active Trades)
    open_positions = Trade.objects.filter(
        user=request.user, 
        status__in=['OPEN', 'PENDING_EXIT']
    ).order_by('-created_at')

    # 2. Scanner Results (Pending Breakouts waiting for Trigger)
    scanner_signals = Trade.objects.filter(
        user=request.user, 
        status='PENDING'
    ).order_by('-created_at')

    # 3. History (Closed/Expired/Cancelled)
    trade_history = Trade.objects.filter(
        user=request.user, 
        status__in=['CLOSED', 'EXPIRED', 'CANCELLED', 'FAILED_ENTRY']
    ).order_by('-created_at')[:20]
    
    context = {
        'creds': creds,
        'settings': settings,
        'open_positions': open_positions,
        'scanner_signals': scanner_signals,
        'trade_history': trade_history,
        'angel_login_url': f"https://smartapi.angelbroking.com/publisher-login?api_key={creds.api_key}" if creds else "#"
    }
    # Note the updated template path
    return render(request, 'tradeapp/dashboard.html', context)

@login_required
def save_settings(request):
    if request.method == "POST":
        s, _ = StrategySettings.objects.get_or_create(user=request.user)
        s.max_total_trades = int(request.POST.get('max_trades', 5))
        s.per_trade_sl_amount = float(request.POST.get('sl_amount', 500))
        s.active = 'active' in request.POST
        s.save()
    return redirect('dashboard')

@login_required
def save_credentials(request):
    if request.method == "POST":
        api_key = request.POST.get('api_key')
        client_code = request.POST.get('client_code')
        secret_key = request.POST.get('secret_key')
        
        APICredential.objects.update_or_create(
            user=request.user,
            defaults={
                'api_key': api_key,
                'client_code': client_code,
                'secret_key': secret_key
            }
        )
    return redirect('dashboard')

def angel_callback(request):
    auth_token = request.GET.get('auth_token')
    if auth_token and request.user.is_authenticated:
        creds, _ = APICredential.objects.get_or_create(user=request.user)
        creds.access_token = auth_token
        creds.save()
    return redirect('dashboard')