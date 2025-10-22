#!/usr/bin/env python
"""
Debug script to check product data and AI prompt generation
"""
import os
import sys
import django

# Setup Django
sys.path.append('.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'conversa_ai.settings')
django.setup()

from core.models import Business, Product
from core.ai_chat import _analyze_product_categories, _format_categories, _format_products_for_ai

def debug_products():
    print("=== PRODUCT DEBUG ===")
    
    # Check all businesses
    businesses = Business.objects.all()
    print(f"Total businesses: {businesses.count()}")
    
    for business in businesses:
        print(f"\nBusiness: {business.name} (ID: {business.id})")
        print(f"Active: {business.active}")
        print(f"AI Enabled: {business.ai_enabled}")
        
        # Check products
        products = business.products.filter(active=True)
        print(f"Active products: {products.count()}")
        
        for product in products:
            print(f"\n  Product: {product.name}")
            print(f"  Price: ${product.price_usd}")
            if product.price_lbp:
                print(f"  Price LBP: {product.price_lbp:,}")
            print(f"  Stock: {product.stock}")
            print(f"  Metadata: {product.metadata}")
            print(f"  Description: {product.description[:100] if product.description else 'None'}")
        
        # Test category analysis
        if products.exists():
            print(f"\n=== CATEGORY ANALYSIS ===")
            categories = _analyze_product_categories(products)
            print(f"Detected categories: {list(categories.keys())}")
            
            for category, category_products in categories.items():
                print(f"\n{category}:")
                for p in category_products:
                    print(f"  - {p.name}")
            
            print(f"\n=== FORMATTED CATEGORIES ===")
            formatted_cats = _format_categories(categories)
            print(formatted_cats)
            
            print(f"\n=== FORMATTED PRODUCTS ===")
            formatted_prods = _format_products_for_ai(products)
            print(formatted_prods)

if __name__ == "__main__":
    debug_products()
