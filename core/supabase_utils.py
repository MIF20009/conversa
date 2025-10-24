"""
Supabase utility functions for image uploads
"""
import os
import uuid
import requests
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

def get_supabase_headers():
    """Get Supabase headers for API requests"""
    if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
        raise ValueError("Supabase URL and KEY must be configured in environment variables")
    
    return {
        'Authorization': f'Bearer {settings.SUPABASE_KEY}',
        'Content-Type': 'application/json'
    }

def upload_image_to_supabase(image_file, product_id=None):
    """
    Upload image file to Supabase storage bucket
    
    Args:
        image_file: Django uploaded file object
        product_id: Optional product ID for file naming
        
    Returns:
        dict: {'success': bool, 'url': str, 'error': str}
    """
    try:
        # Generate unique filename
        file_extension = os.path.splitext(image_file.name)[1].lower()
        if not file_extension:
            file_extension = '.jpg'  # Default to jpg if no extension
        
        # Create unique filename
        unique_id = str(uuid.uuid4())
        if product_id:
            filename = f"product_{product_id}_{unique_id}{file_extension}"
        else:
            filename = f"product_{unique_id}{file_extension}"
        
        # Read file content
        image_file.seek(0)  # Reset file pointer
        file_content = image_file.read()
        
        # Upload to Supabase storage using direct HTTP request
        bucket_name = settings.SUPABASE_BUCKET
        file_path = f"products/{filename}"
        
        upload_url = f"{settings.SUPABASE_URL}/storage/v1/object/{bucket_name}/{file_path}"
        
        headers = {
            'Authorization': f'Bearer {settings.SUPABASE_KEY}',
            'Content-Type': image_file.content_type or 'image/jpeg'
        }
        
        response = requests.post(upload_url, data=file_content, headers=headers)
        
        if response.status_code not in [200, 201]:
            logger.error(f"Supabase upload error: {response.status_code} - {response.text}")
            return {
                'success': False,
                'url': None,
                'error': f"Upload failed: {response.status_code} - {response.text}"
            }
        
        # Get public URL
        public_url = f"{settings.SUPABASE_URL}/storage/v1/object/public/{bucket_name}/{file_path}"
        
        logger.info(f"Successfully uploaded image to Supabase: {public_url}")
        
        return {
            'success': True,
            'url': public_url,
            'error': None
        }
        
    except Exception as e:
        logger.error(f"Error uploading image to Supabase: {str(e)}")
        return {
            'success': False,
            'url': None,
            'error': str(e)
        }

def delete_image_from_supabase(image_url):
    """
    Delete image from Supabase storage
    
    Args:
        image_url: Public URL of the image to delete
        
    Returns:
        dict: {'success': bool, 'error': str}
    """
    try:
        # Extract file path from URL
        # URL format: https://[project].supabase.co/storage/v1/object/public/[bucket]/[path]
        if '/storage/v1/object/public/' not in image_url:
            return {
                'success': False,
                'error': 'Invalid Supabase URL format'
            }
        
        # Extract path after the bucket name
        parts = image_url.split('/storage/v1/object/public/')
        if len(parts) != 2:
            return {
                'success': False,
                'error': 'Could not extract file path from URL'
            }
        
        full_path = parts[1]
        bucket_name = settings.SUPABASE_BUCKET
        
        # Remove bucket name from path if it's included
        if full_path.startswith(f"{bucket_name}/"):
            file_path = full_path[len(f"{bucket_name}/"):]
        else:
            file_path = full_path
        
        # Delete from Supabase storage using direct HTTP request
        delete_url = f"{settings.SUPABASE_URL}/storage/v1/object/{bucket_name}/{file_path}"
        
        headers = {
            'Authorization': f'Bearer {settings.SUPABASE_KEY}',
            'Content-Type': 'application/json'
        }
        
        response = requests.delete(delete_url, headers=headers)
        
        if response.status_code not in [200, 204]:
            logger.error(f"Supabase delete error: {response.status_code} - {response.text}")
            return {
                'success': False,
                'error': f"Delete failed: {response.status_code} - {response.text}"
            }
        
        logger.info(f"Successfully deleted image from Supabase: {file_path}")
        
        return {
            'success': True,
            'error': None
        }
        
    except Exception as e:
        logger.error(f"Error deleting image from Supabase: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }
