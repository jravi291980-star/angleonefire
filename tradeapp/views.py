from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from .models import APICredential, Trade, StrategySettings
import SmartApi.smartConnect as smart
import pyotp
import json
import logging

# Setup Logger to print to Heroku logs
logger = logging.getLogger(__name__)

@login_required
def dashboard(request):
    """
    Main Dashboard View.
    Handles two types of requests:
    1. AJAX (JSON): Used by the JavaScript auto-refresher to update tables.
    2. HTML (Standard): Renders the full page when you first load it.
    """
    # 1. AJAX Handler for Auto-Refresh
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('format') == 'json':
        
        def fmt_date(dt): 
            return dt.strftime('%H:%M') if dt else '--'
        
        # Fetch Data
        open_positions = Trade.objects.filter(user=request.user, status__in=['OPEN', 'PENDING_EXIT']).order_by('-created_at')
        scanner_signals = Trade.objects.filter(user=request.user, status='PENDING').order_by('-created_at')
        trade_history = Trade.objects.filter(user=request.user, status__in=['CLOSED', 'EXPIRED', 'CANCELLED', 'FAILED_ENTRY']).order_by('-created_at')[:20]

        # Prepare JSON Payload
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

    # 2. Standard Page Load
    creds = APICredential.objects.filter(user=request.user).first()
    settings, _ = StrategySettings.objects.get_or_create(user=request.user)
    
    # Check if we are connected
    is_connected = creds and creds.access_token and creds.feed_token and (creds.access_token != creds.feed_token)

    context = {
        'creds': creds,
        'settings': settings,
        'is_connected': is_connected,
        # Fallback URL only used if user clicks old connect button
        'angel_login_url': f"https://smartapi.angelbroking.com/publisher-login?api_key={creds.api_key}" if creds else "#"
    }
    return render(request, 'tradeapp/dashboard.html', context)

@login_required
def save_settings(request):
    """Updates Strategy Risk and Limit Settings"""
    if request.method == "POST":
        s, _ = StrategySettings.objects.get_or_create(user=request.user)
        try:
            s.max_total_trades = int(request.POST.get('max_trades', 5))
            s.per_trade_sl_amount = float(request.POST.get('sl_amount', 500))
            s.active = 'active' in request.POST
            s.save()
        except ValueError:
            pass # Ignore invalid numbers
    return redirect('dashboard')

@login_required
def save_credentials(request):
    """Updates API Key, Client Code, PIN, and TOTP Secret"""
    if request.method == "POST":
        APICredential.objects.update_or_create(
            user=request.user,
            defaults={
                'api_key': request.POST.get('api_key').strip(),
                'client_code': request.POST.get('client_code').strip(),
                'password': request.POST.get('password').strip(), # Angel MPIN
                'totp_secret': request.POST.get('totp_secret').strip() # TOTP Key
            }
        )
    return redirect('dashboard')

@login_required
def connect_angel(request):
    """
    Performs Direct Server-Side Login using SmartAPI Library.
    Generates TOTP -> Logins -> Saves Valid Feed Token.
    """
    creds = APICredential.objects.filter(user=request.user).first()
    
    # Validation
    if not creds:
        print("LOGIN ERROR: No Credentials found.")
        return redirect('dashboard')
        
    if not creds.password or not creds.totp_secret:
        print("LOGIN ERROR: MPIN or TOTP Secret is missing.")
        return redirect('dashboard')

    try:
        # 1. Generate TOTP Code
        try:
            totp = pyotp.TOTP(creds.totp_secret).now()
        except Exception:
            print("LOGIN ERROR: Invalid TOTP Secret format.")
            return redirect('dashboard')
        
        # 2. Initialize SmartAPI
        obj = smart.SmartConnect(api_key=creds.api_key)
        
        # 3. Perform Login
        data = obj.generateSession(creds.client_code, creds.password, totp)
        
        # 4. Handle Response
        if data.get('status'):
            # SUCCESS
            jwt_token = data['data']['jwtToken']
            feed_token = data['data']['feedToken']
            refresh_token = data['data']['refreshToken']
            
            # Save Tokens to Database
            creds.access_token = jwt_token
            creds.feed_token = feed_token
            creds.refresh_token = refresh_token
            creds.save()
            
            print("------------------------------------------------")
            print("✅ ANGEL LOGIN SUCCESSFUL")
            print(f"   Feed Token: {feed_token[:10]}...")
            print("------------------------------------------------")
        else:
            # FAILED
            error_msg = data.get('message', 'Unknown Error')
            error_code = data.get('errorcode', '')
            print("------------------------------------------------")
            print(f"❌ ANGEL LOGIN FAILED: {error_msg} ({error_code})")
            print("------------------------------------------------")
            
    except Exception as e:
        print(f"❌ CRITICAL EXCEPTION during Login: {e}")
        
    return redirect('dashboard')

def angel_callback(request):
    """
    Legacy Callback URL.
    We don't use this for login anymore, but keeping it ensures
    Old Redirect configurations don't crash the app.
    """
    return redirect('dashboard')