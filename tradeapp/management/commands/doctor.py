from django.core.management.base import BaseCommand
from tradeapp.models import APICredential
from SmartApi.smartWebSocketV2 import SmartWebSocketV2
import requests
import logging

class Command(BaseCommand):
    help = 'Diagnose Angel One Connection Issues'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("\n========= ANGEL ONE DOCTOR ========="))
        
        # 1. Check Database Data
        creds = APICredential.objects.first()
        if not creds:
            self.stdout.write(self.style.ERROR("❌ CRITICAL: No credentials found in database."))
            return

        self.stdout.write(f"1. Checking Stored Credentials:")
        self.stdout.write(f"   - Client Code: {creds.client_code}")
        self.stdout.write(f"   - API Key: {creds.api_key[:4]}...{creds.api_key[-4:] if creds.api_key else 'None'}")
        
        if not creds.access_token:
            self.stdout.write(self.style.ERROR("❌ CRITICAL: Access Token is MISSING."))
            return
        self.stdout.write(f"   - Access Token: {creds.access_token[:10]}... (Length: {len(creds.access_token)})")
        
        if not creds.feed_token:
            self.stdout.write(self.style.ERROR("❌ CRITICAL: Feed Token is MISSING."))
            return
        self.stdout.write(f"   - Feed Token:   {creds.feed_token[:10]}... (Length: {len(creds.feed_token)})")

        if creds.access_token == creds.feed_token:
            self.stdout.write("   ⚠️  NOTICE: Feed Token is identical to Access Token (Fallback mode).")

        # 2. Test HTTP API (Validates Access Token & API Key)
        self.stdout.write("\n2. Testing HTTP API (Validates Session)...")
        headers = {
            'Authorization': f'Bearer {creds.access_token}',
            'x-api-key': creds.api_key,
            'x-client-code': creds.client_code,
            'Content-Type': 'application/json'
        }
        try:
            url = "https://apiconnect.angelbroking.com/rest/secure/angelbroking/user/v1/getProfile"
            resp = requests.get(url, headers=headers)
            
            if resp.status_code == 200:
                data = resp.json()
                if data['status']:
                    self.stdout.write(self.style.SUCCESS("✅ HTTP API Success! Token is valid."))
                    self.stdout.write(f"   - User Name: {data['data']['name']}")
                else:
                    self.stdout.write(self.style.ERROR(f"❌ HTTP API Failed Logic: {data['message']}"))
                    self.stdout.write("   -> DIAGNOSIS: Your Token is expired or API Key does not match the token.")
                    return
            else:
                self.stdout.write(self.style.ERROR(f"❌ HTTP API Connection Failed: {resp.status_code}"))
                self.stdout.write(f"   Response: {resp.text}")
                self.stdout.write("   -> DIAGNOSIS: Your API Key is likely invalid or blocked.")
                return
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Exception during HTTP Test: {e}"))
            return

        # 3. Test WebSocket Connection
        self.stdout.write("\n3. Testing WebSocket Connection...")
        try:
            sws = SmartWebSocketV2(creds.access_token, creds.api_key, creds.client_code, creds.feed_token)
            
            def on_open(wsapp):
                self.stdout.write(self.style.SUCCESS("✅ WebSocket Connected Successfully!"))
                self.stdout.write("   -> DIAGNOSIS: Connection is healthy. The issue is likely 'Zombie Connections' limit.")
                wsapp.close()

            def on_error(wsapp, error):
                self.stdout.write(self.style.ERROR(f"❌ WebSocket Error: {error}"))

            def on_close(wsapp):
                self.stdout.write("--- Socket Closed ---")

            sws.on_open = on_open
            sws.on_error = on_error
            sws.on_close = on_close
            
            self.stdout.write("   - Connecting to Angel One...")
            sws.connect()
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ WebSocket Exception: {e}"))

        self.stdout.write("\n========= DIAGNOSIS COMPLETE =========")