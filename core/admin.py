from django.contrib import admin
from .models import Business, Product

@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'whatsapp_number', 'instagram_account', 'active', 'created_at')
    list_filter = ('active',)
    search_fields = ('name', 'owner__email', 'whatsapp_number', 'instagram_account')

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'business', 'sku', 'price_usd', 'price_lbp', 'stock', 'active')
    list_filter = ('business', 'active')
    search_fields = ('name', 'sku')
    raw_id_fields = ('business',)
