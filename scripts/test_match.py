#!/usr/bin/env python
"""
Test script for image matching functionality.

This script demonstrates how to use the image matching system by:
1. Processing a sample image URL
2. Finding matching products
3. Displaying the results

Usage:
    python scripts/test_match.py
"""

import os
import sys
import django
from pathlib import Path

# Add the project directory to Python path
project_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_dir))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'conversa_ai.settings')
django.setup()

from core.tasks import process_media
from core.models import Business, Product, MediaToProductMap


def test_image_matching():
    """Test image matching with a sample image URL."""
    
    print("🧪 Testing Image Matching System")
    print("=" * 50)
    
    # Get the first business for testing
    try:
        business = Business.objects.first()
        if not business:
            print("❌ No businesses found. Please create a business first.")
            return
        
        print(f"📊 Testing with business: {business.name}")
        
        # Check if there are any products with images
        products_with_images = Product.objects.filter(
            business=business,
            image__isnull=False
        ).exclude(image='')
        
        if not products_with_images.exists():
            print("❌ No products with images found. Please add some products with images first.")
            return
        
        print(f"📦 Found {products_with_images.count()} products with images")
        
        # Sample image URL (you can replace this with any public image URL)
        sample_image_url = "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=400&h=400&fit=crop"
        
        print(f"🖼️  Testing with sample image: {sample_image_url}")
        
        # Process the media
        print("\n🔄 Processing media...")
        result = process_media(
            media_url=sample_image_url,
            business_id=business.id,
            media_id="test_sample_image",
            sender_id="test_user"
        )
        
        print(f"\n📋 Results:")
        print(f"   Success: {result.get('success', False)}")
        print(f"   Matched: {result.get('matched', False)}")
        
        if result.get('matched'):
            print(f"   Product ID: {result.get('product_id')}")
            print(f"   Confidence: {result.get('confidence', 0):.3f}")
            
            # Get the matched product
            product = Product.objects.get(id=result['product_id'])
            print(f"   Product Name: {product.name}")
            print(f"   Product Price: ${product.price_usd}")
            
            # Check if mapping was saved
            mapping = MediaToProductMap.objects.filter(
                media_id="test_sample_image",
                business=business
            ).first()
            
            if mapping:
                print(f"   ✅ Mapping saved to database")
                print(f"   📊 Database confidence: {mapping.confidence:.3f}")
            else:
                print(f"   ❌ Mapping not saved to database")
        
        elif result.get('candidates'):
            print(f"   📊 Found {len(result['candidates'])} candidates:")
            for i, (product_id, confidence) in enumerate(result['candidates'][:3]):
                try:
                    product = Product.objects.get(id=product_id)
                    print(f"      {i+1}. {product.name} (confidence: {confidence:.3f})")
                except Product.DoesNotExist:
                    print(f"      {i+1}. Product {product_id} not found (confidence: {confidence:.3f})")
        
        else:
            print(f"   ❌ No matches found")
            if result.get('error'):
                print(f"   Error: {result['error']}")
        
        print("\n✅ Test completed!")
        
    except Exception as e:
        print(f"❌ Error during testing: {str(e)}")
        import traceback
        traceback.print_exc()


def show_mappings():
    """Show all media-to-product mappings."""
    print("\n📋 Media-to-Product Mappings:")
    print("=" * 50)
    
    mappings = MediaToProductMap.objects.select_related('product', 'business').all()
    
    if not mappings.exists():
        print("No mappings found.")
        return
    
    for mapping in mappings:
        print(f"Media ID: {mapping.media_id}")
        print(f"Business: {mapping.business.name}")
        print(f"Product: {mapping.product.name}")
        print(f"Confidence: {mapping.confidence:.3f}")
        print(f"Created: {mapping.created_at}")
        print("-" * 30)


if __name__ == "__main__":
    test_image_matching()
    show_mappings()
