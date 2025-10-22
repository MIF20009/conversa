# Generated manually for Instagram integration

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        # Add Instagram fields to Business model - using AddField with if_not_exists logic
        migrations.RunSQL(
            """
            DO $$ 
            BEGIN
                -- Add instagram_page_id if it doesn't exist
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_name = 'core_business' AND column_name = 'instagram_page_id') THEN
                    ALTER TABLE core_business ADD COLUMN instagram_page_id VARCHAR(64) UNIQUE;
                END IF;
                
                -- Add instagram_business_account_id if it doesn't exist
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_name = 'core_business' AND column_name = 'instagram_business_account_id') THEN
                    ALTER TABLE core_business ADD COLUMN instagram_business_account_id VARCHAR(64);
                END IF;
                
                -- Add page_access_token if it doesn't exist
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_name = 'core_business' AND column_name = 'page_access_token') THEN
                    ALTER TABLE core_business ADD COLUMN page_access_token TEXT;
                END IF;
                
                -- Add page_token_expires_at if it doesn't exist
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_name = 'core_business' AND column_name = 'page_token_expires_at') THEN
                    ALTER TABLE core_business ADD COLUMN page_token_expires_at TIMESTAMP WITH TIME ZONE;
                END IF;
                
                -- Add ai_enabled if it doesn't exist
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_name = 'core_business' AND column_name = 'ai_enabled') THEN
                    ALTER TABLE core_business ADD COLUMN ai_enabled BOOLEAN DEFAULT TRUE;
                END IF;
                
                -- Add allow_auto_reply_from_unknown if it doesn't exist
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_name = 'core_business' AND column_name = 'allow_auto_reply_from_unknown') THEN
                    ALTER TABLE core_business ADD COLUMN allow_auto_reply_from_unknown BOOLEAN DEFAULT FALSE;
                END IF;
            END $$;
            """,
            reverse_sql="""
            ALTER TABLE core_business DROP COLUMN IF EXISTS instagram_page_id;
            ALTER TABLE core_business DROP COLUMN IF EXISTS instagram_business_account_id;
            ALTER TABLE core_business DROP COLUMN IF EXISTS page_access_token;
            ALTER TABLE core_business DROP COLUMN IF EXISTS page_token_expires_at;
            ALTER TABLE core_business DROP COLUMN IF EXISTS ai_enabled;
            ALTER TABLE core_business DROP COLUMN IF EXISTS allow_auto_reply_from_unknown;
            """,
        ),
        
        # Create Customer model
        migrations.CreateModel(
            name='Customer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('platform', models.CharField(choices=[('instagram', 'Instagram'), ('whatsapp', 'WhatsApp')], max_length=20)),
                ('platform_id', models.CharField(help_text='User ID from the platform', max_length=128)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('business', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='customers', to='core.business')),
            ],
            options={
                'unique_together': {('platform', 'platform_id', 'business')},
            },
        ),
        
        # Create MessageLog model
        migrations.CreateModel(
            name='MessageLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sender_id', models.CharField(blank=True, help_text='Platform sender ID if customer not found', max_length=128, null=True)),
                ('incoming_text', models.TextField(blank=True, null=True)),
                ('reply_text', models.TextField(blank=True, null=True)),
                ('direction', models.CharField(choices=[('incoming', 'Incoming'), ('outgoing', 'Outgoing')], max_length=10)),
                ('error_message', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('business', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='message_logs', to='core.business')),
                ('customer', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='message_logs', to='core.customer')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        
        # Add indexes for performance
        migrations.AddIndex(
            model_name='customer',
            index=models.Index(fields=['business', 'platform'], name='core_customer_business_platform_idx'),
        ),
        migrations.AddIndex(
            model_name='customer',
            index=models.Index(fields=['platform', 'platform_id'], name='core_customer_platform_id_idx'),
        ),
        migrations.AddIndex(
            model_name='messagelog',
            index=models.Index(fields=['business', 'created_at'], name='core_messagelog_business_created_idx'),
        ),
        migrations.AddIndex(
            model_name='messagelog',
            index=models.Index(fields=['customer', 'created_at'], name='core_messagelog_customer_created_idx'),
        ),
        migrations.AddIndex(
            model_name='messagelog',
            index=models.Index(fields=['direction', 'created_at'], name='core_messagelog_direction_created_idx'),
        ),
    ]
