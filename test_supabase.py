"""
Test script for Supabase image upload functionality
Run this to test if Supabase configuration is working
"""
import os
import sys
import django
from pathlib import Path

# Add the project directory to Python path
project_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(project_dir))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'conversa_ai.settings')
django.setup()

from core.supabase_utils import get_supabase_headers, upload_image_to_supabase
from django.conf import settings

def test_supabase_connection():
    """Test if Supabase connection is working"""
    try:
        print("Testing Supabase connection...")
        
        # Check if environment variables are set
        if not settings.SUPABASE_URL:
            print("❌ SUPABASE_URL not set in environment variables")
            return False
            
        if not settings.SUPABASE_KEY:
            print("❌ SUPABASE_KEY not set in environment variables")
            return False
            
        print(f"✅ SUPABASE_URL: {settings.SUPABASE_URL}")
        print(f"✅ SUPABASE_KEY: {settings.SUPABASE_KEY[:10]}...")
        print(f"✅ SUPABASE_BUCKET: {settings.SUPABASE_BUCKET}")
        
        # Test headers creation
        headers = get_supabase_headers()
        print("✅ Supabase headers created successfully")
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing Supabase connection: {str(e)}")
        return False

def test_upload():
    """Test image upload functionality"""
    try:
        print("\nTesting image upload...")
        
        # Create a dummy file for testing
        from io import BytesIO
        from PIL import Image
        
        # Create a simple test image
        img = Image.new('RGB', (100, 100), color='red')
        img_buffer = BytesIO()
        img.save(img_buffer, format='JPEG')
        img_buffer.seek(0)
        
        # Create a mock file object
        class MockFile:
            def __init__(self, content, name="test.jpg"):
                self.content = content
                self.name = name
                self.content_type = "image/jpeg"
                
            def read(self):
                return self.content
                
            def seek(self, position):
                pass
        
        mock_file = MockFile(img_buffer.getvalue())
        
        # Test upload
        result = upload_image_to_supabase(mock_file, "test_product")
        
        if result['success']:
            print(f"✅ Upload successful: {result['url']}")
            return True
        else:
            print(f"❌ Upload failed: {result['error']}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing upload: {str(e)}")
        return False

if __name__ == "__main__":
    print("🧪 Testing Supabase Integration")
    print("=" * 40)
    
    # Test connection
    connection_ok = test_supabase_connection()
    
    if connection_ok:
        # Test upload
        upload_ok = test_upload()
        
        if upload_ok:
            print("\n🎉 All tests passed! Supabase integration is working.")
        else:
            print("\n⚠️ Connection works but upload failed. Check your Supabase bucket configuration.")
    else:
        print("\n❌ Supabase connection failed. Please check your environment variables.")
        print("\nRequired environment variables:")
        print("- SUPABASE_URL")
        print("- SUPABASE_KEY") 
        print("- SUPABASE_BUCKET (optional, defaults to 'product-images')")
