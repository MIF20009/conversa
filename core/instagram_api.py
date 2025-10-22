"""
Instagram Graph API helper functions for messaging integration.

This module provides helper functions for:
- Sending text messages via Instagram API
- Subscribing pages to app for webhook notifications
- Token exchange operations
"""

import os
import requests
import logging
from typing import Dict, Any, Optional
from django.conf import settings

logger = logging.getLogger(__name__)

# Environment variables
FB_APP_ID = os.getenv('FB_APP_ID')
FB_APP_SECRET = os.getenv('FB_APP_SECRET')
FB_GRAPH_VERSION = os.getenv('FB_GRAPH_VERSION', 'v17.0')
FB_VERIFY_TOKEN = os.getenv('FB_VERIFY_TOKEN')

# Graph API base URL
GRAPH_API_BASE = f"https://graph.facebook.com/{FB_GRAPH_VERSION}"


def send_instagram_text_reply(page_access_token: str, recipient_id: str, text: str) -> Dict[str, Any]:
    """
    Send a text message via Instagram Graph API.
    
    Args:
        page_access_token: Page access token for the Instagram business account
        recipient_id: Instagram user ID to send message to
        text: Message text to send
        
    Returns:
        Dict containing API response or error information
        
    API Endpoint: POST https://graph.facebook.com/{version}/me/messages
    """
    url = f"{GRAPH_API_BASE}/me/messages"
    
    # Correct payload format for Instagram messaging
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text}
    }
    
    # Use access_token as URL parameter, not in payload
    params = {
        "access_token": page_access_token
    }
    
    try:
        response = requests.post(url, json=payload, params=params, timeout=30)
        
        # Log the response for debugging
        logger.info(f"Instagram API Response Status: {response.status_code}")
        logger.info(f"Instagram API Response: {response.text}")
        
        if response.status_code == 200:
            result = response.json()
            logger.info(f"Successfully sent Instagram message to {recipient_id}")
            return {"success": True, "data": result}
        else:
            error_msg = f"Instagram API Error {response.status_code}: {response.text}"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}
        
    except requests.exceptions.RequestException as e:
        error_msg = f"Failed to send Instagram message: {str(e)}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg}
    
    except Exception as e:
        error_msg = f"Unexpected error sending Instagram message: {str(e)}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg}


def subscribe_page_to_app(page_id: str, page_access_token: str) -> Dict[str, Any]:
    """
    Subscribe a Facebook Page to the app for webhook notifications.
    
    Args:
        page_id: Facebook Page ID
        page_access_token: Page access token
        
    Returns:
        Dict containing API response or error information
        
    API Endpoint: POST https://graph.facebook.com/{version}/{page_id}/subscribed_apps
    """
    url = f"{GRAPH_API_BASE}/{page_id}/subscribed_apps"
    
    payload = {
        "subscribed_fields": "messages,messaging_postbacks",
        "access_token": page_access_token
    }
    
    try:
        response = requests.post(url, data=payload, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        logger.info(f"Successfully subscribed page {page_id} to app")
        return {"success": True, "data": result}
        
    except requests.exceptions.RequestException as e:
        error_msg = f"Failed to subscribe page {page_id}: {str(e)}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg}
    
    except Exception as e:
        error_msg = f"Unexpected error subscribing page {page_id}: {str(e)}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg}


def exchange_code_for_token(code: str, redirect_uri: str) -> Dict[str, Any]:
    """
    Exchange authorization code for short-lived user access token.
    
    Args:
        code: Authorization code from OAuth callback
        redirect_uri: Redirect URI used in OAuth flow
        
    Returns:
        Dict containing token information or error
        
    API Endpoint: GET https://graph.facebook.com/{version}/oauth/access_token
    """
    url = f"{GRAPH_API_BASE}/oauth/access_token"
    
    params = {
        "client_id": FB_APP_ID,
        "client_secret": FB_APP_SECRET,
        "redirect_uri": redirect_uri,
        "code": code
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        logger.info("Successfully exchanged code for short-lived token")
        return {"success": True, "data": result}
        
    except requests.exceptions.RequestException as e:
        error_msg = f"Failed to exchange code for token: {str(e)}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg}
    
    except Exception as e:
        error_msg = f"Unexpected error exchanging code: {str(e)}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg}


def exchange_short_lived_for_long_lived(short_lived_token: str) -> Dict[str, Any]:
    """
    Exchange short-lived user token for long-lived user token.
    
    Args:
        short_lived_token: Short-lived user access token
        
    Returns:
        Dict containing long-lived token information or error
        
    API Endpoint: GET https://graph.facebook.com/{version}/oauth/access_token
    """
    url = f"{GRAPH_API_BASE}/oauth/access_token"
    
    params = {
        "grant_type": "fb_exchange_token",
        "client_id": FB_APP_ID,
        "client_secret": FB_APP_SECRET,
        "fb_exchange_token": short_lived_token
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        logger.info("Successfully exchanged short-lived token for long-lived token")
        return {"success": True, "data": result}
        
    except requests.exceptions.RequestException as e:
        error_msg = f"Failed to exchange short-lived token: {str(e)}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg}
    
    except Exception as e:
        error_msg = f"Unexpected error exchanging short-lived token: {str(e)}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg}


def get_user_pages(user_access_token: str) -> Dict[str, Any]:
    """
    Get Facebook Pages that the user manages.
    
    Args:
        user_access_token: User access token
        
    Returns:
        Dict containing pages information or error
        
    API Endpoint: GET https://graph.facebook.com/{version}/me/accounts
    """
    url = f"{GRAPH_API_BASE}/me/accounts"
    
    params = {
        "access_token": user_access_token,
        "fields": "id,name,instagram_business_account,access_token"
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        logger.info("Successfully retrieved user pages")
        return {"success": True, "data": result}
        
    except requests.exceptions.RequestException as e:
        error_msg = f"Failed to get user pages: {str(e)}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg}
    
    except Exception as e:
        error_msg = f"Unexpected error getting user pages: {str(e)}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg}


def get_page_access_token(page_id: str, user_access_token: str) -> Dict[str, Any]:
    """
    Get page access token for a specific page.
    
    Args:
        page_id: Facebook Page ID
        user_access_token: User access token
        
    Returns:
        Dict containing page access token information or error
        
    API Endpoint: GET https://graph.facebook.com/{version}/{page_id}
    """
    url = f"{GRAPH_API_BASE}/{page_id}"
    
    params = {
        "access_token": user_access_token,
        "fields": "access_token,instagram_business_account"
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        logger.info(f"Successfully retrieved page access token for {page_id}")
        return {"success": True, "data": result}
        
    except requests.exceptions.RequestException as e:
        error_msg = f"Failed to get page access token for {page_id}: {str(e)}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg}
    
    except Exception as e:
        error_msg = f"Unexpected error getting page access token for {page_id}: {str(e)}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg}


def verify_webhook_signature(payload: str, signature: str) -> bool:
    """
    Verify webhook signature using X-Hub-Signature-256 header.
    
    Args:
        payload: Raw request body
        signature: X-Hub-Signature-256 header value
        
    Returns:
        True if signature is valid, False otherwise
    """
    if not FB_APP_SECRET:
        logger.warning("FB_APP_SECRET not configured, skipping signature verification")
        return True
    
    import hmac
    import hashlib
    
    try:
        # Remove 'sha256=' prefix if present
        if signature.startswith('sha256='):
            signature = signature[7:]
        
        # Create expected signature
        expected_signature = hmac.new(
            FB_APP_SECRET.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Compare signatures
        return hmac.compare_digest(signature, expected_signature)
        
    except Exception as e:
        logger.error(f"Error verifying webhook signature: {str(e)}")
        return False
