from django.conf import settings
from django.db import models

class Business(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='businesses'
    )
    name = models.CharField(max_length=255)
    whatsapp_number = models.CharField(
        max_length=32,
        blank=True,
        null=True,
        help_text="Store normalized phone (E.164) if possible, e.g. +9617XXXXXXX"
    )
    instagram_account = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        help_text="Instagram handle or business id (e.g. @shopname)"
    )
    active = models.BooleanField(default=True)  # control if AI runs for this business
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Instagram Business Integration Fields
    instagram_page_id = models.CharField(
        max_length=64,
        unique=True,
        blank=True,
        null=True,
        help_text="Facebook Page ID linked to the Instagram Business account"
    )
    instagram_business_account_id = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        help_text="Instagram Business Account ID"
    )
    page_access_token = models.TextField(
        blank=True,
        null=True,
        help_text="Page Access Token for sending messages via Instagram API"
    )
    page_token_expires_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Expiry timestamp for the page access token"
    )
    ai_enabled = models.BooleanField(
        default=True,
        help_text="Owner toggle for AI auto-replies"
    )
    allow_auto_reply_from_unknown = models.BooleanField(
        default=False,
        help_text="Whether to auto-reply to first-time senders"
    )

    def __str__(self):
        return self.name
    
    @property
    def instagram_connected(self):
        """Check if Instagram is properly connected"""
        return bool(self.instagram_page_id and self.page_access_token)
    
    @property
    def token_expired(self):
        """Check if the page access token is expired"""
        if not self.page_token_expires_at:
            return False
        from django.utils import timezone
        return timezone.now() > self.page_token_expires_at


class Product(models.Model):
    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name='products'
    )
    # Category FK - can be global or business-specific
    category = models.ForeignKey(
        'Category', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='products',
        limit_choices_to={'business': models.F('business')}  # Only allow categories for this business
    )
    sku = models.CharField(max_length=64, blank=True, null=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    price_usd = models.DecimalField(max_digits=12, decimal_places=2)
    price_lbp = models.BigIntegerField(blank=True, null=True, help_text="Store as integer LBP")
    stock = models.IntegerField(default=0)
    image = models.ImageField(upload_to='product_images/', blank=True, null=True)
    metadata = models.JSONField(blank=True, null=True)  # sizes, colors, etc.
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['business', 'sku']),
            models.Index(fields=['business', 'name']),
        ]

    def __str__(self):
        return f"{self.name} — {self.business.name}"


class Customer(models.Model):
    """Customer information from messaging platforms"""
    PLATFORM_CHOICES = [
        ('instagram', 'Instagram'),
        ('whatsapp', 'WhatsApp'),
    ]
    
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    platform_id = models.CharField(max_length=128, help_text="User ID from the platform")
    business = models.ForeignKey(
        Business, 
        on_delete=models.CASCADE, 
        related_name='customers'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['platform', 'platform_id', 'business']
        indexes = [
            models.Index(fields=['business', 'platform']),
            models.Index(fields=['platform', 'platform_id']),
        ]
    
    def __str__(self):
        return f"{self.platform}:{self.platform_id} - {self.business.name}"


class MessageLog(models.Model):
    """Log of messages sent and received for analytics/debugging"""
    DIRECTION_CHOICES = [
        ('incoming', 'Incoming'),
        ('outgoing', 'Outgoing'),
    ]
    
    business = models.ForeignKey(
        Business, 
        on_delete=models.CASCADE, 
        related_name='message_logs'
    )
    customer = models.ForeignKey(
        Customer, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='message_logs'
    )
    sender_id = models.CharField(
        max_length=128, 
        blank=True, 
        null=True,
        help_text="Platform sender ID if customer not found"
    )
    incoming_text = models.TextField(blank=True, null=True)
    reply_text = models.TextField(blank=True, null=True)
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES)
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['business', 'created_at']),
            models.Index(fields=['customer', 'created_at']),
            models.Index(fields=['direction', 'created_at']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.direction} - {self.business.name} - {self.created_at}"


class Category(models.Model):
    """Product category that can be shared across businesses or business-specific."""
    name = models.CharField(max_length=120)
    business = models.ForeignKey(
        Business, 
        on_delete=models.CASCADE, 
        related_name='categories',
        null=True, 
        blank=True,
        help_text="If null, this is a global category. If set, this is business-specific."
    )
    is_global = models.BooleanField(
        default=False,
        help_text="Global categories are available to all businesses"
    )

    class Meta:
        ordering = ['name']
        unique_together = ['name', 'business']  # Prevent duplicate names within same business
        verbose_name_plural = 'Categories'

    def __str__(self):
        return self.name
