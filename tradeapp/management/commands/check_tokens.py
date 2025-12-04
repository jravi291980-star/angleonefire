from django.core.management.base import BaseCommand
from tradeapp.models import APICredential
from django.utils import timezone

class Command(BaseCommand):
    help = 'Checks if Access and Feed tokens are present in the database'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("\n🔍 CHECKING ANGEL ONE TOKENS..."))
        
        # 1. Fetch Credentials from DB
        creds = APICredential.objects.first()
        
        if not creds:
            self.stdout.write(self.style.ERROR("❌ NO CREDENTIALS FOUND!"))
            self.stdout.write("   -> Go to Dashboard and save your API Key, Client Code, etc.")
            return

        # 2. Print Basic Info
        self.stdout.write(f"   👤 User: {creds.user.username}")
        self.stdout.write(f"   🆔 Client Code: {creds.client_code}")
        self.stdout.write(f"   🕒 Last Update: {creds.last_login.strftime('%Y-%m-%d %H:%M:%S') if creds.last_login else 'Never'}")
        self.stdout.write("-" * 40)

        # 3. Check Access Token
        if creds.access_token:
            token_len = len(creds.access_token)
            preview = creds.access_token[:15] + "..." + creds.access_token[-5:]
            self.stdout.write(self.style.SUCCESS(f"✅ ACCESS TOKEN Found"))
            self.stdout.write(f"   Length: {token_len} chars")
            self.stdout.write(f"   Value:  {preview}")
        else:
            self.stdout.write(self.style.ERROR("❌ ACCESS TOKEN MISSING (None/Empty)"))

        self.stdout.write("-" * 40)

        # 4. Check Feed Token
        if creds.feed_token:
            token_len = len(creds.feed_token)
            preview = creds.feed_token[:15] + "..." + creds.feed_token[-5:]
            self.stdout.write(self.style.SUCCESS(f"✅ FEED TOKEN Found"))
            self.stdout.write(f"   Length: {token_len} chars")
            self.stdout.write(f"   Value:  {preview}")
            
            if creds.feed_token == creds.access_token:
                self.stdout.write(self.style.ERROR("   ⚠️  WARNING: Feed Token is IDENTICAL to Access Token!"))
                self.stdout.write("       This usually means the Redirect Login was used.")
                self.stdout.write("       WebSocket might fail. Use TOTP Login.")
        else:
            self.stdout.write(self.style.ERROR("❌ FEED TOKEN MISSING"))

        self.stdout.write("-" * 40)

        # 5. Check Refresh Token
        if creds.refresh_token:
            token_len = len(creds.refresh_token)
            self.stdout.write(self.style.SUCCESS(f"✅ REFRESH TOKEN Found ({token_len} chars)"))
        else:
            self.stdout.write(self.style.ERROR("❌ REFRESH TOKEN MISSING"))
            self.stdout.write("   -> Auto-refresh will NOT work.")

        self.stdout.write("\n" + "="*30)
        
        # Final Verdict
        if creds.access_token and creds.feed_token and creds.refresh_token:
             self.stdout.write(self.style.SUCCESS("🚀 STATUS: READY TO TRADE"))
        else:
             self.stdout.write(self.style.ERROR("🛑 STATUS: NOT READY - PLEASE LOGIN"))