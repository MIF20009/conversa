from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.urls import reverse
from django.contrib import messages
import json
import logging
from .models import Business, Product, Customer, MessageLog, Category
from django.core.cache import cache
from .forms import ProductForm, ExcelUploadForm
from .instagram_api import (
    exchange_code_for_token, exchange_short_lived_for_long_lived,
    get_user_pages, get_page_access_token, send_instagram_text_reply,
    verify_webhook_signature
)
from .ai_chat import get_ai_response
import pandas as pd

logger = logging.getLogger(__name__)

@login_required
def owner_dashboard(request):
    # show list of businesses owned by user
    businesses = request.user.businesses.all()
    
    # Add in-stock count for each business
    for business in businesses:
        business.in_stock_count = business.products.filter(stock__gt=0).count()
    
    return render(request, 'core/owner_dashboard.html', {'businesses': businesses})

@login_required
def product_list(request, business_id):
    business = get_object_or_404(Business, id=business_id, owner=request.user)
    products = business.products.select_related('category').all().order_by('-created_at')
    return render(request, 'core/product_list.html', {'business': business, 'products': products})

@login_required
def product_create(request, business_id):
    business = get_object_or_404(Business, id=business_id, owner=request.user)
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, business=business)
        if form.is_valid():
            p = form.save(commit=False)
            p.business = business
            p.save()
            messages.success(request, 'Product added.')
            return redirect('core:product_list', business_id=business.id)
    else:
        form = ProductForm(business=business)
    return render(request, 'core/product_form.html', {'form': form, 'business': business})

@login_required
def product_edit(request, business_id, product_id):
    business = get_object_or_404(Business, id=business_id, owner=request.user)
    product = get_object_or_404(Product, id=product_id, business=business)
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product, business=business)
        if form.is_valid():
            form.save()
            messages.success(request, 'Product updated.')
            return redirect('core:product_list', business_id=business.id)
    else:
        form = ProductForm(instance=product, business=business)
    return render(request, 'core/product_form.html', {'form': form, 'business': business, 'product': product})


@login_required
def product_detail(request, business_id, product_id):
    business = get_object_or_404(Business, id=business_id, owner=request.user)
    product = get_object_or_404(Product, id=product_id, business=business)
    return render(request, 'core/product_detail.html', {'business': business, 'product': product})


@login_required
def product_delete(request, business_id, product_id):
    business = get_object_or_404(Business, id=business_id, owner=request.user)
    product = get_object_or_404(Product, id=product_id, business=business)
    if request.method == 'POST':
        product.delete()
        messages.success(request, 'Product deleted.')
        return redirect('core:product_list', business_id=business.id)
    return render(request, 'core/confirm_delete.html', {'business': business, 'object': product, 'object_name': 'Product'})


@login_required
def category_list(request, business_id):
    """List categories for a business"""
    business = get_object_or_404(Business, id=business_id, owner=request.user)
    categories = business.categories.all().order_by('name')
    return render(request, 'core/category_list.html', {'business': business, 'categories': categories})


@login_required
def category_create(request, business_id):
    """Create a new category for a business"""
    business = get_object_or_404(Business, id=business_id, owner=request.user)
    
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if name:
            category, created = Category.objects.get_or_create(
                name=name,
                business=business,
                defaults={'is_global': False}
            )
            if created:
                messages.success(request, f'Category "{name}" created successfully.')
            else:
                messages.warning(request, f'Category "{name}" already exists.')
            return redirect('core:category_list', business_id=business.id)
        else:
            messages.error(request, 'Category name is required.')
    
    return render(request, 'core/category_form.html', {'business': business})


@login_required
def category_delete(request, business_id, category_id):
    """Delete a category"""
    business = get_object_or_404(Business, id=business_id, owner=request.user)
    category = get_object_or_404(Category, id=category_id, business=business)
    
    if request.method == 'POST':
        category_name = category.name
        category.delete()
        messages.success(request, f'Category "{category_name}" deleted successfully.')
        return redirect('core:category_list', business_id=business.id)
    
    return render(request, 'core/confirm_delete.html', {
        'business': business, 
        'object': category, 
        'object_name': 'Category'
    })

@login_required
def product_import_excel(request, business_id):
    business = get_object_or_404(Business, id=business_id, owner=request.user)
    
    # Handle template download
    if request.GET.get('download_template'):
        return _generate_excel_template()
    
    if request.method == 'POST':
        form = ExcelUploadForm(request.POST, request.FILES)
        if form.is_valid():
            file = request.FILES['file']
            try:
                df = pd.read_excel(file)  # expects columns: sku,name,description,price_usd,price_lbp,stock,category
            except Exception as e:
                messages.error(request, f'Error reading Excel: {e}')
                return redirect('core:product_list', business_id=business.id)

            created = 0
            errors = []
            
            for index, row in df.iterrows():
                try:
                    # Required fields
                    name = str(row.get('name', '')).strip()
                    if not name or name.lower() in ['nan', 'none', '']:
                        errors.append(f'Row {index + 2}: Name is required')
                        continue
                    
                    price_usd = row.get('price_usd')
                    if pd.isna(price_usd) or price_usd is None:
                        errors.append(f'Row {index + 2}: Price USD is required')
                        continue
                    
                    try:
                        price_usd = float(price_usd)
                        if price_usd < 0:
                            raise ValueError("Price cannot be negative")
                    except (ValueError, TypeError):
                        errors.append(f'Row {index + 2}: Invalid price USD value')
                        continue
                    
                    # Optional fields - handle NaN/None values
                    sku = row.get('sku')
                    if pd.isna(sku) or sku is None or str(sku).strip().lower() in ['nan', 'none', '']:
                        sku = None
                    else:
                        sku = str(sku).strip()
                    
                    description = row.get('description', '')
                    if pd.isna(description) or description is None:
                        description = ''
                    else:
                        description = str(description).strip()
                    
                    price_lbp = row.get('price_lbp')
                    if pd.isna(price_lbp) or price_lbp is None or str(price_lbp).strip().lower() in ['nan', 'none', '']:
                        price_lbp = None
                    else:
                        try:
                            price_lbp = int(float(price_lbp))
                        except (ValueError, TypeError):
                            price_lbp = None
                    
                    stock = row.get('stock', 0)
                    if pd.isna(stock) or stock is None or str(stock).strip().lower() in ['nan', 'none', '']:
                        stock = 0
                    else:
                        try:
                            stock = int(float(stock))
                            if stock < 0:
                                stock = 0
                        except (ValueError, TypeError):
                            stock = 0
                    
                    # Handle category
                    category = None
                    category_name = row.get('category')
                    if not pd.isna(category_name) and category_name is not None and str(category_name).strip().lower() not in ['nan', 'none', '']:
                        category_name = str(category_name).strip()
                        if category_name:
                            # Get or create category for this business
                            category, created = Category.objects.get_or_create(
                                name=category_name,
                                business=business,
                                defaults={'is_global': False}
                            )
                            if created:
                                logger.info(f"Created new category '{category_name}' for business {business.name}")
                            else:
                                logger.info(f"Using existing category '{category_name}' for business {business.name}")
                    
                    # Create product
                    Product.objects.create(
                        business=business,
                        sku=sku,
                        name=name,
                        description=description,
                        price_usd=price_usd,
                        price_lbp=price_lbp,
                        stock=stock,
                        category=category,
                        active=True
                    )
                    created += 1
                    
                except Exception as e:
                    errors.append(f'Row {index + 2}: {str(e)}')
                    continue
            
            # Show results
            if errors:
                for error in errors[:5]:  # Show first 5 errors
                    messages.error(request, error)
                if len(errors) > 5:
                    messages.warning(request, f'... and {len(errors) - 5} more errors')
            
            if created > 0:
                messages.success(request, f'Successfully imported {created} products.')
            else:
                messages.error(request, 'No products were imported. Please check your Excel file format.')
            return redirect('core:product_list', business_id=business.id)
    else:
        form = ExcelUploadForm()
    return render(request, 'core/product_import.html', {'form': form, 'business': business})


def home(request):
    """Home page - shows landing page for all users"""
    return render(request, 'core/home.html')


# Instagram OAuth Integration Views

@login_required
def instagram_connect(request, business_id):
    """
    Redirect user to Facebook OAuth for Instagram integration.
    
    Args:
        business_id: ID of the business to connect Instagram to
    """
    import os
    from django.conf import settings
    
    business = get_object_or_404(Business, id=business_id, owner=request.user)
    
    # Build OAuth URL
    fb_app_id = os.getenv('FB_APP_ID')
    if not fb_app_id:
        messages.error(request, 'Facebook App ID not configured.')
        return redirect('core:owner_dashboard')
    
    # Build redirect URI
    redirect_uri = request.build_absolute_uri(
        reverse('core:instagram_callback', args=[business_id])
    )
    
    # Required scopes for Instagram messaging
    scopes = [
        'pages_show_list',
        'pages_read_engagement', 
        'instagram_basic',
        'instagram_manage_messages',
        'pages_messaging'
    ]
    
    # State parameter for security (carry business_id)
    import hmac
    import hashlib
    state_data = f"business_{business_id}"
    state_signature = hmac.new(
        os.getenv('SECRET_KEY', '').encode(),
        state_data.encode(),
        hashlib.sha256
    ).hexdigest()
    state = f"{state_data}:{state_signature}"
    
    # Build Facebook OAuth URL
    oauth_url = (
        f"https://www.facebook.com/v17.0/dialog/oauth?"
        f"client_id={fb_app_id}&"
        f"redirect_uri={redirect_uri}&"
        f"scope={','.join(scopes)}&"
        f"state={state}&"
        f"response_type=code"
    )
    
    logger.info(f"Redirecting business {business_id} to Facebook OAuth")
    return redirect(oauth_url)


@login_required
def instagram_callback(request, business_id):
    """
    Handle Facebook OAuth callback and exchange tokens.
    
    Args:
        business_id: ID of the business (from URL)
    """
    business = get_object_or_404(Business, id=business_id, owner=request.user)
    
    # Get parameters from callback
    code = request.GET.get('code')
    state = request.GET.get('state')
    error = request.GET.get('error')
    
    if error:
        error_description = request.GET.get('error_description', 'Unknown error')
        messages.error(request, f'Facebook OAuth error: {error_description}')
        logger.error(f"Facebook OAuth error for business {business_id}: {error_description}")
        return redirect('core:owner_dashboard')
    
    if not code or not state:
        messages.error(request, 'Invalid OAuth callback parameters.')
        return redirect('core:owner_dashboard')
    
    # Verify state parameter
    import hmac
    import hashlib
    import os
    
    try:
        state_data, state_signature = state.split(':', 1)
        expected_signature = hmac.new(
            os.getenv('SECRET_KEY', '').encode(),
            state_data.encode(),
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(state_signature, expected_signature):
            messages.error(request, 'Invalid OAuth state parameter.')
            return redirect('core:owner_dashboard')
        
        if state_data != f"business_{business_id}":
            messages.error(request, 'OAuth state mismatch.')
            return redirect('core:owner_dashboard')
            
    except (ValueError, IndexError):
        messages.error(request, 'Invalid OAuth state format.')
        return redirect('core:owner_dashboard')
    
    # Build redirect URI
    redirect_uri = request.build_absolute_uri(
        reverse('core:instagram_callback', args=[business_id])
    )
    
    try:
        # Step 1: Exchange code for short-lived token
        token_result = exchange_code_for_token(code, redirect_uri)
        if not token_result['success']:
            messages.error(request, f"Failed to exchange code: {token_result['error']}")
            return redirect('core:owner_dashboard')
        
        short_lived_token = token_result['data']['access_token']
        
        # Step 2: Exchange short-lived token for long-lived token
        long_lived_result = exchange_short_lived_for_long_lived(short_lived_token)
        if not long_lived_result['success']:
            messages.error(request, f"Failed to get long-lived token: {long_lived_result['error']}")
            return redirect('core:owner_dashboard')
        
        long_lived_token = long_lived_result['data']['access_token']
        token_expires_in = long_lived_result['data'].get('expires_in', 0)
        
        # Step 3: Get user's pages
        pages_result = get_user_pages(long_lived_token)
        if not pages_result['success']:
            messages.error(request, f"Failed to get pages: {pages_result['error']}")
            return redirect('core:owner_dashboard')
        
        pages = pages_result['data']['data']
        if not pages:
            messages.error(request, 'No Facebook pages found. Please create a Facebook page first.')
            return redirect('core:owner_dashboard')
        
        # For now, use the first page (in production, you might want to let user choose)
        page = pages[0]
        page_id = page['id']
        page_access_token = page['access_token']
        instagram_business_account = page.get('instagram_business_account', {})
        instagram_business_account_id = instagram_business_account.get('id') if instagram_business_account else None
        
        # Step 4: Update business with Instagram information
        business.instagram_page_id = page_id
        business.instagram_business_account_id = instagram_business_account_id
        business.page_access_token = page_access_token
        
        if token_expires_in > 0:
            business.page_token_expires_at = timezone.now() + timezone.timedelta(seconds=token_expires_in)
        
        business.save()
        
        # Step 5: Subscribe page to app for webhooks
        from .instagram_api import subscribe_page_to_app
        subscribe_result = subscribe_page_to_app(page_id, page_access_token)
        if not subscribe_result['success']:
            logger.warning(f"Failed to subscribe page {page_id} to app: {subscribe_result['error']}")
            messages.warning(request, 'Instagram connected but webhook subscription failed. Please contact support.')
        else:
            messages.success(request, 'Instagram successfully connected!')
        
        logger.info(f"Successfully connected Instagram for business {business_id}")
        return redirect('core:owner_dashboard')
        
    except Exception as e:
        logger.error(f"Error in Instagram callback for business {business_id}: {str(e)}")
        messages.error(request, 'An error occurred during Instagram connection. Please try again.')
        return redirect('core:owner_dashboard')


# Instagram Webhook Views

@csrf_exempt
@require_http_methods(["GET", "POST"])
def instagram_webhook(request):
    """
    Handle Instagram webhook for incoming messages.
    
    GET: Webhook verification
    POST: Handle incoming messages
    """
    logger.info("🔥🔥🔥 WEBHOOK FUNCTION CALLED - NEW CODE IS RUNNING! 🔥🔥🔥")
    
    if request.method == 'GET':
        return _handle_webhook_verification(request)
    else:
        return _handle_webhook_message(request)


def _handle_webhook_verification(request):
    """Handle webhook verification from Facebook."""
    import os
    
    hub_mode = request.GET.get('hub.mode')
    hub_verify_token = request.GET.get('hub.verify_token')
    hub_challenge = request.GET.get('hub.challenge')
    
    verify_token = os.getenv('FB_VERIFY_TOKEN')
    
    if hub_mode == 'subscribe' and hub_verify_token == verify_token:
        logger.info("Webhook verification successful")
        return HttpResponse(hub_challenge, content_type='text/plain')
    else:
        logger.warning(f"Webhook verification failed: mode={hub_mode}, token={hub_verify_token}")
        return HttpResponse('Verification failed', status=403)


def _handle_webhook_message(request):
    """Handle incoming Instagram messages."""
    logger.info("🔥🔥🔥 _handle_webhook_message CALLED! 🔥🔥🔥")
    
    try:
        logger.info(f"🔥 WEBHOOK RECEIVED - Method: {request.method}")
        logger.info(f"🔥 WEBHOOK HEADERS: {dict(request.META)}")
        
        # Get raw body for signature verification
        body = request.body.decode('utf-8')
        logger.info(f"🔥 WEBHOOK BODY: {body}")
        
        # Verify signature
        signature = request.META.get('HTTP_X_HUB_SIGNATURE_256', '')
        logger.info(f"🔥 SIGNATURE: {signature}")
        
        if not verify_webhook_signature(body, signature):
            logger.warning("Invalid webhook signature")
            return HttpResponse('Invalid signature', status=403)
        
        # Parse payload
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            logger.error("Invalid JSON payload")
            return HttpResponse('Invalid JSON', status=400)
        
        logger.info(f"Received webhook payload: {json.dumps(payload, indent=2)}")
        
        # Process Instagram messaging events
        logger.info(f"🔥 PROCESSING PAYLOAD: {json.dumps(payload, indent=2)}")
        
        if 'entry' in payload:
            logger.info(f"🔥 FOUND {len(payload['entry'])} ENTRIES")
            for i, entry in enumerate(payload['entry']):
                logger.info(f"🔥 PROCESSING ENTRY {i}: {entry}")
                if 'messaging' in entry:
                    logger.info(f"🔥 FOUND {len(entry['messaging'])} MESSAGING EVENTS")
                    for j, event in enumerate(entry['messaging']):
                        logger.info(f"🔥 PROCESSING MESSAGING EVENT {j}: {event}")
                        # Ignore read receipts and delivery receipts
                        if 'read' in event or 'delivery' in event:
                            logger.info("Ignoring read/delivery receipt event")
                            continue
                        _process_messaging_event(event, entry.get('id'))
                else:
                    logger.info(f"🔥 NO MESSAGING IN ENTRY {i}")
        else:
            logger.info(f"🔥 NO ENTRY IN PAYLOAD")
        
        return HttpResponse('OK', status=200)
        
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        return HttpResponse('Internal error', status=500)


def _process_messaging_event(event, page_id):
    """
    Process individual messaging event.
    
    Args:
        event: Messaging event data
        page_id: Facebook Page ID
    """
    logger.info("🚀🚀🚀 _process_messaging_event CALLED! 🚀🚀🚀")
    
    try:
        logger.info(f"🚀 STARTING _process_messaging_event")
        logger.info(f"🚀 EVENT: {event}")
        logger.info(f"🚀 PAGE_ID: {page_id}")
        
        # Find business by page ID
        try:
            business = Business.objects.get(instagram_page_id=page_id, active=True)
            logger.info(f"🚀 FOUND BUSINESS: {business.name}")
        except Business.DoesNotExist:
            logger.warning(f"No business found for page ID: {page_id}")
            return
        
        # Check if AI is enabled
        if not business.ai_enabled:
            logger.info(f"AI disabled for business {business.id}")
            return
        
        # Extract message data
        # Try different paths to get sender_id
        sender_id = None
        if 'sender' in event:
            sender_id = event['sender'].get('id')
        elif 'from' in event:
            # Sometimes it's 'from' instead of 'sender'
            sender_id = event['from'].get('id')
        
        message_data = event.get('message', {})
        message_text = message_data.get('text', '')
        message_mid = message_data.get('mid')
        
        # Ignore page echo messages to prevent loops/duplicates
        if message_data.get('is_echo'):
            logger.info("Ignoring echo message from page")
            return

        # Idempotency: skip if we've already processed this message id recently
        if message_mid:
            cache_key_mid = f"ig_processed_mid:{message_mid}"
            if cache.get(cache_key_mid):
                logger.info("Skipping already-processed message by mid")
                return
            # mark processed for 5 minutes
            cache.set(cache_key_mid, True, timeout=300)
        
        logger.info(f"🚀 RAW EVENT: {json.dumps(event, indent=2)}")
        logger.info(f"🚀 SENDER_ID: {sender_id}")
        logger.info(f"🚀 PAGE_ID: {page_id}")
        logger.info(f"🚀 MESSAGE_DATA: {message_data}")
        logger.info(f"🚀 MESSAGE_TEXT: {message_text}")
        
        # Extract post context if this is a reply to a post
        logger.info(f"🔍 CALLING _extract_post_context")
        post_context = _extract_post_context(event)
        logger.info(f"🔍 POST CONTEXT RESULT: {post_context}")
        
        # Store post context in conversation if available
        if post_context:
            logger.info(f"🔍 STORING POST CONTEXT IN CONVERSATION")
            _store_post_context_in_conversation(business, sender_id, post_context)
        
        # Get stored post context for this conversation
        stored_post_context = _get_stored_post_context(business, sender_id)
        logger.info(f"🔍 STORED POST CONTEXT: {stored_post_context}")
        
        # Use current post context or stored post context
        final_post_context = post_context if post_context else stored_post_context
        logger.info(f"🔍 FINAL POST CONTEXT: {final_post_context}")
        
        # Log the event for debugging
        logger.info(f"Processing event: sender_id={sender_id}, message_text='{message_text}', post_context={final_post_context}")
        
        # Log the full event for debugging post context
        logger.info(f"🔍 FULL EVENT DATA: {json.dumps(event, indent=2)}")
        logger.info(f"🔍 MESSAGE DATA: {json.dumps(message_data, indent=2)}")
        logger.info(f"🔍 MESSAGE DATA KEYS: {list(message_data.keys())}")
        
        # Check if this is a media-only message
        has_attachments = 'attachments' in message_data and message_data['attachments']
        if not message_text and not has_attachments:
            logger.info("No message text or attachments found")
            return
        
        # Handle case where sender_id is same as page_id or missing
        # TEMPORARY: Allow processing but warn about sender ID
        if not sender_id or sender_id == page_id:
            logger.error(f"Invalid sender ID: {sender_id}. Cannot send response to customer.")
            # Still allow processing to see if we can extract correct sender from event
            # Don't return yet, continue to see if post context processing can work
            if not message_text and not has_attachments:
                # No content to process, exit early
                return
        
        # Log incoming message
        MessageLog.objects.create(
            business=business,
            sender_id=sender_id,
            incoming_text=message_text or '[Media only]',
            direction='incoming'
        )
        
        # Check if we should auto-reply to unknown senders
        customer, created = Customer.objects.get_or_create(
            platform='instagram',
            platform_id=sender_id,
            business=business
        )
        
        if created and not business.allow_auto_reply_from_unknown:
            logger.info(f"New customer {sender_id} but auto-reply disabled for unknown senders")
            return
        
        # Generate AI response with post context
        try:
            # For media-only messages, process the media and respond based on matches
            if not message_text and has_attachments:
                # Let the media processing handle the response
                # Don't generate an AI response here for media-only messages
                logger.info("Media-only message, processing media attachments...")
                # The media processing will handle generating and sending a response
                
                # Process media attachments for product matching
                _process_media_attachments(business, sender_id, message_data)
                return
            
            # Check if this is a post context request (user asking about a post they replied to)
            logger.info(f"🔍 CHECKING FINAL POST CONTEXT: final_post_context={final_post_context}")
            
            # Only process image if caption is empty or unclear
            has_caption = final_post_context and 'post_caption' in final_post_context and final_post_context['post_caption']
            has_media_url = final_post_context and 'media_url' in final_post_context
            
            logger.info(f"🔍 Has caption: {has_caption}, Has media_url: {has_media_url}")
            
            if has_media_url and not has_caption:
                # User replied to a post WITHOUT caption - use image matching
                logger.info(f"🔥🔥🔥 Post has no caption, processing post image for matching...")
                _process_post_image_for_matching(business, sender_id, final_post_context)
                return
            else:
                logger.info(f"⚠️ Skipping image matching - caption is available (has_caption={has_caption})")
            
            # Enhance message with post context if available
            enhanced_message = _enhance_message_with_post_context(message_text, final_post_context)
            logger.info(f"🔍 Original message: {message_text}")
            logger.info(f"🔍 Enhanced message: {enhanced_message}")
            logger.info(f"🔍 Post context: {final_post_context}")
            
            ai_response = get_ai_response(business.id, enhanced_message, sender_id)
            logger.info(f"Generated AI response: {ai_response[:100]}...")
            
            # Send reply via Instagram API
            send_result = send_instagram_text_reply(
                business.page_access_token,
                sender_id,
                ai_response
            )
            
            if send_result['success']:
                # Log successful outgoing message
                MessageLog.objects.create(
                    business=business,
                    customer=customer,
                    sender_id=sender_id,
                    reply_text=ai_response,
                    direction='outgoing'
                )
                logger.info(f"Successfully sent AI response to {sender_id}")
            else:
                # Log failed message
                MessageLog.objects.create(
                    business=business,
                    customer=customer,
                    sender_id=sender_id,
                    reply_text=ai_response,
                    direction='outgoing',
                    error_message=send_result['error']
                )
                logger.error(f"Failed to send message to {sender_id}: {send_result['error']}")
                
        except Exception as e:
            logger.error(f"Error generating/sending AI response: {str(e)}")
            # Log error
            MessageLog.objects.create(
                business=business,
                customer=customer,
                sender_id=sender_id,
                direction='outgoing',
                error_message=str(e)
            )
        
        # If we didn't already process via post context, process media attachments
        if not (final_post_context and final_post_context.get('media_url') and not (final_post_context.get('post_caption'))):
            _process_media_attachments(business, sender_id, message_data)
            
    except Exception as e:
        logger.error(f"Error processing messaging event: {str(e)}")


def _process_post_image_for_matching(business, sender_id, post_context):
    """
    Process a post's image for product matching when user replies to a post without clear caption.
    
    Args:
        business: Business instance
        sender_id: Sender ID
        post_context: Post context with media_url
    """
    try:
        media_url = post_context.get('media_url')
        if not media_url:
            logger.warning("No media_url in post_context for image matching")
            return
        
        logger.info(f"Processing post image for matching: {media_url}")
        
        # Process the post's image using the media processing function
        from .tasks import process_media
        logger.info(f"Processing post image synchronously: {media_url}")
        result = process_media(
            media_url=media_url,
            business_id=business.id,
            media_id=f"post_{sender_id}_{int(timezone.now().timestamp())}",
            sender_id=sender_id,
            thumbnail_url=post_context.get('thumbnail_url')
        )
        logger.info(f"Post image processing completed: {result}")
        
    except Exception as e:
        logger.error(f"Error processing post image: {str(e)}")


def _process_media_attachments(business, sender_id, message_data):
    """
    Process media attachments for product matching.
    
    Args:
        business: Business instance
        sender_id: Sender ID
        message_data: Message data containing attachments
    """
    try:
        if 'attachments' not in message_data:
            return
        
        attachments = message_data['attachments']
        for attachment in attachments:
            att_type = attachment.get('type')
            if att_type in ['image', 'video']:
                media_url = attachment.get('payload', {}).get('url')
                if media_url:
                    logger.info(f"Processing media attachment: {media_url}")
                    
                    # Process media synchronously (Celery not available)
                    try:
                        from .tasks import process_media
                        logger.info(f"Processing media synchronously: {media_url}")
                        result = process_media(
                            media_url=media_url,
                            business_id=business.id,
                            media_id=f"attachment_{sender_id}_{int(timezone.now().timestamp())}",
                            sender_id=sender_id
                        )
                        logger.info(f"Media processing completed: {result}")
                    except Exception as e:
                        logger.error(f"Failed to process media: {str(e)}")
            elif att_type == 'ig_reel':
                payload = attachment.get('payload', {})
                reel_video_id = payload.get('reel_video_id')
                media_url = None
                if reel_video_id:
                    logger.info(f"Fetching reel media for reel_video_id: {reel_video_id}")
                    reel_info = _fetch_reel_info(reel_video_id)
                    if reel_info and reel_info.get('media_url'):
                        media_url = reel_info['media_url']
                # Fallback to payload url if API didn't return media_url
                if not media_url:
                    media_url = payload.get('url')
                if media_url:
                    try:
                        from .tasks import process_media
                        logger.info(f"Processing reel media synchronously: {media_url}")
                        result = process_media(
                            media_url=media_url,
                            business_id=business.id,
                            media_id=f"reel_{sender_id}_{int(timezone.now().timestamp())}",
                            sender_id=sender_id,
                            thumbnail_url=reel_info.get('thumbnail_url') if reel_info else None
                        )
                        logger.info(f"Reel media processing completed: {result}")
                    except Exception as e:
                        logger.error(f"Failed to process reel media: {str(e)}")
    except Exception as e:
        logger.error(f"Error processing media attachments: {str(e)}")


def _extract_post_context(event):
    """
    Extract post context from Instagram messaging event.
    
    Args:
        event: Instagram messaging event data
        
    Returns:
        Dict with post information if available, None otherwise
    """
    try:
        import re  # Move import to top of function
        
        logger.info(f"🔍 EXTRACTING POST CONTEXT FROM EVENT")
        logger.info(f"🔍 EVENT KEYS: {list(event.keys())}")
        
        # Check if this is a reply to a post
        message_data = event.get('message', {})
        logger.info(f"🔍 MESSAGE DATA IN EXTRACT: {message_data}")
        
        # Look for post context in the message data
        post_context = {}
        
        # Check for media_id in the message (this is the key field for post replies)
        media_id = message_data.get('media_id')
        if media_id:
            post_context['media_id'] = media_id
            logger.info(f"✅ Found media_id: {media_id}")
            
            # Try to fetch the post caption and media URL using the media_id
            media_info = _fetch_post_caption_from_media_id(media_id)
            if media_info:
                if media_info.get('caption'):
                    post_context['post_caption'] = media_info['caption']
                    logger.info(f"✅ Fetched post caption: {media_info['caption']}")
                else:
                    logger.warning(f"⚠️ Caption field is empty in API response: {media_info}")
                
                if media_info.get('media_url'):
                    post_context['media_url'] = media_info['media_url']
                    post_context['media_type'] = media_info.get('media_type', 'IMAGE')
                    logger.info(f"✅ Fetched post media_url: {media_info['media_url']}")
            else:
                logger.warning(f"❌ Failed to fetch media info for media_id: {media_id}")
        else:
            logger.info(f"❌ No media_id found in message_data: {message_data}")
        
        # Check for post ID in the message
        if 'post_id' in message_data:
            post_context['post_id'] = message_data['post_id']
        
        # Check for media context (if the message references a post)
        if 'attachments' in message_data:
            logger.info(f"🔍 FOUND ATTACHMENTS: {message_data['attachments']}")
            attachments = message_data['attachments']
            for attachment in attachments:
                logger.info(f"🔍 PROCESSING ATTACHMENT: {attachment}")
                if attachment.get('type') == 'share' and 'payload' in attachment:
                    payload = attachment['payload']
                    logger.info(f"🔍 SHARE PAYLOAD: {payload}")
                    if 'url' in payload:
                        # Extract post ID from URL if it's an Instagram post
                        url = payload['url']
                        logger.info(f"🔍 SHARE URL: {url}")
                        if 'instagram.com/p/' in url:
                            # Extract post ID from Instagram URL
                            match = re.search(r'instagram\.com/p/([^/]+)', url)
                            if match:
                                post_context['post_id'] = match.group(1)
                                post_context['post_url'] = url
                                logger.info(f"✅ Extracted post_id from URL: {match.group(1)}")
                        elif 'lookaside.fbsbx.com' in url:
                            # This is a Facebook CDN URL for shared content
                            logger.info(f"🔍 FACEBOOK CDN URL DETECTED: {url}")
                            # Try to extract asset_id from the URL
                            asset_match = re.search(r'asset_id=([^&]+)', url)
                            if asset_match:
                                asset_id = asset_match.group(1)
                                post_context['asset_id'] = asset_id
                                post_context['share_url'] = url
                                logger.info(f"✅ Extracted asset_id: {asset_id}")
                                # Try to fetch the post caption and media_url using the asset_id
                                media_info = _fetch_post_caption_from_asset_id(asset_id)
                                if media_info:
                                    if media_info.get('caption'):
                                        post_context['post_caption'] = media_info['caption']
                                        logger.info(f"✅ Fetched post caption from asset_id: {media_info['caption']}")
                                    if media_info.get('media_url'):
                                        post_context['media_url'] = media_info['media_url']
                                        post_context['media_type'] = media_info.get('media_type', 'IMAGE')
                                        logger.info(f"✅ Fetched post media_url from asset_id: {media_info['media_url']}")
                
                # Handle Instagram reel attachment coming as 'ig_reel'
                if attachment.get('type') == 'ig_reel' and 'payload' in attachment:
                    payload = attachment['payload']
                    reel_video_id = payload.get('reel_video_id')
                    if reel_video_id:
                        logger.info(f"🔍 IG_REEL attachment detected with reel_video_id: {reel_video_id}")
                        reel_info = _fetch_reel_info(reel_video_id)
                        if reel_info and reel_info.get('media_url'):
                            post_context['reel_id'] = reel_video_id
                            post_context['reel_url'] = reel_info.get('permalink') or payload.get('url')
                            post_context['media_url'] = reel_info['media_url']
                            post_context['media_type'] = reel_info.get('media_type', 'VIDEO')
                            if reel_info.get('thumbnail_url'):
                                post_context['thumbnail_url'] = reel_info['thumbnail_url']
                            if reel_info.get('caption'):
                                post_context['post_caption'] = reel_info['caption']
                            logger.info(f"✅ Fetched reel media_url from API: {reel_info['media_url']}")
                        else:
                            logger.warning(f"❌ Failed to fetch reel info for reel_video_id: {reel_video_id}")
        
        # Check for story context - can be directly in message_data or in reply_to
        story_data = None
        if 'story' in message_data:
            story_data = message_data['story']
        elif 'reply_to' in message_data and 'story' in message_data.get('reply_to', {}):
            story_data = message_data['reply_to']['story']
        
        if story_data:
            story_id = story_data.get('id')
            post_context['story_id'] = story_id
            post_context['story_url'] = story_data.get('url')
            
            # Try to fetch story media information
            logger.info(f"🔍 Found story ID: {story_id}")
            story_info = _fetch_story_info(story_id)
            if story_info:
                if story_info.get('media_url'):
                    post_context['media_url'] = story_info['media_url']
                    post_context['media_type'] = story_info.get('media_type', 'IMAGE')
                    logger.info(f"✅ Fetched story media_url: {story_info['media_url']}")
                # Stories don't have captions, so we'll rely on image matching
                if story_info.get('caption'):
                    post_context['post_caption'] = story_info['caption']
                    logger.info(f"✅ Fetched story caption: {story_info['caption']}")
            else:
                logger.warning(f"❌ Failed to fetch story info for story_id: {story_id}")
        
        # Check for reel context - can be directly in message_data or in reply_to
        reel_data = None
        if 'reel' in message_data:
            reel_data = message_data['reel']
        elif 'reply_to' in message_data and 'reel' in message_data.get('reply_to', {}):
            reel_data = message_data['reply_to']['reel']
        
        if reel_data:
            reel_id = reel_data.get('id')
            post_context['reel_id'] = reel_id
            post_context['reel_url'] = reel_data.get('url')
            logger.info(f"🔍 Found reel ID: {reel_id}")
            reel_info = _fetch_reel_info(reel_id)
            if reel_info:
                if reel_info.get('media_url'):
                    post_context['media_url'] = reel_info['media_url']
                    post_context['media_type'] = reel_info.get('media_type', 'VIDEO')
                    logger.info(f"✅ Fetched reel media_url: {reel_info['media_url']}")
                if reel_info.get('thumbnail_url'):
                    post_context['thumbnail_url'] = reel_info['thumbnail_url']
                if reel_info.get('caption'):
                    post_context['post_caption'] = reel_info['caption']
                    logger.info(f"✅ Fetched reel caption: {reel_info['caption']}")
            else:
                logger.warning(f"❌ Failed to fetch reel info for reel_id: {reel_id}")
        
        logger.info(f"🔍 FINAL POST CONTEXT: {post_context}")
        # Return post_context if it has any keys (even if media_url exists without caption)
        return post_context if post_context and len(post_context) > 0 else None
        
    except Exception as e:
        logger.error(f"Error extracting post context: {str(e)}")
        return None


def _fetch_post_caption_from_media_id(media_id):
    """
    Fetch post caption and media URL from Instagram using media_id and Graph API.
    
    Args:
        media_id: Instagram media ID
        
    Returns:
        Dict with caption and media_url if successful, None otherwise
    """
    try:
        import requests
        import os
        
        # Get the page access token from the business
        # We need to find the business that owns this media
        # For now, we'll use the first business with a page access token
        from .models import Business
        
        business = Business.objects.filter(
            page_access_token__isnull=False,
            page_access_token__gt=''
        ).first()
        
        if not business:
            logger.error("No business found with page access token")
            return None
        
        # Instagram Graph API endpoint
        graph_version = os.getenv('FB_GRAPH_VERSION', 'v17.0')
        url = f"https://graph.facebook.com/{graph_version}/{media_id}"
        
        params = {
            'fields': 'caption,media_type,media_url,permalink',
            'access_token': business.page_access_token
        }
        
        logger.info(f"🔍 Fetching post caption for media_id: {media_id}")
        logger.info(f"🔍 Using access token: {business.page_access_token[:10]}...")
        logger.info(f"🔍 API URL: {url}")
        logger.info(f"🔍 API Params: {params}")
        
        response = requests.get(url, params=params, timeout=10)
        
        logger.info(f"🔍 API Response Status: {response.status_code}")
        logger.info(f"🔍 API Response Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"🔍 API Response Data: {data}")
            
            return {
                'caption': data.get('caption', ''),
                'media_url': data.get('media_url', ''),
                'media_type': data.get('media_type', ''),
                'permalink': data.get('permalink', '')
            }
        else:
            logger.error(f"❌ Failed to fetch post caption: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Error fetching post caption from media_id {media_id}: {str(e)}")
        return None


def _fetch_story_info(story_id):
    """
    Fetch story information from Instagram using story_id and Graph API.
    
    Args:
        story_id: Instagram story ID
        
    Returns:
        Dict with media_url and caption if successful, None otherwise
    """
    try:
        import requests
        import os
        
        # Get the page access token from the business
        from .models import Business
        
        business = Business.objects.filter(
            page_access_token__isnull=False,
            page_access_token__gt=''
        ).first()
        
        if not business:
            logger.error("No business found with page access token")
            return None
        
        # Instagram Graph API endpoint for stories
        graph_version = os.getenv('FB_GRAPH_VERSION', 'v17.0')
        url = f"https://graph.facebook.com/{graph_version}/{story_id}"
        
        params = {
            'fields': 'media_type,media_url,caption,permalink',
            'access_token': business.page_access_token
        }
        
        logger.info(f"🔍 Fetching story info for story_id: {story_id}")
        logger.info(f"🔍 Using access token: {business.page_access_token[:10]}...")
        logger.info(f"🔍 API URL: {url}")
        
        response = requests.get(url, params=params, timeout=10)
        
        logger.info(f"🔍 API Response Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"🔍 API Response Data: {data}")
            
            return {
                'caption': data.get('caption', ''),
                'media_url': data.get('media_url', ''),
                'media_type': data.get('media_type', 'IMAGE'),
                'permalink': data.get('permalink', '')
            }
        else:
            logger.error(f"❌ Failed to fetch story info: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Error fetching story info from story_id {story_id}: {str(e)}")
        return None


def _fetch_reel_info(reel_id):
    """
    Fetch reel information from Instagram using reel_id and Graph API.
    Returns media_url (video) and caption when available.
    """
    try:
        import requests
        import os
        from .models import Business

        business = Business.objects.filter(
            page_access_token__isnull=False,
            page_access_token__gt=''
        ).first()
        if not business:
            logger.error("No business found with page access token")
            return None

        graph_version = os.getenv('FB_GRAPH_VERSION', 'v17.0')
        url = f"https://graph.facebook.com/{graph_version}/{reel_id}"
        params = {
            'fields': 'media_type,media_url,thumbnail_url,caption,permalink',
            'access_token': business.page_access_token
        }
        logger.info(f"🔍 Fetching reel info for reel_id: {reel_id}")
        response = requests.get(url, params=params, timeout=10)
        logger.info(f"🔍 API Response Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            logger.info(f"🔍 API Response Data: {data}")
            # Reels are typically VIDEO; fall back to IMAGE if API returns otherwise
            media_type = data.get('media_type') or 'VIDEO'
            return {
                'caption': data.get('caption', ''),
                'media_url': data.get('media_url', ''),
                'media_type': media_type,
                'thumbnail_url': data.get('thumbnail_url', ''),
                'permalink': data.get('permalink', '')
            }
        else:
            logger.error(f"❌ Failed to fetch reel info: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        logger.error(f"Error fetching reel info from reel_id {reel_id}: {str(e)}")
        return None


def _fetch_post_caption_from_asset_id(asset_id):
    """
    Fetch post caption and media_url from Instagram using asset_id from Facebook CDN URL.
    
    Args:
        asset_id: Asset ID from Facebook CDN URL
        
    Returns:
        Dict with caption and media_url if successful, None otherwise
    """
    try:
        import requests
        import os
        
        # Get the page access token from the business
        from .models import Business
        
        business = Business.objects.filter(
            page_access_token__isnull=False,
            page_access_token__gt=''
        ).first()
        
        if not business:
            logger.error("No business found with page access token")
            return None
        
        # Try to fetch the asset using the asset_id
        # This might not work directly, but let's try
        graph_version = os.getenv('FB_GRAPH_VERSION', 'v17.0')
        url = f"https://graph.facebook.com/{graph_version}/{asset_id}"
        
        params = {
            'fields': 'caption,media_type,media_url,permalink',
            'access_token': business.page_access_token
        }
        
        logger.info(f"🔍 Fetching post caption for asset_id: {asset_id}")
        logger.info(f"🔍 Using access token: {business.page_access_token[:10]}...")
        logger.info(f"🔍 API URL: {url}")
        logger.info(f"🔍 API Params: {params}")
        
        response = requests.get(url, params=params, timeout=10)
        
        logger.info(f"🔍 API Response Status: {response.status_code}")
        logger.info(f"🔍 API Response Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"🔍 API Response Data: {data}")
            caption = data.get('caption', '')
            media_url = data.get('media_url', '')
            if caption or media_url:
                logger.info(f"✅ Successfully fetched data from asset_id: caption={bool(caption)}, media_url={bool(media_url)}")
                return {
                    'caption': caption,
                    'media_url': media_url,
                    'media_type': data.get('media_type', ''),
                    'permalink': data.get('permalink', '')
                }
            else:
                logger.warning(f"⚠️ Both caption and media_url are empty in API response: {data}")
                return None
        else:
            logger.error(f"❌ Failed to fetch post caption from asset_id: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Error fetching post caption from asset_id {asset_id}: {str(e)}")
        return None


def _enhance_message_with_post_context(message_text, post_context):
    """
    Enhance user message with post context for better AI understanding.
    
    Args:
        message_text: Original user message
        post_context: Post context information
        
    Returns:
        Enhanced message with post context
    """
    if not post_context:
        return message_text
    
    try:
        enhanced_parts = [message_text]
        
        # Add post context information
        if 'media_id' in post_context:
            enhanced_parts.append(f"[This message is a reply to media ID: {post_context['media_id']}]")
        
        if 'post_id' in post_context:
            enhanced_parts.append(f"[This message is a reply to post ID: {post_context['post_id']}]")
        
        if 'post_url' in post_context:
            enhanced_parts.append(f"[Post URL: {post_context['post_url']}]")
        
        if 'post_caption' in post_context:
            enhanced_parts.append(f"[Post caption: {post_context['post_caption']}]")
        
        if 'story_id' in post_context:
            enhanced_parts.append(f"[This message is a reply to story ID: {post_context['story_id']}]")
        
        if 'reel_id' in post_context:
            enhanced_parts.append(f"[This message is a reply to reel ID: {post_context['reel_id']}]")
        
        # Add instruction for AI to consider post context
        enhanced_parts.append("[Please consider that this message is a reply to a post. The user might be asking about the product shown in that post. If the message is just 'price?' or 'cost?' or similar, they are likely asking about the product in the post they replied to. Use the post caption to understand what product they're referring to.]")
        
        return " ".join(enhanced_parts)
        
    except Exception as e:
        logger.error(f"Error enhancing message with post context: {str(e)}")
        return message_text


def _store_post_context_in_conversation(business, sender_id, post_context):
    """
    Store post context in the conversation for later retrieval.
    
    Args:
        business: Business instance
        sender_id: Sender ID
        post_context: Post context to store
    """
    try:
        import json
        from django.utils import timezone
        
        # Create or update customer with post context
        customer, created = Customer.objects.get_or_create(
            business=business,
            platform_id=sender_id,
            defaults={'platform': 'instagram'}
        )
        
        # Store post context in customer metadata (if you have a metadata field)
        # For now, we'll use a simple approach with MessageLog
        MessageLog.objects.create(
            business=business,
            sender_id=sender_id,
            incoming_text="[POST_CONTEXT_STORED]",
            reply_text=json.dumps(post_context),
            direction='incoming',
            created_at=timezone.now()
        )
        
        logger.info(f"🔍 STORED POST CONTEXT FOR {sender_id}: {post_context}")
        
    except Exception as e:
        logger.error(f"Error storing post context: {str(e)}")


def _get_stored_post_context(business, sender_id):
    """
    Retrieve stored post context for this conversation.
    
    Args:
        business: Business instance
        sender_id: Sender ID
        
    Returns:
        Stored post context if available, None otherwise
    """
    try:
        import json
        from django.utils import timezone
        from datetime import timedelta
        
        # Look for recent post context storage (within last 10 minutes)
        recent_time = timezone.now() - timedelta(minutes=10)
        
        recent_logs = MessageLog.objects.filter(
            business=business,
            sender_id=sender_id,
            incoming_text="[POST_CONTEXT_STORED]",
            created_at__gte=recent_time
        ).order_by('-created_at')
        
        if recent_logs.exists():
            latest_log = recent_logs.first()
            post_context = json.loads(latest_log.reply_text)
            logger.info(f"🔍 RETRIEVED STORED POST CONTEXT FOR {sender_id}: {post_context}")
            return post_context
        
        logger.info(f"🔍 NO STORED POST CONTEXT FOUND FOR {sender_id}")
        return None
        
    except Exception as e:
        logger.error(f"Error retrieving stored post context: {str(e)}")
        return None


def _generate_excel_template():
    """
    Generate Excel template with category column.
    
    Returns:
        HttpResponse with Excel file
    """
    try:
        import pandas as pd
        from django.http import HttpResponse
        import io
        
        # Create sample data with category column
        sample_data = {
            'sku': ['SKU001', 'SKU002', 'SKU003'],
            'name': ['Sample Product 1', 'Sample Product 2', 'Sample Product 3'],
            'description': ['Description 1', 'Description 2', 'Description 3'],
            'price_usd': [10.99, 25.50, 5.00],
            'price_lbp': [165000, 382500, 75000],
            'stock': [10, 5, 20],
            'category': ['Electronics', 'Clothing', '']  # Empty category is allowed
        }
        
        df = pd.DataFrame(sample_data)
        
        # Create Excel file in memory
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Products', index=False)
        
        output.seek(0)
        
        # Create HTTP response
        response = HttpResponse(
            output.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="product_import_template.xlsx"'
        
        return response
        
    except Exception as e:
        logger.error(f"Error generating Excel template: {str(e)}")
        return HttpResponse("Error generating template", status=500)
