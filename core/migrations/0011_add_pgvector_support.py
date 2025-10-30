"""
Add pgvector support to ProductEmbeddings table.
This migration adds the vector column and creates the necessary indexes.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0010_productembeddings_mediatoproductmap'),
    ]

    operations = [
        # Enable pgvector extension
        migrations.RunSQL(
            "CREATE EXTENSION IF NOT EXISTS vector;",
            reverse_sql="DROP EXTENSION IF EXISTS vector;"
        ),
        
        # Add vector column to product_embeddings table
        migrations.RunSQL(
            """
            ALTER TABLE product_embeddings 
            ADD COLUMN embedding_vector vector(1536);
            """,
            reverse_sql="ALTER TABLE product_embeddings DROP COLUMN embedding_vector;"
        ),
        
        # Create index for vector similarity search (without CONCURRENTLY for compatibility)
        migrations.RunSQL(
            """
            CREATE INDEX IF NOT EXISTS product_embeddings_embedding_vector_idx 
            ON product_embeddings USING ivfflat (embedding_vector vector_cosine_ops) 
            WITH (lists = 100);
            """,
            reverse_sql="DROP INDEX IF EXISTS product_embeddings_embedding_vector_idx;"
        ),
        
        # Create function to update vector column when embedding text changes
        migrations.RunSQL(
            """
            CREATE OR REPLACE FUNCTION update_embedding_vector()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.embedding_vector = NEW.embedding::vector;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """,
            reverse_sql="DROP FUNCTION IF EXISTS update_embedding_vector();"
        ),
        
        # Create trigger to automatically update vector column
        migrations.RunSQL(
            """
            CREATE TRIGGER update_embedding_vector_trigger
                BEFORE INSERT OR UPDATE ON product_embeddings
                FOR EACH ROW
                EXECUTE FUNCTION update_embedding_vector();
            """,
            reverse_sql="DROP TRIGGER IF EXISTS update_embedding_vector_trigger ON product_embeddings;"
        ),
        
        # Update existing records to populate vector column
        migrations.RunSQL(
            """
            UPDATE product_embeddings 
            SET embedding_vector = embedding::vector 
            WHERE embedding_vector IS NULL;
            """,
            reverse_sql="UPDATE product_embeddings SET embedding_vector = NULL;"
        ),
    ]
