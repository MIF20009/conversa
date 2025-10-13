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

    def __str__(self):
        return f"{self.name} ({self.owner.email})"


class Product(models.Model):
    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name='products'
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
