from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from .models import APICredential, Trade, StrategySettings
import SmartApi.smartConnect as smart
import pyotp
import json

@login_required
def dashboard(request):
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('format') == 'json':
        def fmt_date(dt): return dt.strftime('%H:%M') if dt else '--'
        open_positions = Trade.objects.filter(user=request.user, status__in=['OPEN', 'PENDING_EXIT']).order_by('-created_at')
        scanner_signals = Trade.objects.filter(user=request.user, status='PENDING').order_by('-created_at')
        trade_history = Trade.objects.filter(user=request.user, status__in=['CLOSED', 'EXPIRED', 'CANCELLED', 'FAILED_ENTRY']).order_by('-created_at')[:20]
        data = {
            'scanner': [{'ts': fmt_date(t.candle_ts), 'symbol': t.symbol, 'pdh': float(t.prev_day_high or 0), 'range': f"{float(t.candle_low or 0)}-{float(t.candle_high or 0)}", 'level': float(t.entry_level), 'status': 'Watching'} for t in scanner_signals],
            'positions': [{'symbol': t.symbol, 'qty': t.quantity, 'entry': float(t.entry_price or 0), 'stop': float(t.stop_level), 'target': float(t.target_level), 'status': t.status} for t in open_positions],
            'history': [{'time': fmt_date(t.updated_at), 'symbol': t.symbol, 'status': t.status, 'pnl': float(t.pnl or 0), 'reason': t.exit_reason or t.status} for t in trade_history]
        }
        return JsonResponse(data)

    creds = APICredential.objects.filter(user=request.user).first()
    settings, _ = StrategySettings.objects.get_or_create(user=request.user)
    return render(request, 'tradeapp/dashboard.html', {'creds': creds, 'settings': settings})

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
        APICredential.objects.update_or_create(
            user=request.user,
            defaults={
                'api_key': request.POST.get('api_key'),
                'client_code': request.POST.get('client_code'),
                'password': request.POST.get('password'),
                'totp_secret': request.POST.get('totp_secret')
            }
        )
    return redirect('dashboard')

@login_required
def connect_angel(request):
    """Performs Direct Server-Side Login using TOTP"""
    creds = APICredential.objects.filter(user=request.user).first()
    if not creds or not creds.totp_secret:
        return redirect('dashboard')

    try:
        # 1. Generate TOTP
        totp = pyotp.TOTP(creds.totp_secret).now()
        
        # 2. Initialize API
        obj = smart.SmartConnect(api_key=creds.api_key)
        
        # 3. Login
        data = obj.generateSession(creds.client_code, creds.password, totp)
        
        if data['status']:
            # 4. Capture Tokens
            creds.access_token = data['data']['jwtToken']
            creds.feed_token = data['data']['feedToken'] # AUTHORITATIVE SOURCE
            creds.refresh_token = data['data']['refreshToken']
            creds.save()
            print(f"SUCCESS: Connected! Feed Token: {creds.feed_token[:10]}...")
        else:
            print(f"LOGIN FAILED: {data['message']}")
            
    except Exception as e:
        print(f"EXCEPTION during login: {e}")
        
    return redirect('dashboard')

# Keeping callback for backward compatibility, but we rely on connect_angel now
def angel_callback(request):
    return redirect('dashboard')