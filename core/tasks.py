"""
Celery tasks for media processing and product matching.
"""

import os
import json
import tempfile
import logging
from typing import Dict, List, Optional
from django.db import transaction
from django.conf import settings
from django.core.cache import cache

from .models import Product, ProductEmbeddings, MediaToProductMap, Business
from .image_utils import (
    download_media, is_video, extract_frames, 
    process_image_for_matching, run_ocr
)

logger = logging.getLogger(__name__)

# Try to import Celery, fall back to synchronous execution if not available
try:
    from celery import shared_task
    CELERY_AVAILABLE = True
except ImportError:
    logger.warning("Celery not available, running tasks synchronously")
    CELERY_AVAILABLE = False
    
    # Create a mock decorator for when Celery is not available
    def shared_task(func):
        return func


@shared_task(bind=True, max_retries=3)
def process_media(self, media_url: str, business_id: int, media_id: Optional[str] = None, sender_id: Optional[str] = None, thumbnail_url: Optional[str] = None) -> Dict:
    """
    Process media (image/video) and match it to products.
    
    Args:
        media_url: URL of the media to process
        business_id: Business ID to search within
        media_id: Optional media identifier (e.g., Instagram media ID)
        sender_id: Optional sender identifier
        
    Returns:
        Dict: Processing results with matches and confidence scores
    """
    try:
        logger.info(f"Processing media: {media_url} for business {business_id}")
        # Short-term idempotency by media URL per sender
        try:
            if sender_id:
                cache_key_media = f"ig_media_seen:{sender_id}:{hash(media_url)}"
                if cache.get(cache_key_media):
                    logger.info("Skipping duplicate media_url processing within window")
                    return {
                        'success': False,
                        'error': 'duplicate_media_skipped',
                        'matched': False
                    }
                cache.set(cache_key_media, True, timeout=180)
        except Exception:
            pass
        
        # Download media
        media_content = download_media(media_url)
        
        # Determine if it's a video (by content or URL extension)
        url_is_video = False
        try:
            clean_url = media_url.split('?')[0].lower()
            url_is_video = clean_url.endswith(('.mp4', '.mov', '.m4v', '.avi', '.webm'))
        except Exception:
            url_is_video = False
        
        if is_video(media_content) or url_is_video:
            logger.info("Processing video, extracting frames")
            result = process_video_media(media_content, business_id, media_id)
            # Fallback: if frame extraction failed and we have a thumbnail_url, try processing the thumbnail as image
            if not result.get('success') and 'Failed to extract frames' in str(result.get('error', '')) and thumbnail_url:
                try:
                    thumb_bytes = download_media(thumbnail_url)
                    logger.info("Falling back to reel/story thumbnail for matching")
                    result = process_image_media(thumb_bytes, business_id, media_id)
                except Exception as _:
                    pass
        else:
            logger.info("Processing image")
            result = process_image_media(media_content, business_id, media_id)
        
        # If sender_id is provided, send a response
        if sender_id:
            send_media_match_response(business_id, sender_id, result)
        
        return result
            
    except Exception as e:
        logger.error(f"Media processing failed: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'matched': False
        }


def process_video_media(video_content: bytes, business_id: int, media_id: Optional[str] = None) -> Dict:
    """
    Process video media by extracting frames and analyzing each.
    
    Args:
        video_content: Video content as bytes
        business_id: Business ID to search within
        media_id: Optional media identifier
        
    Returns:
        Dict: Processing results
    """
    try:
        # Save video to temporary file
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_file:
            temp_file.write(video_content)
            temp_video_path = temp_file.name
        
        try:
            # Extract frames
            frames = extract_frames(temp_video_path, n=3)
            
            if not frames:
                return {
                    'success': False,
                    'error': 'Failed to extract frames from video',
                    'matched': False
                }
            
            # Process each frame
            best_match = None
            best_confidence = 0.0
            all_candidates = []
            
            for i, frame_bytes in enumerate(frames):
                logger.info(f"Processing frame {i+1}/{len(frames)}")
                
                result = process_image_for_matching(frame_bytes, business_id)
                
                if result['confidence'] > best_confidence:
                    best_match = result
                    best_confidence = result['confidence']
                
                # Collect all candidates
                all_candidates.extend(result.get('candidates', []))
            
            # Aggregate results
            if best_match and best_match['matched']:
                # Auto-match found
                return save_media_mapping(
                    media_id or f"video_{business_id}_{len(frames)}frames",
                    best_match['product_id'],
                    business_id,
                    best_confidence
                )
            else:
                # Return ambiguous results
                return {
                    'success': True,
                    'matched': False,
                    'status': 'ambiguous',
                    'confidence': best_confidence,
                    'candidates': sorted(set(all_candidates), key=lambda x: x[1], reverse=True)[:5]
                }
                
        finally:
            # Clean up temporary file
            os.unlink(temp_video_path)
            
    except Exception as e:
        logger.error(f"Video processing failed: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'matched': False
        }


def process_image_media(image_content: bytes, business_id: int, media_id: Optional[str] = None) -> Dict:
    """
    Process image media and find matching products.
    
    Args:
        image_content: Image content as bytes
        business_id: Business ID to search within
        media_id: Optional media identifier
        
    Returns:
        Dict: Processing results
    """
    try:
        # Process image for matching
        result = process_image_for_matching(image_content, business_id)
        
        if result['matched']:
            # Auto-match found, save mapping
            return save_media_mapping(
                media_id or f"image_{business_id}_{hash(image_content) % 10000}",
                result['product_id'],
                business_id,
                result['confidence']
            )
        else:
            # Return ambiguous results
            return {
                'success': True,
                'matched': False,
                'status': result['status'],
                'confidence': result['confidence'],
                'candidates': result['candidates']
            }
            
    except Exception as e:
        logger.error(f"Image processing failed: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'matched': False
        }


def save_media_mapping(media_id: str, product_id: int, business_id: int, confidence: float) -> Dict:
    """
    Save media to product mapping in database.
    
    Args:
        media_id: Media identifier
        product_id: Product ID
        business_id: Business ID
        confidence: Similarity confidence score
        
    Returns:
        Dict: Success result
    """
    try:
        with transaction.atomic():
            # Create or update mapping
            mapping, created = MediaToProductMap.objects.update_or_create(
                media_id=media_id,
                business_id=business_id,
                defaults={
                    'product_id': product_id,
                    'confidence': confidence
                }
            )
            
            action = 'created' if created else 'updated'
            logger.info(f"Media mapping {action}: {media_id} -> Product {product_id} (confidence: {confidence:.3f})")
            
            return {
                'success': True,
                'matched': True,
                'product_id': product_id,
                'confidence': confidence,
                'mapping_id': mapping.id,
                'action': action
            }
            
    except Exception as e:
        logger.error(f"Failed to save media mapping: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'matched': False
        }


@shared_task
def index_product_images(business_id: Optional[int] = None) -> Dict:
    """
    Index product images by generating embeddings.
    
    Args:
        business_id: Optional business ID to limit indexing to specific business
        
    Returns:
        Dict: Indexing results
    """
    try:
        from .image_utils import download_media, image_to_openai_embedding
        
        logger.info(f"Starting product image indexing for business {business_id or 'all'}")
        
        # Get products with images
        products_query = Product.objects.filter(image__isnull=False).exclude(image='')
        if business_id:
            products_query = products_query.filter(business_id=business_id)
        
        products = products_query.select_related('business')
        
        indexed_count = 0
        error_count = 0
        
        for product in products:
            try:
                # Download image
                image_content = download_media(product.image)
                
                # Generate embedding
                embedding = image_to_openai_embedding(image_content)
                
                # Save embedding
                with transaction.atomic():
                    ProductEmbeddings.objects.update_or_create(
                        product=product,
                        defaults={
                            'business': product.business,
                            'image_url': product.image,
                            'embedding': json.dumps(embedding)
                        }
                    )
                
                indexed_count += 1
                logger.info(f"Indexed product: {product.name}")
                
            except Exception as e:
                error_count += 1
                logger.error(f"Failed to index product {product.name}: {str(e)}")
        
        logger.info(f"Indexing completed: {indexed_count} indexed, {error_count} errors")
        
        return {
            'success': True,
            'indexed_count': indexed_count,
            'error_count': error_count,
            'total_products': products.count()
        }
        
    except Exception as e:
        logger.error(f"Product indexing failed: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }


def send_media_match_response(business_id: int, sender_id: str, match_result: Dict):
    """
    Send a response to the customer based on media matching results.
    
    Args:
        business_id: Business ID
        sender_id: Instagram sender ID
        match_result: Result from media processing
    """
    try:
        from .models import Business, Product, MessageLog
        from .instagram_api import send_instagram_text_reply
        
        business = Business.objects.get(id=business_id)
        
        # Generate response based on matching result
        if match_result.get('matched'):
            # Auto-match found
            product = Product.objects.get(id=match_result['product_id'])
            confidence = match_result['confidence']
            
            # Natural response without "AI" markers
            response = f"This is our {product.name} - ${product.price_usd:.2f}"
            
            if product.description:
                response += f"\n\n{product.description}"
            else:
                response += "\n\nLet me know if you'd like to order!"
            
            logger.info(f"Sending match response: {response}")
        elif match_result.get('candidates'):
            # Ambiguous match - show top candidates
            candidates = match_result['candidates'][:3]
            response = "I found a few similar options:\n\n"
            
            for i, (prod_id, similarity) in enumerate(candidates, 1):
                product = Product.objects.get(id=prod_id)
                response += f"{i}. {product.name} - ${product.price_usd:.2f}\n"
            
            response += "\nWhich one were you interested in?"
            logger.info(f"Sending ambiguous match response with {len(candidates)} candidates")
        else:
            # No match found
            response = "I'm not seeing an exact match in our inventory. "
            response += "Can you tell me a bit more about what you're looking for?"
            
            logger.info("Sending no match response")
        
        # Send response via Instagram API
        # Dedup: avoid resending identical response within the last 90 seconds
        try:
            from django.utils import timezone
            from datetime import timedelta
            recent_time = timezone.now() - timedelta(seconds=90)
            recent_same = MessageLog.objects.filter(
                business=business,
                sender_id=sender_id,
                reply_text=response,
                direction='outgoing',
                created_at__gte=recent_time
            ).exists()
            if recent_same:
                logger.info("Skipping duplicate response send within 90s window")
                return
        except Exception as _:
            # If dedup check fails, proceed with best effort send
            pass

        send_result = send_instagram_text_reply(
            business.page_access_token,
            sender_id,
            response
        )
        
        # Log the response
        MessageLog.objects.create(
            business=business,
            sender_id=sender_id,
            reply_text=response,
            direction='outgoing',
            error_message=send_result.get('error') if not send_result.get('success') else None
        )
        
        if send_result.get('success'):
            logger.info(f"Successfully sent media match response to {sender_id}")
        else:
            logger.error(f"Failed to send media match response: {send_result.get('error')}")
            
    except Exception as e:
        logger.error(f"Failed to send media match response: {str(e)}")
