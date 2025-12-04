import SmartApi.smartConnect as smart
import logging
import time
import os
import redis
from datetime import datetime, timedelta
from tenacity import retry, stop_after_attempt, wait_exponential

# Import Models locally to avoid circular imports
from django.apps import apps

logger = logging.getLogger(__name__)

def get_redis_client():
    redis_url = os.environ.get('REDIS_URL')
    if redis_url:
        return redis.from_url(redis_url, decode_responses=True, ssl_cert_reqs=None)
    else:
        return redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

class AngelConnect:
    def __init__(self, api_key, access_token=None, refresh_token=None, feed_token=None):
        self.api_key = api_key
        self.client = smart.SmartConnect(api_key=self.api_key)
        
        # Store tokens for refreshing later
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.feed_token = feed_token
        
        if access_token:
            self.client.setAccessToken(access_token)
            self.client.setRefreshToken(refresh_token)
            self.client.setFeedToken(feed_token)

    def _refresh_and_save_token(self):
        """
        Internal method to refresh token using the refresh_token.
        """
        if not self.refresh_token:
            print("❌ Cannot refresh: No refresh token available.")
            return False

        try:
            print("🔄 Attempting Token Refresh via API...")
            # Attempt refresh
            data = self.client.generateToken(self.refresh_token)
            
            if data['status']:
                new_access_token = data['data']['jwtToken']
                new_feed_token = data['data']['feedToken']
                new_refresh_token = data['data']['refreshToken']
                
                # Update Client
                self.client.setAccessToken(new_access_token)
                self.client.setFeedToken(new_feed_token)
                self.client.setRefreshToken(new_refresh_token)
                
                # Save to Database
                APICredential = apps.get_model('tradeapp', 'APICredential')
                creds = APICredential.objects.first()
                if creds:
                    creds.access_token = new_access_token
                    creds.feed_token = new_feed_token
                    creds.refresh_token = new_refresh_token
                    creds.save()
                    print("✅ Token Refreshed & Saved Successfully!")
                    return True
            else:
                print(f"❌ Token Refresh Failed: {data['message']}")
        except Exception as e:
            print(f"❌ Exception during Token Refresh: {e}")
        
        return False

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def place_order(self, symbol_token, symbol, quantity, transaction_type, product_type="INTRADAY", order_type="MARKET", price=0.0):
        try:
            orderparams = {
                "variety": "NORMAL",
                "tradingsymbol": symbol,
                "symboltoken": symbol_token,
                "transactiontype": transaction_type,
                "exchange": "NSE",
                "ordertype": order_type,
                "producttype": product_type,
                "duration": "DAY",
                "price": price,
                "squareoff": "0",
                "stoploss": "0",
                "quantity": quantity
            }
            order_id = self.client.placeOrder(orderparams)
            return order_id
        except Exception as e:
            logger.error(f"Angel Utils: Place Order Failed: {e}")
            raise e

    def get_historical_data(self, token, interval="ONE_DAY"):
        """
        Fetches historical data with Auto-Refresh Logic for AG8001 Errors.
        Also clamps 'todate' to CURRENT TIME to avoid 'Future Date' errors.
        """
        try:
            now = datetime.now()
            
            # 1. Date Logic: Last 10 days
            from_date = now - timedelta(days=10)
            from_str = from_date.strftime("%Y-%m-%d 09:15")
            
            # 2. Date Logic: If running during market hours, cap 'todate' to NOW
            # Asking for 15:30 when it is 12:00 can cause AB1004 errors
            to_str = now.strftime("%Y-%m-%d %H:%M") 
            
            params = {
                "exchange": "NSE",
                "symboltoken": token,
                "interval": interval,
                "fromdate": from_str,
                "todate": to_str
            }
            
            # First Attempt
            data = self.client.getCandleData(params)
            
            # 3. Auto-Refresh Logic (AG8001)
            # If status is False AND (Error is AG8001 OR message says Invalid Token)
            if not data.get('status') and (data.get('errorcode') == 'AG8001' or 'Invalid Token' in str(data.get('message'))):
                print(f"⚠️ Token Expired for {token}. Initiating Auto-Refresh...")
                
                if self._refresh_and_save_token():
                    # Retry Request with new token
                    data = self.client.getCandleData(params)
                    if data.get('status'):
                        print("✅ Retry Success!")
                    else:
                        print(f"❌ Retry Failed: {data.get('message')}")
                else:
                    print("❌ Refresh Failed. Please Login manually via Dashboard.")

            return data['data'] if data and 'data' in data else None
            
        except Exception as e:
            logger.error(f"Error fetching history for {token}: {e}")
            return None