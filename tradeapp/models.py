from django.db import models
from django.contrib.auth.models import User

class APICredential(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    api_key = models.CharField(max_length=100)
    client_code = models.CharField(max_length=50)
    
    # New Fields for Direct Login
    password = models.CharField(max_length=100, blank=True, null=True) 
    totp_secret = models.CharField(max_length=50, blank=True, null=True)
    
    access_token = models.TextField(blank=True, null=True)
    refresh_token = models.TextField(blank=True, null=True)
    feed_token = models.TextField(blank=True, null=True)
    last_login = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.client_code}"

class StrategySettings(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='strategy_settings')
    active = models.BooleanField(default=True)
    start_time = models.TimeField(default='09:15:00')
    end_time = models.TimeField(default='15:15:00')
    max_total_trades = models.IntegerField(default=5)
    per_trade_sl_amount = models.DecimalField(max_digits=10, decimal_places=2, default=500.0)
    pnl_exit_enabled = models.BooleanField(default=False)
    profit_target_amount = models.DecimalField(max_digits=10, decimal_places=2, default=2000.0)
    stop_loss_amount = models.DecimalField(max_digits=10, decimal_places=2, default=1000.0)
    volume_price_threshold = models.DecimalField(max_digits=15, decimal_places=2, default=1000000.0)

    def __str__(self):
        return f"Settings for {self.user.username}"

class Trade(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending Monitor'), ('PENDING_ENTRY', 'Pending Entry Order'),
        ('OPEN', 'Open Position'), ('PENDING_EXIT', 'Pending Exit Order'),
        ('CLOSED', 'Closed'), ('CANCELLED', 'Cancelled'),
        ('EXPIRED', 'Expired'), ('FAILED_ENTRY', 'Entry Failed'),
        ('FAILED_EXIT', 'Exit Failed'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    symbol = models.CharField(max_length=50)
    token = models.CharField(max_length=50)
    candle_ts = models.DateTimeField(null=True, blank=True)
    candle_open = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    candle_high = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    candle_low = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    candle_close = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    prev_day_high = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    entry_level = models.DecimalField(max_digits=10, decimal_places=2)
    stop_level = models.DecimalField(max_digits=10, decimal_places=2)
    target_level = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.IntegerField(default=0)
    transaction_type = models.CharField(max_length=10, default="BUY")
    entry_order_id = models.CharField(max_length=50, null=True, blank=True)
    exit_order_id = models.CharField(max_length=50, null=True, blank=True)
    entry_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    exit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='PENDING')
    exit_reason = models.CharField(max_length=100, null=True, blank=True)
    pnl = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.symbol} - {self.status}"