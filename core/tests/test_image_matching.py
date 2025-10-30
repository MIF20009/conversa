"""
Unit tests for image matching functionality.
"""

import json
import unittest
from unittest.mock import patch, MagicMock, mock_open
from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings

from core.models import Business, Product, ProductEmbeddings, MediaToProductMap
from core.image_utils import (
    image_to_openai_embedding, 
    calculate_similarity,
    process_image_for_matching
)
from core.tasks import process_media, index_product_images
from core.management.commands.index_product_images import Command


class ImageMatchingTestCase(TestCase):
    """Test cases for image matching functionality."""
    
    def setUp(self):
        """Set up test data."""
        self.business = Business.objects.create(
            name="Test Business",
            owner_id=1,  # Assuming user ID 1 exists
            active=True,
            ai_enabled=True
        )
        
        self.product = Product.objects.create(
            name="Test Product",
            business=self.business,
            price_usd=10.00,
            image="https://example.com/product.jpg"
        )
        
        # Mock embedding vector (1536 dimensions)
        self.mock_embedding = [0.1] * 1536
        
    @patch('core.image_utils.openai.OpenAI')
    def test_image_to_openai_embedding(self, mock_openai_client):
        """Test OpenAI embedding generation."""
        # Mock OpenAI response
        mock_response = MagicMock()
        mock_response.data = [MagicMock()]
        mock_response.data[0].embedding = self.mock_embedding
        mock_openai_client.return_value.embeddings.create.return_value = mock_response
        
        # Test image bytes
        image_bytes = b"fake image data"
        
        result = image_to_openai_embedding(image_bytes)
        
        self.assertEqual(result, self.mock_embedding)
        mock_openai_client.return_value.embeddings.create.assert_called_once()
    
    def test_calculate_similarity(self):
        """Test similarity calculation between embeddings."""
        embedding1 = [1.0, 0.0, 0.0]
        embedding2 = [1.0, 0.0, 0.0]
        embedding3 = [0.0, 1.0, 0.0]
        
        # Identical embeddings should have similarity of 1.0
        similarity = calculate_similarity(embedding1, embedding2)
        self.assertAlmostEqual(similarity, 1.0, places=5)
        
        # Orthogonal embeddings should have similarity of 0.0
        similarity = calculate_similarity(embedding1, embedding3)
        self.assertAlmostEqual(similarity, 0.0, places=5)
    
    @patch('core.image_utils.find_similar_products')
    def test_process_image_for_matching(self, mock_find_similar):
        """Test image processing for product matching."""
        # Mock similar products response
        mock_find_similar.return_value = [
            (self.product.id, 0.85),
            (999, 0.70),
            (998, 0.60)
        ]
        
        # Test image bytes
        image_bytes = b"fake image data"
        
        result = process_image_for_matching(image_bytes, self.business.id)
        
        self.assertTrue(result['matched'])
        self.assertEqual(result['product_id'], self.product.id)
        self.assertEqual(result['confidence'], 0.85)
        self.assertEqual(result['status'], 'auto_match')
        self.assertEqual(len(result['candidates']), 3)
    
    @patch('core.image_utils.find_similar_products')
    def test_process_image_for_matching_ambiguous(self, mock_find_similar):
        """Test image processing for ambiguous matches."""
        # Mock ambiguous similar products response
        mock_find_similar.return_value = [
            (self.product.id, 0.65),
            (999, 0.63),  # Close to top match
            (998, 0.60)
        ]
        
        image_bytes = b"fake image data"
        
        result = process_image_for_matching(image_bytes, self.business.id)
        
        self.assertFalse(result['matched'])
        self.assertEqual(result['status'], 'ambiguous')
        self.assertEqual(result['confidence'], 0.65)
    
    @patch('core.tasks.download_media')
    @patch('core.tasks.image_to_openai_embedding')
    def test_index_product_images_task(self, mock_embedding, mock_download):
        """Test product image indexing task."""
        # Mock dependencies
        mock_download.return_value = b"fake image data"
        mock_embedding.return_value = self.mock_embedding
        
        # Run the task
        result = index_product_images(self.business.id)
        
        self.assertTrue(result['success'])
        self.assertEqual(result['indexed_count'], 1)
        self.assertEqual(result['error_count'], 0)
        
        # Check that embedding was created
        embedding = ProductEmbeddings.objects.get(product=self.product)
        self.assertEqual(embedding.business, self.business)
        self.assertEqual(embedding.image_url, self.product.image)
    
    @patch('core.tasks.download_media')
    @patch('core.tasks.is_video')
    @patch('core.tasks.process_image_for_matching')
    def test_process_media_task_image(self, mock_process_image, mock_is_video, mock_download):
        """Test media processing task for images."""
        # Mock dependencies
        mock_download.return_value = b"fake image data"
        mock_is_video.return_value = False
        mock_process_image.return_value = {
            'matched': True,
            'product_id': self.product.id,
            'confidence': 0.85,
            'status': 'auto_match'
        }
        
        # Run the task
        result = process_media(
            media_url="https://example.com/image.jpg",
            business_id=self.business.id,
            media_id="test_media_id"
        )
        
        self.assertTrue(result['success'])
        self.assertTrue(result['matched'])
        self.assertEqual(result['product_id'], self.product.id)
        
        # Check that mapping was created
        mapping = MediaToProductMap.objects.get(
            media_id="test_media_id",
            business=self.business
        )
        self.assertEqual(mapping.product, self.product)
        self.assertEqual(mapping.confidence, 0.85)
    
    @patch('core.tasks.download_media')
    @patch('core.tasks.is_video')
    @patch('core.tasks.extract_frames')
    @patch('core.tasks.process_image_for_matching')
    def test_process_media_task_video(self, mock_process_image, mock_extract_frames, mock_is_video, mock_download):
        """Test media processing task for videos."""
        # Mock dependencies
        mock_download.return_value = b"fake video data"
        mock_is_video.return_value = True
        mock_extract_frames.return_value = [b"frame1", b"frame2", b"frame3"]
        mock_process_image.return_value = {
            'matched': True,
            'product_id': self.product.id,
            'confidence': 0.80,
            'status': 'auto_match'
        }
        
        # Run the task
        result = process_media(
            media_url="https://example.com/video.mp4",
            business_id=self.business.id,
            media_id="test_video_id"
        )
        
        self.assertTrue(result['success'])
        self.assertTrue(result['matched'])
        self.assertEqual(result['product_id'], self.product.id)
        
        # Check that mapping was created
        mapping = MediaToProductMap.objects.get(
            media_id="test_video_id",
            business=self.business
        )
        self.assertEqual(mapping.product, self.product)


class ManagementCommandTestCase(TestCase):
    """Test cases for management commands."""
    
    def setUp(self):
        """Set up test data."""
        self.business = Business.objects.create(
            name="Test Business",
            owner_id=1,
            active=True
        )
        
        self.product = Product.objects.create(
            name="Test Product",
            business=self.business,
            price_usd=10.00,
            image="https://example.com/product.jpg"
        )
    
    @patch('core.management.commands.index_product_images.download_media')
    @patch('core.management.commands.index_product_images.image_to_openai_embedding')
    def test_index_product_images_command(self, mock_embedding, mock_download):
        """Test the index_product_images management command."""
        # Mock dependencies
        mock_download.return_value = b"fake image data"
        mock_embedding.return_value = [0.1] * 1536
        
        # Run the command
        command = Command()
        command.handle(business_id=self.business.id)
        
        # Check that embedding was created
        embedding = ProductEmbeddings.objects.get(product=self.product)
        self.assertEqual(embedding.business, self.business)
        self.assertEqual(embedding.image_url, self.product.image)
        
        # Verify the embedding data
        embedding_data = json.loads(embedding.embedding)
        self.assertEqual(len(embedding_data), 1536)
        self.assertEqual(embedding_data[0], 0.1)
    
    def test_index_product_images_command_dry_run(self):
        """Test the index_product_images command in dry-run mode."""
        command = Command()
        
        # Should not raise an exception
        command.handle(dry_run=True)
        
        # No embeddings should be created
        self.assertEqual(ProductEmbeddings.objects.count(), 0)


if __name__ == '__main__':
    unittest.main()
