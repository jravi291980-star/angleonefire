from django.core.management.base import BaseCommand
from tradeapp.models import APICredential

class Command(BaseCommand):
    help = 'Removes "Bearer " prefix from Access Token if present'

    def handle(self, *args, **options):
        creds = APICredential.objects.first()
        
        if not creds:
            self.stdout.write(self.style.ERROR("No credentials found."))
            return

        token = creds.access_token
        
        if token and token.startswith("Bearer "):
            # Strip the prefix
            clean_token = token.replace("Bearer ", "").strip()
            
            # Save back to DB
            creds.access_token = clean_token
            creds.save()
            
            self.stdout.write(self.style.SUCCESS("✅ FIXED: Removed 'Bearer ' prefix from Access Token."))
            self.stdout.write(f"New Value: {clean_token[:10]}...")
        else:
            self.stdout.write(self.style.SUCCESS("✅ Token is already clean (No 'Bearer' prefix found)."))