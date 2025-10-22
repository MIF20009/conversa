# Instagram Messaging Integration

This document provides testing instructions and setup guide for the Instagram messaging integration.

## Environment Variables Required

Create a `.env` file in the project root with the following variables:

```env
# Django Settings
SECRET_KEY=your-secret-key-here
DEBUG=True
DB_NAME=conversa_db
DB_USER=postgres
DB_PASSWORD=your-db-password
DB_HOST=localhost
DB_PORT=5432

# Facebook/Instagram Integration
FB_APP_ID=your-facebook-app-id
FB_APP_SECRET=your-facebook-app-secret
FB_GRAPH_VERSION=v17.0
FB_VERIFY_TOKEN=your-webhook-verify-token

# OpenAI Integration
OPENAI_API_KEY=your-openai-api-key
OPENAI_MODEL=gpt-3.5-turbo

# Development (optional)
NGROK_URL=your-ngrok-url.ngrok-free.app
```

## Facebook App Setup

### 1. Create Facebook App
1. Go to [Facebook Developers](https://developers.facebook.com/)
2. Create a new app with "Business" type
3. Add "Instagram Basic Display" and "Instagram Messaging" products

### 2. Required Permissions
The following permissions are required for Instagram messaging:
- `pages_show_list` - List user's pages
- `pages_read_engagement` - Read page engagement
- `instagram_basic` - Basic Instagram access
- `instagram_manage_messages` - Send/receive Instagram messages
- `pages_messaging` - Page messaging access

### 3. Webhook Configuration
1. In your Facebook App, go to "Webhooks" section
2. Add webhook URL: `https://your-domain.com/core/webhook/instagram/`
3. Subscribe to: `messages`, `messaging_postbacks`
4. Set verify token to match `FB_VERIFY_TOKEN` in your `.env`

## Local Development Setup

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run Migrations
```bash
python manage.py migrate
```

### 3. Create Superuser
```bash
python manage.py createsuperuser
```

### 4. Start Development Server
```bash
python manage.py runserver
```

### 5. Use ngrok for Webhook Testing
```bash
# Install ngrok
# Download from https://ngrok.com/

# Start ngrok tunnel
ngrok http 8000

# Use the HTTPS URL for webhook configuration
# Example: https://abc123.ngrok.io/core/webhook/instagram/
```

## Testing the Integration

### 1. Connect Instagram Account
1. Login to Django admin
2. Create a Business record
3. Navigate to: `http://localhost:8000/core/instagram/connect/{business_id}/`
4. Complete Facebook OAuth flow
5. Verify business has `instagram_page_id` and `page_access_token` set

### 2. Test Webhook Verification
```bash
curl -X GET "https://your-domain.com/core/webhook/instagram/?hub.mode=subscribe&hub.verify_token=your-verify-token&hub.challenge=test-challenge"
```

Expected response: `test-challenge`

### 3. Test AI Response Generation
```python
# In Django shell
python manage.py shell

from core.ai_chat import get_ai_response
from core.models import Business

# Test AI response
business = Business.objects.first()
response = get_ai_response(business.id, "Hello, what products do you have?")
print(response)
```

### 4. Test Instagram Message Sending
```python
# In Django shell
from core.instagram_api import send_instagram_text_reply
from core.models import Business

business = Business.objects.first()
result = send_instagram_text_reply(
    business.page_access_token,
    "recipient_instagram_id",
    "Test message from AI"
)
print(result)
```

### 5. Simulate Webhook Message
```bash
# Simulate incoming Instagram message
curl -X POST "https://your-domain.com/core/webhook/instagram/" \
  -H "Content-Type: application/json" \
  -H "X-Hub-Signature-256: sha256=your-signature" \
  -d '{
    "entry": [{
      "id": "page_id",
      "messaging": [{
        "sender": {"id": "user_id"},
        "message": {"text": "Hello, what products do you have?"}
      }]
    }]
  }'
```

## Production Deployment Notes

### 1. App Review Requirements
For production use, your Facebook App will need to go through App Review for these permissions:
- `instagram_basic`
- `instagram_manage_messages`
- `pages_messaging`

### 2. Security Considerations
- Always verify webhook signatures in production
- Use HTTPS for webhook URLs
- Store sensitive tokens securely
- Implement rate limiting for AI responses

### 3. Monitoring
- Check `MessageLog` model for message history and errors
- Monitor webhook delivery in Facebook App dashboard
- Set up logging for failed API calls

## Troubleshooting

### Common Issues

1. **OAuth Error**: Check `FB_APP_ID` and `FB_APP_SECRET` are correct
2. **Webhook Verification Failed**: Verify `FB_VERIFY_TOKEN` matches in app settings
3. **AI Not Responding**: Check `OPENAI_API_KEY` and business `ai_enabled` setting
4. **Messages Not Sending**: Verify `page_access_token` is valid and not expired

### Debug Commands

```python
# Check business Instagram connection
business = Business.objects.get(id=1)
print(f"Connected: {business.instagram_connected}")
print(f"Token Expired: {business.token_expired}")

# Test Instagram API
from core.instagram_api import get_user_pages
result = get_user_pages("user_access_token")
print(result)
```

## API Endpoints

### OAuth Flow
- `GET /core/instagram/connect/{business_id}/` - Start OAuth flow
- `GET /core/instagram/callback/{business_id}/` - OAuth callback

### Webhook
- `GET /core/webhook/instagram/` - Webhook verification
- `POST /core/webhook/instagram/` - Receive messages

### Admin Actions
- Clear Instagram tokens
- Subscribe page to app
- Test AI responses

## File Structure

```
conversa_ai/core/
├── models.py              # Business, Customer, MessageLog models
├── admin.py               # Admin interface with Instagram fields
├── views.py               # OAuth and webhook views
├── urls.py                # URL patterns
├── instagram_api.py       # Instagram Graph API helpers
├── ai_chat.py            # OpenAI integration
└── migrations/
    └── 0002_auto_instagram_integration.py
```

## Support

For issues with this integration:
1. Check Django logs for errors
2. Verify all environment variables are set
3. Test with Facebook's webhook testing tools
4. Review Instagram Graph API documentation
