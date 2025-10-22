#!/usr/bin/env python
"""
Debug script to check business Instagram connection
"""
import os
import sys
import django

# Setup Django
sys.path.append('.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'conversa_ai.settings')
django.setup()

from core.models import Business, Product, MessageLog

def debug_business():
    print("=== BUSINESS DEBUG ===")
    
    # Check all businesses
    businesses = Business.objects.all()
    print(f"Total businesses: {businesses.count()}")
    
    for business in businesses:
        print(f"\nBusiness ID: {business.id}")
        print(f"Name: {business.name}")
        print(f"Owner: {business.owner.username}")
        print(f"Active: {business.active}")
        print(f"AI Enabled: {business.ai_enabled}")
        print(f"Allow Auto Reply: {business.allow_auto_reply_from_unknown}")
        print(f"Instagram Page ID: {business.instagram_page_id}")
        print(f"Instagram Business Account ID: {business.instagram_business_account_id}")
        print(f"Page Access Token: {'SET' if business.page_access_token else 'NOT SET'}")
        print(f"Token Expires: {business.page_token_expires_at}")
        print(f"Instagram Connected: {business.instagram_connected}")
        print(f"Token Expired: {business.token_expired}")
        
        # Check products
        products = business.products.filter(active=True)
        print(f"Active Products: {products.count()}")
        
        # Check message logs
        logs = business.message_logs.all()
        print(f"Message Logs: {logs.count()}")
        
        if logs.exists():
            latest = logs.first()
            print(f"Latest Log: {latest.direction} - {latest.created_at}")
            if latest.error_message:
                print(f"Error: {latest.error_message}")

def test_ai_response():
    print("\n=== AI RESPONSE TEST ===")
    
    business = Business.objects.first()
    if not business:
        print("No businesses found!")
        return
        
    if not business.instagram_connected:
        print("Business not connected to Instagram!")
        return
        
    try:
        from core.ai_chat import get_ai_response
        response = get_ai_response(business.id, "Hello, what products do you have?")
        print(f"AI Response: {response}")
    except Exception as e:
        print(f"AI Error: {str(e)}")

if __name__ == "__main__":
    debug_business()
    test_ai_response()
