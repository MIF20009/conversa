# Image/Video → Product Matching Feature

This document describes the implementation of the image/video to product matching feature in the Conversa AI Django application.

## Overview

The system enables automatic matching of media (images, videos, stories, reels, ads, or user-uploaded pictures) to products in your catalog using OpenAI image embeddings and pgvector similarity search.

## Features

- **Automatic Media Processing**: Processes images and videos from Instagram webhooks
- **OpenAI Embeddings**: Uses OpenAI's text-embedding-3-large model for image embeddings
- **Vector Similarity Search**: Uses pgvector for efficient nearest-neighbor search
- **Background Processing**: Celery tasks for non-blocking media processing
- **Confidence Scoring**: Configurable thresholds for auto-matching vs manual review
- **Video Support**: Extracts frames from videos for analysis
- **OCR Support**: Optional text extraction for SKU/product identification

## Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Enable pgvector Extension

```sql
-- Connect to your PostgreSQL database and run:
CREATE EXTENSION IF NOT EXISTS vector;
```

### 3. Run Migrations

```bash
python manage.py migrate
```

### 4. Install System Dependencies

- **ffmpeg**: Required for video processing
  - Ubuntu/Debian: `sudo apt install ffmpeg`
  - macOS: `brew install ffmpeg`
  - Windows: Download from https://ffmpeg.org/download.html

- **tesseract**: Optional, for OCR functionality
  - Ubuntu/Debian: `sudo apt install tesseract-ocr`
  - macOS: `brew install tesseract`
  - Windows: Download from https://github.com/UB-Mannheim/tesseract/wiki

### 5. Configure Environment Variables

Add these to your `.env` file:

```env
# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key_here

# Celery Configuration (optional, defaults to local Redis)
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

### 6. Index Product Images

```bash
# Index all product images
python manage.py index_product_images

# Index for specific business
python manage.py index_product_images --business-id 1

# Force re-indexing
python manage.py index_product_images --force

# Dry run (see what would be indexed)
python manage.py index_product_images --dry-run
```

### 7. Start Celery Worker

```bash
celery -A conversa_ai worker -l info
```

## Usage

### Automatic Processing

The system automatically processes media when:

1. Instagram webhook receives a message with media attachments
2. Media is sent to the business's Instagram account
3. The webhook enqueues a Celery task for background processing

### Manual Testing

Use the test script to manually test the system:

```bash
python scripts/test_match.py
```

### Admin Interface

Access the Django admin to:

- View and manage product embeddings
- View and correct media-to-product mappings
- Re-index product images for specific businesses

## Configuration

### Confidence Thresholds

Edit these settings in `settings.py` or `core/image_utils.py`:

```python
IMAGE_MATCH_HIGH_CONFIDENCE = 0.70  # Auto-match threshold
IMAGE_MATCH_LOW_CONFIDENCE = 0.55   # Manual review threshold
```

### Matching Logic

- **High Confidence (≥0.70)**: Automatically creates mapping
- **Medium Confidence (0.55-0.70)**: Requires manual review
- **Low Confidence (<0.55)**: Marked as ambiguous

## Database Schema

### ProductEmbeddings Table

```sql
CREATE TABLE product_embeddings (
    id BIGSERIAL PRIMARY KEY,
    product_id BIGINT UNIQUE REFERENCES core_product(id),
    business_id BIGINT REFERENCES core_business(id),
    image_url VARCHAR(500),
    embedding TEXT,  -- JSON string
    embedding_vector vector(1536),  -- pgvector column
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### MediaToProductMap Table

```sql
CREATE TABLE media_to_product_map (
    id BIGSERIAL PRIMARY KEY,
    media_id VARCHAR(255),
    product_id BIGINT REFERENCES core_product(id),
    business_id BIGINT REFERENCES core_business(id),
    confidence FLOAT,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(media_id, business_id)
);
```

## API Reference

### Celery Tasks

#### `process_media(media_url, business_id, media_id=None, sender_id=None)`

Processes media and finds matching products.

**Parameters:**
- `media_url`: URL of the media to process
- `business_id`: Business ID to search within
- `media_id`: Optional media identifier
- `sender_id`: Optional sender identifier

**Returns:**
```python
{
    'success': True,
    'matched': True,
    'product_id': 123,
    'confidence': 0.85,
    'mapping_id': 456,
    'action': 'created'
}
```

#### `index_product_images(business_id=None)`

Indexes product images by generating embeddings.

**Parameters:**
- `business_id`: Optional business ID to limit indexing

**Returns:**
```python
{
    'success': True,
    'indexed_count': 10,
    'error_count': 0,
    'total_products': 10
}
```

### Utility Functions

#### `image_to_openai_embedding(image_bytes)`

Generates OpenAI embedding for image bytes.

#### `calculate_similarity(embedding1, embedding2)`

Calculates cosine similarity between two embeddings.

#### `find_similar_products(query_embedding, business_id, limit=10)`

Finds similar products using pgvector similarity search.

## Testing

### Unit Tests

Run the unit tests:

```bash
python manage.py test core.tests.test_image_matching
```

### Integration Testing

1. Add products with images to your business
2. Run the indexing command
3. Use the test script to process sample images
4. Check the admin interface for mappings

## Troubleshooting

### Common Issues

1. **pgvector extension not enabled**
   - Solution: Run `CREATE EXTENSION IF NOT EXISTS vector;` in PostgreSQL

2. **OpenAI API key not configured**
   - Solution: Add `OPENAI_API_KEY` to your `.env` file

3. **Celery worker not running**
   - Solution: Start Celery worker with `celery -A conversa_ai worker -l info`

4. **ffmpeg not found**
   - Solution: Install ffmpeg system package

5. **No embeddings generated**
   - Solution: Check OpenAI API key and run indexing command

### Logging

The system provides detailed logging for debugging:

- Media download and processing
- Embedding generation
- Similarity search results
- Mapping creation
- Error conditions

Check your Django logs for detailed information.

## Performance Considerations

- **Index Size**: pgvector indexes work best with 100-1000 lists for ivfflat
- **Batch Processing**: Index multiple products at once for better performance
- **Memory Usage**: Large images may require more memory for processing
- **API Limits**: Respect OpenAI API rate limits

## Security Considerations

- Store OpenAI API keys securely in environment variables
- Validate media URLs before processing
- Implement rate limiting for webhook endpoints
- Monitor for suspicious media processing requests

## Future Enhancements

- Support for additional embedding models
- Real-time similarity search API
- Batch media processing
- Advanced OCR for product text extraction
- Multi-modal embeddings (image + text)
- Custom confidence thresholds per business
