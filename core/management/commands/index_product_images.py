"""
Management command to index product images by generating OpenAI embeddings.

Usage:
    python manage.py index_product_images
    python manage.py index_product_images --business-id 1
    python manage.py index_product_images --force
"""

import json
import logging
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.conf import settings

from core.models import Product, ProductEmbeddings
from core.image_utils import download_media, image_to_openai_embedding

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Index product images by generating OpenAI embeddings for similarity search'

    def add_arguments(self, parser):
        parser.add_argument(
            '--business-id',
            type=int,
            help='Only index products for a specific business ID'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force re-indexing of existing embeddings'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be indexed without actually doing it'
        )

    def handle(self, *args, **options):
        business_id = options.get('business_id')
        force = options.get('force', False)
        dry_run = options.get('dry_run', False)

        # Check if OpenAI API key is configured
        if not hasattr(settings, 'OPENAI_API_KEY') or not settings.OPENAI_API_KEY:
            raise CommandError('OPENAI_API_KEY not configured in settings')

        self.stdout.write(
            self.style.SUCCESS('Starting product image indexing...')
        )

        # Get products with images
        products_query = Product.objects.filter(image__isnull=False).exclude(image='')
        if business_id:
            products_query = products_query.filter(business_id=business_id)
            self.stdout.write(f'Filtering by business ID: {business_id}')

        products = products_query.select_related('business')
        total_products = products.count()

        if total_products == 0:
            self.stdout.write(
                self.style.WARNING('No products with images found to index')
            )
            return

        self.stdout.write(f'Found {total_products} products to index')

        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN MODE - No actual indexing will be performed')
            )
            for product in products:
                self.stdout.write(f'Would index: {product.name} ({product.business.name})')
            return

        indexed_count = 0
        skipped_count = 0
        error_count = 0

        for product in products:
            try:
                # Check if embedding already exists
                existing_embedding = ProductEmbeddings.objects.filter(product=product).first()
                if existing_embedding and not force:
                    self.stdout.write(
                        self.style.WARNING(f'Skipping {product.name} (already indexed)')
                    )
                    skipped_count += 1
                    continue

                self.stdout.write(f'Indexing: {product.name}')

                # Download image
                try:
                    image_content = download_media(product.image)
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'Failed to download image for {product.name}: {str(e)}')
                    )
                    error_count += 1
                    continue

                # Generate embedding
                try:
                    embedding = image_to_openai_embedding(image_content)
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'Failed to generate embedding for {product.name}: {str(e)}')
                    )
                    error_count += 1
                    continue

                # Save embedding
                try:
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
                    self.stdout.write(
                        self.style.SUCCESS(f'✓ Indexed: {product.name}')
                    )

                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'Failed to save embedding for {product.name}: {str(e)}')
                    )
                    error_count += 1

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'Unexpected error processing {product.name}: {str(e)}')
                )
                error_count += 1

        # Summary
        self.stdout.write('\n' + '='*50)
        self.stdout.write(self.style.SUCCESS('Indexing completed!'))
        self.stdout.write(f'Total products: {total_products}')
        self.stdout.write(f'Indexed: {indexed_count}')
        self.stdout.write(f'Skipped: {skipped_count}')
        self.stdout.write(f'Errors: {error_count}')

        if error_count > 0:
            self.stdout.write(
                self.style.WARNING(f'There were {error_count} errors. Check logs for details.')
            )
