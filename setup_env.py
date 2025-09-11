#!/usr/bin/env python3
"""
Setup script to create .env file for pytitan data service.
Run this script and follow the prompts to configure your environment.
"""

import os
from pathlib import Path

def create_env_file():
    """Interactive setup for .env file"""
    env_path = Path(".env")
    
    if env_path.exists():
        response = input(".env file already exists. Overwrite? (y/N): ")
        if response.lower() != 'y':
            print("Setup cancelled.")
            return
    
    print("=== Pytitan Data Service Environment Setup ===\n")
    
    # Snowflake Configuration
    print("1. SNOWFLAKE CONFIGURATION")
    print("   (You can find these in your Snowflake account settings)")
    snowflake_account = input("   Snowflake Account Name: ").strip()
    snowflake_warehouse = input("   Snowflake Warehouse: ").strip()
    snowflake_user = input("   Snowflake Username: ").strip()
    snowflake_database = input("   Snowflake Database [PLAYGROUND]: ").strip() or "PLAYGROUND"
    snowflake_schema = input("   Snowflake Schema [STYX]: ").strip() or "STYX"
    snowflake_role = input("   Snowflake Default Role: ").strip()
    
    # Google OAuth
    print("\n2. GOOGLE OAUTH CONFIGURATION")
    print("   (Get this from Google Cloud Console > APIs & Services > Credentials)")
    google_client_id = input("   Google Client ID: ").strip()
    
    # CORS
    print("\n3. CORS CONFIGURATION")
    cors_origins = input("   Allowed Origins [http://localhost:3000]: ").strip() or "http://localhost:3000"
    
    # Optional settings
    print("\n4. OPTIONAL SETTINGS")
    max_page_size = input("   Max Page Size [1000]: ").strip() or "1000"
    
    # Generate JWT secrets
    import secrets
    jwt_secret = secrets.token_urlsafe(32)
    refresh_secret = secrets.token_urlsafe(32)
    
    # Create .env content
    env_content = f"""# Snowflake Configuration
SNOWFLAKE_ACCOUNT={snowflake_account}
SNOWFLAKE_WAREHOUSE={snowflake_warehouse}
SNOWFLAKE_USER={snowflake_user}
SNOWFLAKE_PRIVATE_KEY_PATH=./snowflake_private_key.pem
SNOWFLAKE_DATABASE={snowflake_database}
SNOWFLAKE_SCHEMA={snowflake_schema}
SNOWFLAKE_DEFAULT_ROLE={snowflake_role}

# Authentication
GOOGLE_CLIENT_ID={google_client_id}

# CORS
CORS_ALLOW_ORIGINS={cors_origins}

# Pagination
GLOBAL_MAX_PAGE_SIZE={max_page_size}

# File paths
VIEWS_FILE=config/views.yaml
COLUMNS_CACHE_FILE=config/columns_cache.json

# JWT Configuration (auto-generated)
APP_JWT_SECRET={jwt_secret}
APP_REFRESH_SECRET={refresh_secret}
APP_JWT_ISS=http://localhost:8000
APP_JWT_AUD=data-service
ACCESS_TOKEN_TTL_SECONDS=900
REFRESH_TOKEN_TTL_SECONDS=2592000
REFRESH_COOKIE_NAME=refresh
REFRESH_COOKIE_PATH=/auth/refresh
REFRESH_COOKIE_SAMESITE=Lax
REFRESH_COOKIE_SECURE=false
REFRESH_COOKIE_HTTPONLY=true
"""
    
    # Write .env file
    with open(env_path, 'w') as f:
        f.write(env_content)
    
    print(f"\n✅ .env file created successfully!")
    print(f"📁 Location: {env_path.absolute()}")
    print("\n📋 Next steps:")
    print("   1. Set up Snowflake private key authentication")
    print("   2. Configure Google OAuth in Google Cloud Console")
    print("   3. Run the application")

if __name__ == "__main__":
    create_env_file()
