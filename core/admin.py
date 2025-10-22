from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from .models import Business, Product, Customer, MessageLog, Category

@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'owner', 'whatsapp_number', 'instagram_account', 
        'instagram_connection_status', 'ai_enabled', 'active', 'created_at'
    )
    list_filter = ('active', 'ai_enabled', 'allow_auto_reply_from_unknown')
    search_fields = ('name', 'owner__email', 'whatsapp_number', 'instagram_account', 'instagram_page_id')
    readonly_fields = ('page_token_expires_at', 'created_at', 'updated_at')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('owner', 'name', 'active')
        }),
        ('Contact Information', {
            'fields': ('whatsapp_number', 'instagram_account')
        }),
        ('Instagram Integration', {
            'fields': (
                'instagram_page_id', 'instagram_business_account_id', 
                'page_access_token', 'page_token_expires_at'
            ),
            'classes': ('collapse',)
        }),
        ('AI Settings', {
            'fields': ('ai_enabled', 'allow_auto_reply_from_unknown')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def instagram_connection_status(self, obj):
        """Display Instagram connection status with color coding"""
        if obj.instagram_connected:
            if obj.token_expired:
                return format_html(
                    '<span style="color: orange;">⚠️ Connected (Token Expired)</span>'
                )
            else:
                return format_html(
                    '<span style="color: green;">✅ Connected</span>'
                )
        else:
            return format_html(
                '<span style="color: red;">❌ Not Connected</span>'
            )
    instagram_connection_status.short_description = 'Instagram Status'
    
    actions = ['clear_instagram_tokens', 'subscribe_to_instagram']
    
    def clear_instagram_tokens(self, request, queryset):
        """Admin action to clear Instagram tokens"""
        updated = queryset.update(
            instagram_page_id=None,
            instagram_business_account_id=None,
            page_access_token=None,
            page_token_expires_at=None
        )
        self.message_user(request, f'Cleared Instagram tokens for {updated} businesses.')
    clear_instagram_tokens.short_description = 'Clear Instagram tokens'
    
    def subscribe_to_instagram(self, request, queryset):
        """Admin action to subscribe pages to Instagram messaging"""
        from .instagram_api import subscribe_page_to_app
        success_count = 0
        for business in queryset:
            if business.instagram_page_id and business.page_access_token:
                try:
                    subscribe_page_to_app(business.instagram_page_id, business.page_access_token)
                    success_count += 1
                except Exception as e:
                    self.message_user(request, f'Failed to subscribe {business.name}: {str(e)}', level='ERROR')
        
        if success_count > 0:
            self.message_user(request, f'Successfully subscribed {success_count} businesses to Instagram messaging.')
    subscribe_to_instagram.short_description = 'Subscribe to Instagram messaging'

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'sku', 'category', 'business', 'price_usd', 'stock', 'active', 'created_at')
    list_filter = ('business', 'active', 'category', 'created_at')
    search_fields = ('name', 'sku', 'description')
    raw_id_fields = ('business', 'category')
    fieldsets = (
        ('Basic Information', {
            'fields': ('business', 'category', 'sku', 'name', 'description', 'active')
        }),
        ('Pricing', {
            'fields': ('price_usd', 'price_lbp')
        }),
        ('Inventory', {
            'fields': ('stock',)
        }),
        ('Additional Data', {
            'fields': ('metadata', 'image'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    readonly_fields = ('created_at', 'updated_at')

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'business', 'is_global', 'product_count')
    list_filter = ('business', 'is_global')
    search_fields = ('name', 'business__name')
    raw_id_fields = ('business',)
    fields = ('name', 'business', 'is_global')
    
    def product_count(self, obj):
        return obj.products.count()
    product_count.short_description = 'Products'

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('platform', 'platform_id', 'business', 'created_at')
    list_filter = ('platform', 'business', 'created_at')
    search_fields = ('platform_id', 'business__name')
    raw_id_fields = ('business',)
    readonly_fields = ('created_at', 'updated_at')

@admin.register(MessageLog)
class MessageLogAdmin(admin.ModelAdmin):
    list_display = ('business', 'customer', 'direction', 'created_at', 'has_error')
    list_filter = ('direction', 'business', 'created_at', 'error_message')
    search_fields = ('business__name', 'customer__platform_id', 'incoming_text', 'reply_text')
    raw_id_fields = ('business', 'customer')
    readonly_fields = ('created_at',)
    
    def has_error(self, obj):
        """Display if message has error"""
        return bool(obj.error_message)
    has_error.boolean = True
    has_error.short_description = 'Has Error'
