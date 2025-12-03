import json
import time
import logging
import threading
from math import floor
from datetime import datetime as dt, timedelta
from typing import Dict, Any

import pytz
import redis
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.conf import settings

from tradeapp.models import APICredential, Trade, StrategySettings
from tradeapp.angel_utils import AngelConnect, get_redis_client

logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")

CANDLE_STREAM_KEY = getattr(settings, "BREAKOUT_CANDLE_STREAM", "candle_1m")
LIVE_OHLC_KEY = getattr(settings, "BREAKOUT_LIVE_OHLC_KEY", "live_ohlc_data")
PREV_DAY_HASH = "prev_day_ohlc"
ENTRY_OFFSET_PCT = 0.0001
STOP_OFFSET_PCT = 0.0002

class CashBreakoutClient:
    def __init__(self, user, api_creds):
        self.user = user
        self.api_creds = api_creds
        self.angel = AngelConnect(
            api_key=api_creds.api_key, 
            access_token=api_creds.access_token,
            refresh_token=api_creds.refresh_token,
            feed_token=api_creds.feed_token
        )
        # FIX: Use helper
        self.redis_client = get_redis_client()
        
        self.settings, _ = StrategySettings.objects.get_or_create(user=user)
        self.running = True
        self.last_reconcile_time = time.time()
        self.open_trades = {}
        self.pending_trades = {}
        self.group_name = f"CB_GROUP:{self.user.id}"
        self.consumer_name = f"CB_CONSUMER:{threading.get_ident()}"
        
        try:
            self.redis_client.xgroup_create(CANDLE_STREAM_KEY, self.group_name, id='0', mkstream=True)
        except redis.exceptions.ResponseError:
            pass

        self._load_trades_from_db()

    def _load_trades_from_db(self):
        active_trades = Trade.objects.filter(
            user=self.user, 
            status__in=["OPEN", "PENDING_EXIT", "PENDING", "PENDING_ENTRY"]
        )
        for trade in active_trades:
            if trade.status == "PENDING":
                self.pending_trades[trade.symbol] = trade
            elif trade.status in ["OPEN", "PENDING_EXIT"]:
                self.open_trades[trade.symbol] = trade

    def _get_live_ohlc(self) -> Dict[str, Any]:
        try:
            raw = self.redis_client.get(LIVE_OHLC_KEY)
            return json.loads(raw) if raw else {}
        except Exception:
            return {}

    def _get_prev_day_high(self, symbol):
        raw = self.redis_client.hget(PREV_DAY_HASH, symbol)
        if raw:
            try:
                data = json.loads(raw)
                return float(data.get('high', 0))
            except: pass
        return None

    def _calculate_quantity(self, entry_price, sl_price):
        risk_per_share = abs(entry_price - sl_price)
        if risk_per_share <= 0: return 0
        qty = floor(float(self.settings.per_trade_sl_amount) / risk_per_share)
        return int(qty)

    def _process_candle(self, candle):
        symbol = candle['symbol']
        token = candle['token']
        if symbol in self.pending_trades or symbol in self.open_trades:
            return

        pdh = self._get_prev_day_high(symbol)
        if not pdh: return 

        close = float(candle['close'])
        open_ = float(candle['open'])
        high = float(candle['high'])
        low = float(candle['low'])
        
        if not (close > open_): return
        if not (low < pdh < close): return
        if not (open_ < pdh): return
        
        entry_level = high * (1.0 + ENTRY_OFFSET_PCT)
        stop_level = low - (low * STOP_OFFSET_PCT)
        target_level = entry_level + (2.5 * (entry_level - stop_level))
        
        trade = Trade.objects.create(
            user=self.user,
            symbol=symbol,
            token=token,
            candle_ts=timezone.now(),
            candle_open=open_, candle_high=high, candle_low=low, candle_close=close,
            prev_day_high=pdh,
            entry_level=entry_level,
            stop_level=stop_level,
            target_level=target_level,
            status="PENDING"
        )
        self.pending_trades[symbol] = trade
        logger.info(f"Registered PENDING: {symbol} Entry: {entry_level}")

    def _try_enter_pending(self):
        live_data = self._get_live_ohlc()
        to_remove = []
        for symbol, trade in self.pending_trades.items():
            if symbol not in live_data: continue
            
            ltp = float(live_data[symbol].get('ltp', 0))
            if timezone.now() > trade.candle_ts + timedelta(minutes=6):
                trade.status = "EXPIRED"
                trade.save()
                to_remove.append(symbol)
                continue

            if ltp < float(trade.stop_level):
                trade.status = "EXPIRED"
                trade.save()
                to_remove.append(symbol)
                continue

            if ltp > float(trade.entry_level):
                qty = self._calculate_quantity(ltp, float(trade.stop_level))
                if qty > 0:
                    try:
                        order_id = self.angel.place_order(trade.token, trade.symbol, qty, "BUY")
                        trade.status = "PENDING_ENTRY"
                        trade.entry_order_id = order_id
                        trade.quantity = qty
                        trade.save()
                    except Exception:
                        trade.status = "FAILED_ENTRY"
                        trade.save()
                to_remove.append(symbol)

        for s in to_remove:
            del self.pending_trades[s]

    def reconcile_trades(self):
        entries = Trade.objects.filter(user=self.user, status="PENDING_ENTRY")
        for trade in entries:
            status_data = self.angel.get_order_status(trade.entry_order_id)
            if status_data:
                if status_data['status'].lower() == 'complete':
                    trade.status = "OPEN"
                    trade.entry_price = status_data['average_price']
                    trade.quantity = status_data['filled_quantity'] 
                    trade.save()
                    self.open_trades[trade.symbol] = trade
                elif status_data['status'].lower() in ['rejected', 'cancelled']:
                    trade.status = "FAILED_ENTRY"
                    trade.save()

        exits = Trade.objects.filter(user=self.user, status="PENDING_EXIT")
        for trade in exits:
            status_data = self.angel.get_order_status(trade.exit_order_id)
            if status_data and status_data['status'].lower() == 'complete':
                trade.status = "CLOSED"
                trade.exit_price = status_data['average_price']
                trade.pnl = (float(trade.exit_price) - float(trade.entry_price)) * trade.quantity
                trade.save()
                if trade.symbol in self.open_trades:
                    del self.open_trades[trade.symbol]

    def monitor_trades(self):
        live_data = self._get_live_ohlc()
        for symbol, trade in list(self.open_trades.items()):
            if symbol not in live_data: continue
            
            ltp = float(live_data[symbol].get('ltp', 0))
            entry_price = float(trade.entry_price)
            stop_level = float(trade.stop_level)
            target_level = float(trade.target_level)
            
            risk = entry_price - stop_level
            if risk > 0:
                be_trigger = entry_price + (1.25 * risk)
                if ltp >= be_trigger and stop_level < entry_price:
                    trade.stop_level = entry_price 
                    trade.save()

            exit_needed = False
            reason = ""
            
            if ltp >= target_level:
                exit_needed = True
                reason = "Target Hit"
            elif ltp <= stop_level:
                exit_needed = True
                reason = "Stop Loss Hit"
            
            if exit_needed:
                try:
                    order_id = self.angel.place_order(trade.token, trade.symbol, trade.quantity, "SELL")
                    trade.status = "PENDING_EXIT"
                    trade.exit_order_id = order_id
                    trade.exit_reason = reason
                    trade.save()
                except Exception:
                    pass

    def run(self):
        logger.info("Algo Engine Started...")
        while self.running:
            try:
                messages = self.redis_client.xreadgroup(
                    self.group_name, self.consumer_name, {CANDLE_STREAM_KEY: '>'}, count=10, block=1000
                )
                if messages:
                    for _, msg_list in messages:
                        for msg_id, msg_data in msg_list:
                            candle = json.loads(msg_data['data'])
                            self._process_candle(candle)
                            self.redis_client.xack(CANDLE_STREAM_KEY, self.group_name, msg_id)

                self._try_enter_pending()
                self.monitor_trades()
                
                if time.time() - self.last_reconcile_time > 1:
                    self.reconcile_trades()
                    self.last_reconcile_time = time.time()
                
            except Exception as e:
                logger.error(f"Engine Loop Error: {e}")
                time.sleep(1)

class Command(BaseCommand):
    help = 'Runs the Angel Algo Engine'

    def handle(self, *args, **options):
        creds = APICredential.objects.first()
        if not creds: return
        client = CashBreakoutClient(creds.user, creds)
        client.run()