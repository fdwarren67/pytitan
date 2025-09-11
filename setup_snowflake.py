#!/usr/bin/env python3
"""
Snowflake private key setup helper.
This script helps you generate and configure a private key for Snowflake authentication.
"""

import os
import subprocess
import sys
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

def generate_private_key():
    """Generate a new RSA private key for Snowflake"""
    print("🔑 Generating new RSA private key...")
    
    # Generate private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    
    # Save as PEM format
    key_path = Path("snowflake_private_key.pem")
    with open(key_path, "wb") as key_file:
        key_file.write(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            )
        )
    
    print(f"✅ Private key generated: {key_path.absolute()}")
    
    # Get public key for Snowflake
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    
    # Extract the key content (remove headers)
    public_key_content = public_pem.decode('utf-8')
    public_key_content = public_key_content.replace('-----BEGIN PUBLIC KEY-----\n', '')
    public_key_content = public_key_content.replace('\n-----END PUBLIC KEY-----\n', '')
    public_key_content = public_key_content.replace('\n', '')
    
    print(f"\n📋 PUBLIC KEY FOR SNOWFLAKE:")
    print(f"   Copy this key and add it to your Snowflake user:")
    print(f"   {public_key_content}")
    
    return key_path, public_key_content

def check_existing_key():
    """Check if a private key already exists"""
    key_path = Path("snowflake_private_key.pem")
    if key_path.exists():
        print(f"🔍 Found existing private key: {key_path.absolute()}")
        response = input("   Use existing key? (Y/n): ").strip().lower()
        if response != 'n':
            return key_path, None
    return None, None

def test_snowflake_connection():
    """Test the Snowflake connection"""
    print("\n🧪 Testing Snowflake connection...")
    
    try:
        # Import the snowflake module from the app
        sys.path.insert(0, str(Path(__file__).parent / "app"))
        from mysnowflake import _describe_view_snowflake
        
        # Try to connect using the first view from config
        import yaml
        with open("config/views.yaml", "r") as f:
            config = yaml.safe_load(f)
        
        first_entity = list(config["entities"].keys())[0]
        first_view = config["entities"][first_entity]["view"]
        
        print(f"   Testing connection to: {first_view}")
        columns = _describe_view_snowflake(first_view)
        print(f"✅ Connection successful! Found {len(columns)} columns.")
        return True
        
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False

def main():
    print("=== Snowflake Private Key Setup ===\n")
    
    # Check for existing key
    existing_key, _ = check_existing_key()
    
    if existing_key:
        key_path = existing_key
    else:
        # Generate new key
        key_path, public_key = generate_private_key()
        
        print(f"\n📝 SNOWFLAKE SETUP INSTRUCTIONS:")
        print(f"   1. Log into your Snowflake account")
        print(f"   2. Go to: Account > Users > [Your User] > Public Keys")
        print(f"   3. Click 'Add Public Key'")
        print(f"   4. Paste the public key shown above")
        print(f"   5. Save the changes")
        print(f"\n   ⚠️  Make sure your .env file has the correct SNOWFLAKE_* values!")
        
        input("\n   Press Enter when you've added the public key to Snowflake...")
    
    # Test connection
    if test_snowflake_connection():
        print(f"\n🎉 Snowflake setup complete!")
        print(f"   Private key: {key_path.absolute()}")
    else:
        print(f"\n❌ Setup incomplete. Please check:")
        print(f"   1. Your .env file has correct Snowflake credentials")
        print(f"   2. The public key is added to your Snowflake user")
        print(f"   3. Your user has access to the database/schema")

if __name__ == "__main__":
    main()
