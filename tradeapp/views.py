from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from .models import APICredential, Trade, StrategySettings
import json

@login_required
def dashboard(request):
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('format') == 'json':
        def fmt_date(dt): return dt.strftime('%H:%M') if dt else '--'
        
        open_positions = Trade.objects.filter(user=request.user, status__in=['OPEN', 'PENDING_EXIT']).order_by('-created_at')
        scanner_signals = Trade.objects.filter(user=request.user, status='PENDING').order_by('-created_at')
        trade_history = Trade.objects.filter(user=request.user, status__in=['CLOSED', 'EXPIRED', 'CANCELLED', 'FAILED_ENTRY']).order_by('-created_at')[:20]

        data = {
            'scanner': [{
                'ts': fmt_date(t.candle_ts),
                'symbol': t.symbol,
                'pdh': float(t.prev_day_high or 0),
                'range': f"{float(t.candle_low or 0)} - {float(t.candle_high or 0)}",
                'level': float(t.entry_level),
                'status': 'Watching'
            } for t in scanner_signals],
            
            'positions': [{
                'symbol': t.symbol,
                'qty': t.quantity,
                'entry': float(t.entry_price or 0),
                'stop': float(t.stop_level),
                'target': float(t.target_level),
                'status': t.status
            } for t in open_positions],
            
            'history': [{
                'time': fmt_date(t.updated_at),
                'symbol': t.symbol,
                'status': t.status,
                'pnl': float(t.pnl or 0),
                'reason': t.exit_reason or t.status
            } for t in trade_history]
        }
        return JsonResponse(data)

    creds = APICredential.objects.filter(user=request.user).first()
    settings, _ = StrategySettings.objects.get_or_create(user=request.user)
    
    context = {
        'creds': creds,
        'settings': settings,
        'angel_login_url': f"https://smartapi.angelbroking.com/publisher-login?api_key={creds.api_key}" if creds else "#"
    }
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
    
    # CHECK BOTH PARAMETER NAMES (CamelCase vs Snake_Case)
    feed_token = request.GET.get('feedToken') or request.GET.get('feed_token')
    refresh_token = request.GET.get('refreshToken') or request.GET.get('refresh_token')
    
    if auth_token and request.user.is_authenticated:
        creds, _ = APICredential.objects.get_or_create(user=request.user)
        creds.access_token = auth_token
        
        if feed_token:
            creds.feed_token = feed_token
        else:
            # Fallback: If Angel still doesn't send it, use auth_token
            # This is a safe fallback for WebSocket V2
            creds.feed_token = auth_token
            
        if refresh_token:
            creds.refresh_token = refresh_token
            
        creds.save()
    return redirect('dashboard')