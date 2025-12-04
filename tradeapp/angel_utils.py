import SmartApi.smartConnect as smart
import logging
import time
import os
import redis
from datetime import datetime, timedelta
from tenacity import retry, stop_after_attempt, wait_exponential

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
        
        if access_token:
            self.client.setAccessToken(access_token)
            self.client.setRefreshToken(refresh_token)
            self.client.setFeedToken(feed_token)

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

    def get_order_status(self, order_id):
        try:
            book = self.client.orderBook()
            if not book or 'data' not in book:
                return None
            for order in book['data']:
                if order['orderid'] == order_id:
                    return {
                        'status': order['orderstatus'],
                        'filled_quantity': int(order.get('filledshares', 0)),
                        'average_price': float(order.get('averageprice', 0.0)),
                        'text': order.get('text', '')
                    }
            return None
        except Exception as e:
            logger.error(f"Angel Utils: Get Order Status Failed: {e}")
            return None

    def get_historical_data(self, token, interval="ONE_DAY"):
        """
        Fetches historical data with STRICT time formatting.
        Format must be: yyyy-MM-dd 09:15 to yyyy-MM-dd 15:30
        """
        try:
            today = datetime.now()
            
            # We fetch the last 5 days to automatically handle weekends/holidays.
            # If we only asked for "yesterday", it would fail on Mondays.
            from_date_obj = today - timedelta(days=5)
            
            # Formatting as per Official Doc: '%Y-%m-%d %H:%M'
            # Timestamps MUST be 09:15 and 15:30
            from_str = from_date_obj.strftime("%Y-%m-%d 09:15")
            to_str = today.strftime("%Y-%m-%d 15:30")
            
            params = {
                "exchange": "NSE",
                "symboltoken": token,
                "interval": interval,
                "fromdate": from_str,
                "todate": to_str
            }
            
            data = self.client.getCandleData(params)
            return data['data'] if data and 'data' in data else None
        except Exception as e:
            logger.error(f"Error fetching history for {token}: {e}")
            return None