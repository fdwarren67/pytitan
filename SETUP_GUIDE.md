# Pytitan Data Service Setup Guide

This guide will help you set up the Pytitan data service with Snowflake and Google OAuth authentication.

## Prerequisites

- Python 3.8+ with virtual environment activated
- Snowflake account with appropriate permissions
- Google Cloud Console project with OAuth credentials

## Step 1: Environment Configuration ✅

The `.env` file already exists. Make sure it contains the required variables:

```bash
# Snowflake Configuration
SNOWFLAKE_ACCOUNT=your-account-name
SNOWFLAKE_WAREHOUSE=your-warehouse-name
SNOWFLAKE_USER=your-username
SNOWFLAKE_PRIVATE_KEY_PATH=./snowflake_private_key.pem
SNOWFLAKE_DATABASE=PLAYGROUND
SNOWFLAKE_SCHEMA=STYX
SNOWFLAKE_DEFAULT_ROLE=your-role

# Authentication
GOOGLE_CLIENT_ID=your-google-client-id.apps.googleusercontent.com

# CORS
CORS_ALLOW_ORIGINS=http://localhost:3000,http://localhost:8080
```

## Step 2: Snowflake Private Key Authentication

### Option A: Use the Setup Script
```bash
python3 setup_snowflake.py
```

### Option B: Manual Setup

1. **Generate a private key:**
   ```bash
   openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out snowflake_private_key.pem -nocrypt
   ```

2. **Extract the public key:**
   ```bash
   openssl rsa -in snowflake_private_key.pem -pubout -outform DER | openssl base64 -A
   ```

3. **Add public key to Snowflake:**
   - Log into Snowflake web interface
   - Go to: Account → Users → [Your User] → Public Keys
   - Click "Add Public Key"
   - Paste the base64-encoded public key
   - Save changes

4. **Verify permissions:**
   - Ensure your user has access to the `PLAYGROUND.STYX` database/schema
   - Verify you can query the views listed in `config/views.yaml`

## Step 3: Google OAuth Setup

### 1. Create Google Cloud Project
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable the Google+ API

### 2. Create OAuth 2.0 Credentials
1. Go to: APIs & Services → Credentials
2. Click "Create Credentials" → "OAuth 2.0 Client IDs"
3. Choose "Web application"
4. Add authorized redirect URIs:
   - `http://localhost:8000/auth/callback` (for development)
   - Your production domain callback URL
5. Copy the Client ID and add it to your `.env` file

### 3. Configure OAuth Consent Screen
1. Go to: APIs & Services → OAuth consent screen
2. Choose "External" user type
3. Fill in required fields:
   - App name: "Pytitan Data Service"
   - User support email: your email
   - Developer contact: your email
4. Add scopes:
   - `openid`
   - `email`
   - `profile`
5. Add test users (your email address)

## Step 4: Test the Setup

### 1. Test Snowflake Connection
```bash
python3 -c "
import sys
sys.path.append('app')
from mysnowflake import _describe_view_snowflake
try:
    cols = _describe_view_snowflake('PLAYGROUND.STYX.CM_COUNTY_VW')
    print(f'✅ Snowflake connection successful! Found {len(cols)} columns.')
except Exception as e:
    print(f'❌ Snowflake connection failed: {e}')
"
```

### 2. Start the Application
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Test Endpoints
- Health check: `http://localhost:8000/healthz`
- API docs: `http://localhost:8000/docs`
- Entities: `http://localhost:8000/entities` (requires authentication)

## Step 5: Authentication Flow

### For Frontend Integration
1. **Get Google ID Token:**
   ```javascript
   // Use Google Sign-In JavaScript library
   gapi.auth2.getAuthInstance().signIn().then(function(googleUser) {
     const idToken = googleUser.getAuthResponse().id_token;
     // Use this token in Authorization header
   });
   ```

2. **Make Authenticated Requests:**
   ```javascript
   fetch('/search', {
     method: 'POST',
     headers: {
       'Authorization': `Bearer ${idToken}`,
       'Content-Type': 'application/json'
     },
     body: JSON.stringify({
       entityName: 'County',
       filter: {
         logicalOperator: 'And',
         expressions: []
       }
     })
   });
   ```

## Troubleshooting

### Common Issues

1. **Snowflake Connection Failed**
   - Verify private key path in `.env`
   - Check public key is added to Snowflake user
   - Ensure user has database/schema access

2. **Google OAuth Failed**
   - Verify `GOOGLE_CLIENT_ID` in `.env`
   - Check OAuth consent screen is configured
   - Ensure redirect URIs are correct

3. **CORS Issues**
   - Add your frontend domain to `CORS_ALLOW_ORIGINS`
   - Check browser developer tools for CORS errors

### Logs and Debugging
- Application logs: Check terminal output when running uvicorn
- Snowflake logs: Check Snowflake web interface → History
- Google OAuth: Check Google Cloud Console → APIs & Services → Credentials

## Security Notes

- Keep your `.env` file secure and never commit it to version control
- Rotate private keys regularly
- Use HTTPS in production
- Implement proper CORS policies
- Consider rate limiting for production use

## Next Steps

Once setup is complete:
1. Test all endpoints with your frontend
2. Configure production environment variables
3. Set up monitoring and logging
4. Consider implementing additional security measures
