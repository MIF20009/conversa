"""
Image and video processing utilities for product matching.

This module provides utilities for:
- Downloading media from URLs
- Detecting video files and extracting frames
- Generating OpenAI embeddings for images
- Running OCR on images
- Similarity search using pgvector

Setup Instructions:
1. Enable pgvector in PostgreSQL: CREATE EXTENSION IF NOT EXISTS vector;
2. Run migrations: python manage.py migrate
3. Install ffmpeg system package
4. Index product images: python manage.py index_product_images
5. Start Celery worker: celery -A conversa_ai worker -l info
"""

import os
import io
import json
import logging
import requests
from typing import List, Optional, Tuple, Union
from PIL import Image
import ffmpeg
from openai import OpenAI
from django.conf import settings

logger = logging.getLogger(__name__)

# Configuration settings
# NOTE: These thresholds are higher because we're using text embeddings from image descriptions,
# which may not be as accurate as true visual embeddings
IMAGE_MATCH_HIGH_CONFIDENCE = 0.85  # Increased from 0.70 for better accuracy
IMAGE_MATCH_LOW_CONFIDENCE = 0.70   # Increased from 0.55
EMBEDDING_DIMENSION = 1536  # OpenAI text-embedding-3-large dimension


def download_media(url: str, timeout: int = 30) -> bytes:
    """
    Download media from URL and return as bytes.
    
    Args:
        url: URL to download from
        timeout: Request timeout in seconds
        
    Returns:
        bytes: Downloaded media content
        
    Raises:
        requests.RequestException: If download fails
    """
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return response.content
    except requests.RequestException as e:
        logger.error(f"Failed to download media from {url}: {str(e)}")
        raise


def is_video(content_or_url: Union[bytes, str]) -> bool:
    """
    Check if content or URL points to a video file.
    
    Args:
        content_or_url: Either bytes content or URL string
        
    Returns:
        bool: True if content is video
    """
    if isinstance(content_or_url, str):
        # Check URL extension
        video_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv'}
        url_lower = content_or_url.lower()
        return any(url_lower.endswith(ext) for ext in video_extensions)
    
    # Check content type from bytes
    if content_or_url.startswith(b'\x00\x00\x00\x18ftypmp42'):
        return True  # MP4
    elif content_or_url.startswith(b'\x00\x00\x00\x20ftypmp42'):
        return True  # MP4
    elif content_or_url.startswith(b'RIFF') and b'WEBM' in content_or_url[:20]:
        return True  # WEBM
    elif content_or_url.startswith(b'\x1a\x45\xdf\xa3'):
        return True  # Matroska/MKV
    
    return False


def extract_frames(video_path: str, n: int = 3) -> List[bytes]:
    """
    Extract n frames evenly distributed across video duration.
    
    Args:
        video_path: Path to video file
        n: Number of frames to extract
        
    Returns:
        List[bytes]: List of frame images as bytes
    """
    try:
        # Get video duration
        probe = ffmpeg.probe(video_path)
        duration = float(probe['streams'][0]['duration'])
        
        frames = []
        for i in range(n):
            # Calculate timestamp for evenly distributed frames
            timestamp = (duration / (n + 1)) * (i + 1)
            
            # Extract frame
            out, _ = (
                ffmpeg
                .input(video_path, ss=timestamp)
                .output('pipe:', vframes=1, format='image2', vcodec='png')
                .run(capture_stdout=True, quiet=True)
            )
            frames.append(out)
            
        return frames
    except Exception as e:
        logger.error(f"Failed to extract frames from video {video_path}: {str(e)}")
        return []


def image_to_openai_embedding(image_bytes: bytes) -> List[float]:
    """
    Generate OpenAI embedding for image bytes.
    
    Note: OpenAI doesn't have a dedicated image embedding model.
    We'll use a workaround: first get a text description using vision model,
    then generate embedding from that description.
    
    Args:
        image_bytes: Image content as bytes
        
    Returns:
        List[float]: Embedding vector
        
    Raises:
        Exception: If embedding generation fails
    """
    try:
        import base64
        
        # Detect image format and convert if necessary
        try:
            img = Image.open(io.BytesIO(image_bytes))
            format_map = {
                'PNG': 'png',
                'JPEG': 'jpeg',
                'JPG': 'jpeg',
                'GIF': 'gif',
                'WEBP': 'webp'
            }
            detected_format = format_map.get(img.format.upper(), 'jpeg')
            
            # If format is not supported by OpenAI (like AVIF), convert to JPEG
            if img.format.upper() not in ['PNG', 'JPEG', 'JPG', 'GIF', 'WEBP']:
                logger.info(f"Converting unsupported format {img.format} to JPEG")
                # Convert to RGB if necessary (AVIF, RGBA, etc.)
                if img.mode in ('RGBA', 'LA', 'P'):
                    # Create a white background
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                    img = background
                elif img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Save as JPEG bytes
                output = io.BytesIO()
                img.save(output, format='JPEG', quality=95)
                image_bytes = output.getvalue()
                detected_format = 'jpeg'
                logger.info(f"Converted to JPEG successfully")
                
        except Exception as e:
            logger.warning(f"Image format detection failed: {str(e)}, trying pillow with specific format")
            # Try to force open as a specific format
            try:
                # Try to open as JPEG (most common)
                img = Image.open(io.BytesIO(image_bytes))
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                output = io.BytesIO()
                img.save(output, format='JPEG', quality=95)
                image_bytes = output.getvalue()
                detected_format = 'jpeg'
                logger.info("Successfully converted to JPEG")
            except Exception as e2:
                logger.error(f"Failed to convert image: {str(e2)}")
                logger.error("Using fallback: will skip vision model")
                # Set a flag to skip vision model
                detected_format = 'jpeg'  # Will fail but won't crash
        
        # Create base64 encoded image
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        
        # Initialize OpenAI client
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        
        # Step 1: Get image description using vision model
        try:
            response = client.chat.completions.create(
                model="gpt-4o",  # Use GPT-4o which supports images
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Describe this product image in detail. Include: specific brand names/logo if visible, exact colors, distinctive features (e.g., 'Air Jordan 1' or 'Adidas three stripes'), shoe type/style, and any unique characteristics. Be very specific."},
                            {"type": "image_url", "image_url": {"url": f"data:image/{detected_format};base64,{image_base64}"}}
                        ]
                    }
                ],
                max_tokens=300
            )
            
            description = response.choices[0].message.content
            logger.info(f"Generated image description: {description[:100]}...")
            
        except Exception as e:
            logger.warning(f"Vision model failed, using fallback: {str(e)}")
            # Fallback: use a generic description
            description = "product image"
        
        # Step 2: Generate embedding from description with explicit dimension
        embedding_response = client.embeddings.create(
            model="text-embedding-3-large",
            input=description,
            dimensions=1536  # Explicitly set dimension to 1536
        )
        
        embedding = embedding_response.data[0].embedding
        
        logger.info(f"Generated embedding of dimension {len(embedding)}")
        
        return embedding
        
    except Exception as e:
        logger.error(f"Failed to generate embedding: {str(e)}")
        raise


def run_ocr(image_bytes: bytes) -> str:
    """
    Run OCR on image to extract text.
    
    Args:
        image_bytes: Image content as bytes
        
    Returns:
        str: Extracted text
    """
    try:
        import pytesseract
        from PIL import Image
        
        # Convert bytes to PIL Image
        image = Image.open(io.BytesIO(image_bytes))
        
        # Run OCR
        text = pytesseract.image_to_string(image)
        
        return text.strip()
    except ImportError:
        logger.warning("pytesseract not installed, skipping OCR")
        return ""
    except Exception as e:
        logger.error(f"OCR failed: {str(e)}")
        return ""


def calculate_similarity(embedding1: List[float], embedding2: List[float]) -> float:
    """
    Calculate cosine similarity between two embeddings.
    
    Args:
        embedding1: First embedding vector
        embedding2: Second embedding vector
        
    Returns:
        float: Similarity score (0.0 to 1.0)
    """
    import numpy as np
    
    # Convert to numpy arrays
    vec1 = np.array(embedding1)
    vec2 = np.array(embedding2)
    
    # Calculate cosine similarity
    dot_product = np.dot(vec1, vec2)
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    similarity = dot_product / (norm1 * norm2)
    return float(similarity)


def find_similar_products(query_embedding: List[float], business_id: int, limit: int = 10) -> List[Tuple[int, float]]:
    """
    Find similar products using pgvector similarity search.
    
    Args:
        query_embedding: Query embedding vector
        business_id: Business ID to filter by
        limit: Maximum number of results
        
    Returns:
        List[Tuple[int, float]]: List of (product_id, similarity_score) tuples
    """
    from django.db import connection
    
    try:
        with connection.cursor() as cursor:
            # Convert embedding to PostgreSQL array format
            embedding_str = '[' + ','.join(map(str, query_embedding)) + ']'
            
            # Query using pgvector cosine similarity operator (<=>)
            query = """
                SELECT product_id, 
                       (1 - (embedding::vector <=> %s::vector)) as similarity
                FROM product_embeddings 
                WHERE business_id = %s 
                ORDER BY embedding::vector <=> %s::vector 
                LIMIT %s
            """
            
            cursor.execute(query, [embedding_str, business_id, embedding_str, limit])
            results = cursor.fetchall()
            
            return [(row[0], float(row[1])) for row in results]
            
    except Exception as e:
        logger.error(f"Similarity search failed: {str(e)}")
        return []


def process_image_for_matching(image_bytes: bytes, business_id: int) -> dict:
    """
    Process an image and find matching products.
    
    Args:
        image_bytes: Image content as bytes
        business_id: Business ID to search within
        
    Returns:
        dict: Matching results with candidates and confidence
    """
    try:
        # Generate embedding for the image
        embedding = image_to_openai_embedding(image_bytes)
        
        # Find similar products
        similar_products = find_similar_products(embedding, business_id, limit=5)
        
        if not similar_products:
            return {
                'matched': False,
                'candidates': [],
                'confidence': 0.0,
                'status': 'no_matches'
            }
        
        # Get best match
        best_product_id, best_similarity = similar_products[0]
        
        # Determine confidence level
        if best_similarity >= IMAGE_MATCH_HIGH_CONFIDENCE:
            status = 'auto_match'
            matched = True
        elif best_similarity >= IMAGE_MATCH_LOW_CONFIDENCE:
            status = 'manual_review'
            matched = False
        else:
            status = 'ambiguous'
            matched = False
        
        # Check if there are multiple close candidates
        if len(similar_products) > 1:
            second_best_similarity = similar_products[1][1]
            if best_similarity - second_best_similarity < 0.05:
                status = 'ambiguous'
                matched = False
        
        return {
            'matched': matched,
            'product_id': best_product_id if matched else None,
            'confidence': best_similarity,
            'status': status,
            'candidates': similar_products[:3]  # Top 3 candidates
        }
        
    except Exception as e:
        logger.error(f"Image processing failed: {str(e)}")
        return {
            'matched': False,
            'candidates': [],
            'confidence': 0.0,
            'status': 'error',
            'error': str(e)
        }
