#!/usr/bin/env python3
"""
Google OAuth setup helper.
This script helps you configure Google OAuth for the Pytitan data service.
"""

import webbrowser
from urllib.parse import urlencode

def print_google_oauth_setup():
    """Print step-by-step Google OAuth setup instructions"""
    
    print("=== Google OAuth Setup for Pytitan Data Service ===\n")
    
    print("📋 STEP-BY-STEP INSTRUCTIONS:")
    print()
    
    print("1. 🌐 GO TO GOOGLE CLOUD CONSOLE")
    print("   https://console.cloud.google.com/")
    print("   (This will open in your browser)")
    
    # Open Google Cloud Console
    try:
        webbrowser.open("https://console.cloud.google.com/")
        print("   ✅ Opened Google Cloud Console in your browser")
    except:
        print("   ⚠️  Could not open browser automatically")
    
    print()
    print("2. 📁 CREATE OR SELECT PROJECT")
    print("   - Create a new project or select existing one")
    print("   - Note the project name for reference")
    print()
    
    print("3. 🔧 ENABLE APIS")
    print("   - Go to: APIs & Services → Library")
    print("   - Search for and enable: 'Google+ API'")
    print("   - Also enable: 'Google Identity' (if available)")
    print()
    
    print("4. 🎯 CREATE OAUTH 2.0 CREDENTIALS")
    print("   - Go to: APIs & Services → Credentials")
    print("   - Click: 'Create Credentials' → 'OAuth 2.0 Client IDs'")
    print("   - Choose: 'Web application'")
    print("   - Name: 'Pytitan Data Service'")
    print()
    
    print("5. 🔗 CONFIGURE AUTHORIZED REDIRECT URIS")
    print("   Add these URIs:")
    print("   - http://localhost:8000/auth/callback")
    print("   - http://localhost:3000/auth/callback  (if using React dev server)")
    print("   - https://yourdomain.com/auth/callback  (for production)")
    print()
    
    print("6. 📝 COPY CLIENT ID")
    print("   - After creating credentials, copy the 'Client ID'")
    print("   - It looks like: xxxxxx.apps.googleusercontent.com")
    print("   - Add this to your .env file as GOOGLE_CLIENT_ID")
    print()
    
    print("7. ⚙️  CONFIGURE OAUTH CONSENT SCREEN")
    print("   - Go to: APIs & Services → OAuth consent screen")
    print("   - Choose: 'External' user type")
    print("   - Fill required fields:")
    print("     * App name: Pytitan Data Service")
    print("     * User support email: your-email@domain.com")
    print("     * Developer contact: your-email@domain.com")
    print("   - Add scopes:")
    print("     * openid")
    print("     * email") 
    print("     * profile")
    print("   - Add test users: your-email@domain.com")
    print()
    
    print("8. ✅ UPDATE .ENV FILE")
    print("   Add this line to your .env file:")
    print("   GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com")
    print()
    
    print("9. 🧪 TEST AUTHENTICATION")
    print("   - Start the application: uvicorn app.main:app --reload")
    print("   - Visit: http://localhost:8000/docs")
    print("   - Try the /me endpoint with a Google ID token")
    print()

def generate_test_token_url():
    """Generate a URL for testing OAuth flow"""
    
    print("🔗 QUICK TEST URL GENERATOR")
    print("   Use this URL to test your OAuth setup:")
    print()
    
    # This would be a test URL, but we need the actual client ID
    print("   https://accounts.google.com/oauth/authorize?")
    print("   client_id=YOUR_CLIENT_ID&")
    print("   redirect_uri=http://localhost:8000/auth/callback&")
    print("   scope=openid email profile&")
    print("   response_type=code")
    print()
    print("   (Replace YOUR_CLIENT_ID with your actual client ID)")

def main():
    print_google_oauth_setup()
    generate_test_token_url()
    
    print("📚 ADDITIONAL RESOURCES:")
    print("   - Google OAuth 2.0 Documentation: https://developers.google.com/identity/protocols/oauth2")
    print("   - Google Sign-In JavaScript: https://developers.google.com/identity/sign-in/web")
    print("   - FastAPI OAuth Documentation: https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/")
    print()
    
    print("🎉 Once setup is complete, your app will support:")
    print("   ✅ Google Sign-In authentication")
    print("   ✅ JWT token validation")
    print("   ✅ Role-based access control")
    print("   ✅ Secure API endpoints")

if __name__ == "__main__":
    main()
