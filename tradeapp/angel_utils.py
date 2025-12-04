import SmartApi.smartConnect as smart
import logging
import time
import os
import redis
from datetime import datetime, timedelta
from tenacity import retry, stop_after_attempt, wait_exponential
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
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.feed_token = feed_token
        if access_token:
            self.client.setAccessToken(access_token)
            self.client.setRefreshToken(refresh_token)
            self.client.setFeedToken(feed_token)

    def _refresh_and_save_token(self):
        if not self.refresh_token:
            logger.error("❌ Cannot refresh: No refresh token available.")
            return False
        try:
            logger.info("🔄 Attempting Token Refresh via API...")
            data = self.client.generateToken(self.refresh_token)
            is_success = data.get('status', False) or data.get('success', False)
            if is_success:
                new_access_token = data['data']['jwtToken']
                new_feed_token = data['data']['feedToken']
                new_refresh_token = data['data']['refreshToken']
                self.client.setAccessToken(new_access_token)
                self.client.setFeedToken(new_feed_token)
                self.client.setRefreshToken(new_refresh_token)
                APICredential = apps.get_model('tradeapp', 'APICredential')
                creds = APICredential.objects.first()
                if creds:
                    creds.access_token = new_access_token
                    creds.feed_token = new_feed_token
                    creds.refresh_token = new_refresh_token
                    creds.save()
                    logger.info("✅ Token Refreshed & Saved Successfully!")
                    return True
            else:
                msg = data.get('message', 'Unknown Error')
                logger.error(f"❌ Refresh Failed: {msg}")
        except Exception as e:
            logger.error(f"❌ Exception during Refresh: {e}")
        return False

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def place_order(self, symbol_token, symbol, quantity, transaction_type, product_type="INTRADAY", order_type="MARKET", price=0.0):
        logger.info(f"📤 Placing Order: {symbol} {transaction_type} {quantity}")
        try:
            orderparams = {
                "variety": "NORMAL", "tradingsymbol": symbol, "symboltoken": symbol_token,
                "transactiontype": transaction_type, "exchange": "NSE", "ordertype": order_type,
                "producttype": product_type, "duration": "DAY", 
                "price": price, "squareoff": "0", "stoploss": "0", "quantity": quantity
            }
            try:
                oid = self.client.placeOrder(orderparams)
                logger.info(f"✅ Order ID Recieved: {oid}")
                return oid
            except Exception as e:
                if "Invalid Token" in str(e) and self._refresh_and_save_token():
                    return self.client.placeOrder(orderparams)
                raise e
        except Exception as e:
            logger.error(f"❌ Order Failed: {e}")
            raise e

    def get_order_status(self, order_id):
        # Implementation remains same as previous, just adding logger if needed
        try:
            book = self.client.orderBook()
            if not book and self._refresh_and_save_token():
                 book = self.client.orderBook()
            if not book or 'data' not in book: return None
            for order in book['data']:
                if order['orderid'] == order_id:
                    return {
                        'status': order['orderstatus'],
                        'filled_quantity': int(order.get('filledshares', 0)),
                        'average_price': float(order.get('averageprice', 0.0))
                    }
            return None
        except Exception:
            return None

    def get_historical_data(self, token, interval="ONE_DAY"):
        # Implementation from previous step (Already has logs)
        # Re-include it here for completeness if you copy-paste the whole file
        try:
            now = datetime.now()
            from_date = now - timedelta(days=10)
            from_str = from_date.strftime("%Y-%m-%d 09:15")
            yesterday = now - timedelta(days=1)
            to_str = yesterday.strftime("%Y-%m-%d 15:30")
            params = {"exchange": "NSE", "symboltoken": token, "interval": interval, "fromdate": from_str, "todate": to_str}
            data = self.client.getCandleData(params)
            
            if not data.get('status') and (data.get('errorcode') == 'AG8001' or 'Invalid Token' in str(data.get('message', ''))):
                logger.warning(f"⚠️ Token Expired for {token}. Attempting Refresh...")
                if self._refresh_and_save_token():
                    data = self.client.getCandleData(params)
            return data['data'] if data and 'data' in data else None
        except Exception as e:
            logger.error(f"History Error {token}: {e}")
            return None