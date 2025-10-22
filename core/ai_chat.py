"""
AI Chat integration for Instagram messaging.

This module provides AI-powered responses for customer messages using OpenAI's API with function calling.
"""

import os
import logging
import json
from typing import Optional, Dict, Any
from django.conf import settings
from django.db import models
from .models import Business, Product, Category

logger = logging.getLogger(__name__)

# Environment variables
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-3.5-turbo')

# Rate limiting and input validation
MAX_MESSAGE_LENGTH = 1000

# AI Response settings
AI_TEMPERATURE = 0.1  # Low temperature for consistent responses
AI_MAX_TOKENS = 300   # Reduced token limit to prevent hallucinations


def get_ai_response(business_id: int, customer_message: str, sender_id: Optional[str] = None) -> str:
    """
    Generate AI response for customer message using OpenAI function calling.
    
    Args:
        business_id: ID of the business
        customer_message: Message from customer
        sender_id: Optional sender ID for context
        
    Returns:
        AI-generated response text
    """
    try:
        # Input validation
        if not customer_message or len(customer_message.strip()) == 0:
            return "I received your message but it appears to be empty. Could you please try again?"
        
        if len(customer_message) > MAX_MESSAGE_LENGTH:
            customer_message = customer_message[:MAX_MESSAGE_LENGTH]
            logger.warning(f"Message truncated to {MAX_MESSAGE_LENGTH} characters")
        
        # Get business
        try:
            business = Business.objects.get(id=business_id, active=True)
        except Business.DoesNotExist:
            logger.error(f"Business {business_id} not found or inactive")
            return "I'm sorry, but I'm having trouble accessing your business information right now. Please try again later."
        
        # Get recent conversation history for context
        conversation_history = _get_conversation_history(business_id, sender_id)
        
        # Smart context filtering - use minimal context for greetings/general questions
        if _is_greeting_or_general_question(customer_message):
            conversation_history = conversation_history[-1:] if conversation_history else []
            logger.info("Using minimal context for greeting/general question")
        
        # If user is asking for products directly, ensure we have context to understand what they want
        if _should_show_products_directly(customer_message):
            logger.info("User is requesting products directly")
        
        # Build system prompt without product dump
        system_prompt = _build_system_prompt_without_products(business)
        
        # Call OpenAI API with function calling
        response_text = _call_openai_api_with_functions(system_prompt, customer_message, conversation_history, business_id)
        
        return response_text
        
    except Exception as e:
        logger.error(f"Error generating AI response: {str(e)}")
        return _get_fallback_response()


def _build_system_prompt_without_products(business: Business) -> str:
    """
    Build system prompt without product dump - uses function calling instead.
    
    Args:
        business: Business instance
        
    Returns:
        System prompt string
    """
    prompt = f"""You are an AI assistant for {business.name}, a business that sells products online.

CRITICAL INSTRUCTIONS:
- ALWAYS introduce yourself as an AI assistant, not a person
- ALWAYS respond in English, regardless of the language the customer uses (Arabic, Lebanese texting, etc.)
- You are NOT allowed to invent, make up, or guess any product names, prices, or availability
- You can ONLY provide information about products by calling the available functions
- Be DIRECT and HELPFUL - give users what they ask for immediately
- Keep responses concise but informative
- If you don't know something, admit it and suggest they contact the business directly
- Use stock information only to determine availability (in stock/out of stock), NEVER mention specific stock quantities to users

DIRECT RESPONSE STRATEGY:
- When asked "what do you sell?" or "what products do you have?" → IMMEDIATELY call get_categories and show the categories
- When asked about a specific category (e.g., "show me [category]", "what [category] do you have?", "[category] options", "[category] available") → IMMEDIATELY call get_products_by_category and list the products
- When asked about a specific product → IMMEDIATELY call get_product_details and show the details
- When asked general questions like "how much is this?" or "what size is it?" without specifying a product, ask the user to specify the exact product name
- If the message indicates it's a reply to a post (contains post context), try to understand what product the user is asking about from the post context
- When post caption is provided, use it to identify the product the user is asking about
- If the post caption mentions a product name, search for that product in the database
- IMPORTANT: When you see post context in the message, ALWAYS call identify_product_from_post_context to find the product the user is asking about
- If the user just says "price?" or "cost?" and there's post context, they are asking about the product in that post
- When you see "[Post caption: ...]" in the message, use that caption to identify the product the user is asking about
- The post caption contains the actual product information - use it to search for matching products
- NEVER mention prices unless specifically asked about pricing
- Use conversation context to understand what the customer is referring to
- When asked about colors/sizes, provide EXACT information from the database metadata
- Be precise with product attributes - only mention what's actually in the metadata

RESPONSE GUIDELINES:
- Only introduce yourself as an AI assistant in the FIRST message of a conversation
- For follow-up messages, respond naturally without repeating the introduction
- Respond in English only, even if customer writes in Arabic or Lebanese texting
- BE DIRECT: When users ask for products, show them the products immediately
- NEVER ask "would you like to see products?" - just show them
- When users say "yes", "show me", "I want to see" - interpret this as a request for products and show them
- UNDERSTAND USER RESPONSES: When you ask a question and user says "yes", understand they are answering your question
- If you mention categories and user says "yes", they want to see products in those categories
- If you mention a category and user says "yes", they want to see products in that category
- ALWAYS show products when user explicitly asks for them (e.g., "show me [category]", "[category] options", "what [category] do you have?")
- When user asks for "other options", "another options", "different options", "more options" → show different products from the same category, not the same product again
- Use conversation context ONLY when the customer is clearly continuing a specific product discussion
- When asked about colors/sizes for a specific product, provide EXACT information from the metadata
- If customer asks "what colors and sizes are available?" without specifying a product, ask them to specify the exact product name
- Provide EXACT details from the metadata when asked about product attributes - don't guess or invent
- Understand Lebanese texting and Arabic messages, but respond in English
- Be precise: if metadata shows "white, black" don't mention "grey"
- For sizes, list the EXACT sizes available (e.g., "41, 42, 43") not "various sizes"
- IMPORTANT: If customer says "hello", "hi", "what do you sell?", or any general greeting/question, start completely fresh without referencing any previous products or conversations
- Only reference previous products if the customer is clearly continuing that specific discussion (e.g., "what about the colors for that shoe?")
- When asked general questions like "how much does it cost?" or "what size is it?" without specifying a product, ask the user to specify the exact product name they're asking about

EXAMPLES OF WHAT TO DO:
- User: "show me [category]" → IMMEDIATELY call get_products_by_category("[category]") and show the products
- User: "what [category] do you have?" → IMMEDIATELY call get_products_by_category("[category]") and show the products
- User: "[category] options available" → IMMEDIATELY call get_products_by_category("[category]") and show the products
- User: "yes" (after you mentioned categories) → IMMEDIATELY call get_products_by_category for the most relevant category
- User: "yes" (after you mentioned a category) → IMMEDIATELY call get_products_by_category for that category and show the products
- User: "other options" or "another options" → Show different products from the same category, not the same product again
- User: "more options" → Show additional products from the same category
- User: "price?" with post context → IMMEDIATELY call identify_product_from_post_context to find the product
- User: "cost?" with post context → IMMEDIATELY call identify_product_from_post_context to find the product

Remember: You are an AI assistant, not a human. Be DIRECT and HELPFUL - give users what they ask for immediately without asking for confirmation."""
    
    return prompt


def _call_openai_api_with_functions(system_prompt: str, user_message: str, conversation_history: list, business_id: int) -> str:
    """
    Call OpenAI API with function calling capabilities.
    
    Args:
        system_prompt: System prompt with business context
        user_message: Customer message
        conversation_history: Recent conversation context
        business_id: Business ID for function calls
        
    Returns:
        AI-generated response
    """
    if not OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY not configured")
        return _get_fallback_response()
    
    try:
        import openai
        
        # Initialize OpenAI client
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        
        # Build messages array with conversation history
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add conversation history (limit to last 3 messages to minimize token usage)
        recent_history = conversation_history[-3:] if conversation_history else []
        messages.extend(recent_history)
        
        # Add current user message
        messages.append({"role": "user", "content": user_message})
        
        # Define available functions
        functions = [
            {
                "name": "get_categories",
                "description": "Get all product categories available in the store. Use this when user asks 'what do you sell?' or 'what products do you have?'",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            {
                "name": "get_products_by_category",
                "description": "Get products in a specific category. ALWAYS use this when user asks about a specific category like 'show me [category]', 'what [category] do you have?', 'I want to see [category]', '[category] options', '[category] available', or when user says 'yes' after you mentioned a category. Also use when user asks for 'other options', 'another options', 'different options', 'more options' to show different products from the same category.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "category_name": {
                            "type": "string",
                            "description": "Name of the category to search for (e.g., 'shoes', 'clothing', 'accessories', 'electronics', 'books', etc.)"
                        }
                    },
                    "required": ["category_name"]
                }
            },
            {
                "name": "get_product_details",
                "description": "Get detailed information about a specific product. Use this when user asks about a specific product by name.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "product_name": {
                            "type": "string",
                            "description": "Name of the product to get details for"
                        }
                    },
                    "required": ["product_name"]
                }
            },
            {
                "name": "search_products",
                "description": "Search for products by name or description. Use this when user is looking for something specific or when you need to find products that might match a post context.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "search_term": {
                            "type": "string",
                            "description": "Search term to find products"
                        }
                    },
                    "required": ["search_term"]
                }
            },
            {
                "name": "handle_yes_response",
                "description": "Handle when user says 'yes' after you mentioned categories or products. Use this to show products in the most relevant category.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "category_name": {
                            "type": "string",
                            "description": "Name of the category to show products for"
                        }
                    },
                    "required": ["category_name"]
                }
            },
            {
                "name": "identify_product_from_post_context",
                "description": "Identify product from post context when user replies to a post. Use this when the message contains post context and the user is asking about a product.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "post_caption": {
                            "type": "string",
                            "description": "The post caption that might contain product information"
                        },
                        "user_message": {
                            "type": "string",
                            "description": "The user's message (e.g., 'price?', 'cost?')"
                        }
                    },
                    "required": ["post_caption", "user_message"]
                }
            }
        ]
        
        # Call OpenAI API with function calling
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            functions=functions,
            function_call="auto",
            temperature=AI_TEMPERATURE,
            max_tokens=AI_MAX_TOKENS,
            timeout=30
        )
        
        # Handle function calls
        if response.choices[0].message.function_call:
            function_name = response.choices[0].message.function_call.name
            function_args = json.loads(response.choices[0].message.function_call.arguments)
            
            logger.info(f"🤖 AI called function: {function_name}")
            logger.info(f"🤖 Function arguments: {function_args}")
            
            # Execute the function
            function_result = _execute_function(function_name, function_args, business_id)
            
            logger.info(f"🤖 Function result: {function_result}")
            
            # Add function result to messages and get final response
            messages.append({
                "role": "assistant",
                "content": None,
                "function_call": response.choices[0].message.function_call
            })
            messages.append({
                "role": "function",
                "name": function_name,
                "content": json.dumps(function_result)
            })
            
            # Get final response
            final_response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                temperature=AI_TEMPERATURE,
                max_tokens=AI_MAX_TOKENS,
                timeout=30
            )
            
            return final_response.choices[0].message.content.strip()
        else:
            # No function call needed, return direct response
            return response.choices[0].message.content.strip()
        
    except Exception as e:
        logger.error(f"OpenAI API error: {str(e)}")
        return _get_fallback_response()


def _execute_function(function_name: str, function_args: dict, business_id: int) -> dict:
    """
    Execute backend function and return structured data.
    
    Args:
        function_name: Name of the function to execute
        function_args: Arguments for the function
        business_id: Business ID for filtering
        
    Returns:
        Structured data for the AI
    """
    try:
        business = Business.objects.get(id=business_id, active=True)
        
        if function_name == "get_categories":
            return _get_categories_data(business)
        elif function_name == "get_products_by_category":
            return _get_products_by_category_data(business, function_args.get("category_name", ""))
        elif function_name == "get_product_details":
            return _get_product_details_data(business, function_args.get("product_name", ""))
        elif function_name == "search_products":
            return _search_products_data(business, function_args.get("search_term", ""))
        elif function_name == "handle_yes_response":
            return _get_products_by_category_data(business, function_args.get("category_name", ""))
        elif function_name == "identify_product_from_post_context":
            return _identify_product_from_post_context(business, function_args.get("post_caption", ""), function_args.get("user_message", ""))
        else:
            return {"error": f"Unknown function: {function_name}"}
            
    except Exception as e:
        logger.error(f"Error executing function {function_name}: {str(e)}")
        return {"error": str(e)}


def _get_categories_data(business: Business) -> dict:
    """Get categories data for the business."""
    try:
        categories = business.categories.all().order_by('name')
        categories_data = []
        
        for category in categories:
            product_count = category.products.filter(active=True).count()
            categories_data.append({
                "name": category.name,
                "product_count": product_count,
                "is_global": category.is_global
            })
        
        return {
            "categories": categories_data,
            "total_categories": len(categories_data)
        }
    except Exception as e:
        logger.error(f"Error getting categories: {str(e)}")
        return {"error": str(e)}


def _get_products_by_category_data(business: Business, category_name: str) -> dict:
    """Get products in a specific category."""
    try:
        # Find category by name (case insensitive)
        category = business.categories.filter(name__icontains=category_name).first()
        if not category:
            return {"error": f"Category '{category_name}' not found"}
        
        products = category.products.filter(active=True).order_by('name')
        products_data = []
        
        for product in products:
            products_data.append({
                "name": product.name,
                "sku": product.sku,
                "price_usd": float(product.price_usd),
                "price_lbp": product.price_lbp,
                "description": product.description,
                "metadata": product.metadata,
                "available": product.stock > 0
            })
        
        return {
            "category": category.name,
            "products": products_data,
            "total_products": len(products_data)
        }
    except Exception as e:
        logger.error(f"Error getting products by category: {str(e)}")
        return {"error": str(e)}


def _get_product_details_data(business: Business, product_name: str) -> dict:
    """Get detailed information about a specific product."""
    try:
        # Search for product by name (case insensitive)
        product = business.products.filter(
            name__icontains=product_name, 
            active=True
        ).first()
        
        if not product:
            return {"error": f"Product '{product_name}' not found"}
        
        return {
            "name": product.name,
            "sku": product.sku,
            "description": product.description,
            "price_usd": float(product.price_usd),
            "price_lbp": product.price_lbp,
            "category": product.category.name if product.category else None,
            "metadata": product.metadata,
            "available": product.stock > 0
        }
    except Exception as e:
        logger.error(f"Error getting product details: {str(e)}")
        return {"error": str(e)}


def _search_products_data(business: Business, search_term: str) -> dict:
    """Search for products by name or description."""
    try:
        products = business.products.filter(
            models.Q(name__icontains=search_term) | 
            models.Q(description__icontains=search_term),
            active=True
        ).order_by('name')[:10]  # Limit to 10 results
        
        products_data = []
        for product in products:
            products_data.append({
                "name": product.name,
                "sku": product.sku,
                "price_usd": float(product.price_usd),
                "price_lbp": product.price_lbp,
                "category": product.category.name if product.category else None,
                "available": product.stock > 0
            })
        
        return {
            "search_term": search_term,
            "products": products_data,
            "total_found": len(products_data)
        }
    except Exception as e:
        logger.error(f"Error searching products: {str(e)}")
        return {"error": str(e)}


def _identify_product_from_post_context(business: Business, post_caption: str, user_message: str) -> dict:
    """
    Identify product from post context when user replies to a post.
    
    Args:
        business: Business instance
        post_caption: Post caption that might contain product information
        user_message: User's message (e.g., 'price?', 'cost?')
        
    Returns:
        Product information if found, error if not found
    """
    try:
        logger.info(f"🔍 Identifying product from post context:")
        logger.info(f"🔍 Post caption: {post_caption}")
        logger.info(f"🔍 User message: {user_message}")
        
        # Extract potential product names from post caption
        import re
        
        # Look for product names in the caption
        # This is a simple approach - in production, you might use more sophisticated NLP
        caption_lower = post_caption.lower()
        logger.info(f"🔍 Caption (lowercase): {caption_lower}")
        
        # Search for products that might match the caption
        products = business.products.filter(active=True)
        matching_products = []
        
        for product in products:
            product_name_lower = product.name.lower()
            logger.info(f"🔍 Checking product: {product.name} (lowercase: {product_name_lower})")
            
            # Check if product name appears in caption (partial match)
            if product_name_lower in caption_lower or any(word in caption_lower for word in product_name_lower.split() if len(word) > 3):
                logger.info(f"✅ Found matching product: {product.name}")
                matching_products.append({
                    "name": product.name,
                    "sku": product.sku,
                    "price_usd": float(product.price_usd),
                    "price_lbp": product.price_lbp,
                    "description": product.description,
                    "category": product.category.name if product.category else None,
                    "available": product.stock > 0
                })
            else:
                logger.info(f"❌ No match for product: {product.name}")
        
        if matching_products:
            return {
                "found": True,
                "products": matching_products,
                "post_caption": post_caption,
                "user_message": user_message,
                "message": f"Found {len(matching_products)} product(s) mentioned in the post caption"
            }
        else:
            # If no exact matches, try searching by keywords from the caption
            caption_words = re.findall(r'\b\w+\b', caption_lower)
            keyword_matches = []
            
            for word in caption_words:
                if len(word) > 3:  # Only consider words longer than 3 characters
                    word_products = business.products.filter(
                        models.Q(name__icontains=word) | 
                        models.Q(description__icontains=word),
                        active=True
                    )[:3]  # Limit to 3 results per keyword
                    
                    for product in word_products:
                        keyword_matches.append({
                            "name": product.name,
                            "sku": product.sku,
                            "price_usd": float(product.price_usd),
                            "price_lbp": product.price_lbp,
                            "description": product.description,
                            "category": product.category.name if product.category else None,
                            "available": product.stock > 0,
                            "match_reason": f"Keyword '{word}' found in product name or description"
                        })
            
            if keyword_matches:
                return {
                    "found": True,
                    "products": keyword_matches[:5],  # Limit to 5 results
                    "post_caption": post_caption,
                    "user_message": user_message,
                    "message": f"Found {len(keyword_matches)} product(s) matching keywords from the post caption"
                }
            else:
                return {
                    "found": False,
                    "post_caption": post_caption,
                    "user_message": user_message,
                    "message": "No products found matching the post caption. Please specify the product name."
                }
        
    except Exception as e:
        logger.error(f"Error identifying product from post context: {str(e)}")
        return {"error": str(e)}


def _get_conversation_history(business_id: int, sender_id: Optional[str] = None) -> list:
    """
    Get recent conversation history for context.
    
    Args:
        business_id: Business ID
        sender_id: Optional sender ID for filtering
        
    Returns:
        List of conversation messages
    """
    from .models import MessageLog
    from django.utils import timezone
    from datetime import timedelta
    
    since = timezone.now() - timedelta(hours=2) # Reduced to 2 hours
    
    query = MessageLog.objects.filter(
        business_id=business_id,
        created_at__gte=since
    ).order_by('created_at')
    
    if sender_id:
        query = query.filter(sender_id=sender_id)
    
    recent_messages = query[:3] # Reduced to last 3 messages
    
    conversation = []
    for msg in recent_messages:
        if msg.incoming_text:
            conversation.append({"role": "user", "content": msg.incoming_text})
        if msg.reply_text:
            conversation.append({"role": "assistant", "content": msg.reply_text})
    
    return conversation


def _is_greeting_or_general_question(message: str) -> bool:
    """
    Check if message is a greeting or general question.
    
    Args:
        message: Customer message
        
    Returns:
        True if greeting/general question
    """
    message_lower = message.lower().strip()
    
    greetings = ['hello', 'hi', 'hey', 'good morning', 'good afternoon', 'good evening', 'what do you sell', 'what products do you have', 'what do you have']
    
    return any(greeting in message_lower for greeting in greetings)


def _should_show_products_directly(message: str) -> bool:
    """
    Check if message indicates user wants to see products directly.
    
    Args:
        message: Customer message
        
    Returns:
        True if user wants to see products
    """
    message_lower = message.lower().strip()
    
    product_requests = [
        'show me', 'show', 'products', 'options', 'available', 'other options', 'another options',
        'different options', 'more options', 'what do you have', 'what do you sell'
    ]
    
    return any(request in message_lower for request in product_requests)


def _get_fallback_response() -> str:
    """
    Get fallback response when AI fails.
    
    Returns:
        Safe fallback response
    """
    return "Thank you for your message! I'm currently having trouble processing your request. Please try again in a moment, or contact us directly for immediate assistance."


def test_ai_response(business_id: int, test_message: str = "Hello, what products do you have?") -> Dict[str, Any]:
    """
    Test AI response generation (for debugging/admin use).
    
    Args:
        business_id: Business ID to test
        test_message: Test message to send
        
    Returns:
        Dict with test results
    """
    try:
        response = get_ai_response(business_id, test_message)
        return {
            "success": True,
            "response": response,
            "business_id": business_id,
            "test_message": test_message
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "business_id": business_id,
            "test_message": test_message
        }