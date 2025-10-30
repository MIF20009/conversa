"""
Django signals for automatic embedding generation when products are saved/updated.
"""

import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings

from .models import Product, ProductEmbeddings
from .image_utils import download_media, image_to_openai_embedding
from .tasks import index_product_images

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Product)
def generate_product_embedding(sender, instance, created, **kwargs):
    """
    Automatically generate and store embedding when a product is created or updated.
    
    Only generates embedding if:
    - Product has an image URL
    - OpenAI API key is configured
    - Celery is available (runs async)
    """
    # Skip if no image URL
    if not instance.image:
        logger.debug(f"No image URL for product {instance.name}, skipping embedding")
        return
    
    # Check if OpenAI is configured
    if not hasattr(settings, 'OPENAI_API_KEY') or not settings.OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not configured, skipping embedding generation")
        return
    
    # Check if image URL has changed (for updates)
    if not created:
        try:
            existing = instance.embedding
            if existing and existing.image_url == instance.image:
                logger.debug(f"Image URL unchanged for product {instance.name}, skipping embedding")
                return
        except ProductEmbeddings.DoesNotExist:
            pass  # No existing embedding, proceed to create
    
    # Run embedding generation asynchronously or synchronously
    try:
        if hasattr(settings, 'CELERY_BROKER_URL') and settings.CELERY_BROKER_URL:
            logger.info(f"Enqueuing embedding task for product {instance.name}")
            index_product_images.delay(business_id=instance.business_id)
        else:
            # Run synchronously if Celery not configured
            logger.warning("Celery not configured, running embedding generation synchronously")
            _generate_embedding_sync(instance)
    except Exception as e:
        logger.error(f"Failed to enqueue embedding task for product {instance.name}: {str(e)}")
        # Fall back to synchronous generation
        _generate_embedding_sync(instance)


def _generate_embedding_sync(product):
    """
    Generate embedding synchronously (fallback when Celery is not available).
    """
    try:
        logger.info(f"Generating embedding for product {product.name}")
        
        # Download image
        image_content = download_media(product.image)
        
        # Generate embedding
        embedding = image_to_openai_embedding(image_content)
        
        # Save embedding
        import json
        ProductEmbeddings.objects.update_or_create(
            product=product,
            defaults={
                'business': product.business,
                'image_url': product.image,
                'embedding': json.dumps(embedding)
            }
        )
        
        logger.info(f"Successfully generated embedding for product {product.name}")
        
    except Exception as e:
        logger.error(f"Failed to generate embedding for product {product.name}: {str(e)}")

