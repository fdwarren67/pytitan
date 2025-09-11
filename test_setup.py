#!/usr/bin/env python3
"""
Test script to verify the Pytitan data service setup.
This script tests environment variables, Snowflake connection, and basic app functionality.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

def test_environment():
    """Test environment variables"""
    print("🔍 Testing Environment Variables...")
    
    load_dotenv()
    
    required_vars = [
        'SNOWFLAKE_ACCOUNT',
        'SNOWFLAKE_WAREHOUSE', 
        'SNOWFLAKE_USER',
        'SNOWFLAKE_PRIVATE_KEY_PATH',
        'GOOGLE_CLIENT_ID'
    ]
    
    missing_vars = []
    for var in required_vars:
        value = os.getenv(var)
        if not value:
            missing_vars.append(var)
            print(f"   ❌ {var}: Not set")
        else:
            # Mask sensitive values
            if 'KEY' in var or 'SECRET' in var:
                display_value = f"{value[:8]}..." if len(value) > 8 else "***"
            else:
                display_value = value
            print(f"   ✅ {var}: {display_value}")
    
    if missing_vars:
        print(f"\n❌ Missing required environment variables: {', '.join(missing_vars)}")
        return False
    
    print("   ✅ All required environment variables are set")
    return True

def test_private_key():
    """Test private key file exists and is readable"""
    print("\n🔑 Testing Private Key File...")
    
    key_path = os.getenv('SNOWFLAKE_PRIVATE_KEY_PATH', './snowflake_private_key.pem')
    key_file = Path(key_path)
    
    if not key_file.exists():
        print(f"   ❌ Private key file not found: {key_path}")
        return False
    
    try:
        with open(key_file, 'r') as f:
            content = f.read()
            if 'BEGIN PRIVATE KEY' in content:
                print(f"   ✅ Private key file is valid: {key_path}")
                return True
            else:
                print(f"   ❌ Private key file appears invalid: {key_path}")
                return False
    except Exception as e:
        print(f"   ❌ Error reading private key file: {e}")
        return False

def test_snowflake_connection():
    """Test Snowflake connection"""
    print("\n❄️  Testing Snowflake Connection...")
    
    try:
        # Add app directory to path
        sys.path.insert(0, str(Path(__file__).parent / "app"))
        
        from mysnowflake import _describe_view_snowflake
        
        # Test with the first view from config
        import yaml
        config_path = Path("config/views.yaml")
        if not config_path.exists():
            print("   ❌ config/views.yaml not found")
            return False
            
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        
        entities = config.get("entities", {})
        if not entities:
            print("   ❌ No entities found in config/views.yaml")
            return False
        
        # Test with first entity
        first_entity = list(entities.keys())[0]
        first_view = entities[first_entity]["view"]
        
        print(f"   Testing connection to: {first_view}")
        columns = _describe_view_snowflake(first_view)
        
        print(f"   ✅ Snowflake connection successful!")
        print(f"   ✅ Found {len(columns)} columns in {first_view}")
        return True
        
    except Exception as e:
        print(f"   ❌ Snowflake connection failed: {e}")
        return False

def test_app_imports():
    """Test that the app can be imported"""
    print("\n📦 Testing App Imports...")
    
    try:
        sys.path.insert(0, str(Path(__file__).parent / "app"))
        
        # Test main imports
        from main import app
        print("   ✅ FastAPI app imported successfully")
        
        from myfilter import SearchModel, FilterCollection
        print("   ✅ Filter models imported successfully")
        
        from myregistry import Registry
        print("   ✅ Registry imported successfully")
        
        from myauth import verify_google_id_token
        print("   ✅ Auth module imported successfully")
        
        return True
        
    except Exception as e:
        print(f"   ❌ App import failed: {e}")
        return False

def test_config_files():
    """Test configuration files"""
    print("\n📋 Testing Configuration Files...")
    
    # Test views.yaml
    views_path = Path("config/views.yaml")
    if views_path.exists():
        try:
            import yaml
            with open(views_path, "r") as f:
                config = yaml.safe_load(f)
            entities = config.get("entities", {})
            print(f"   ✅ config/views.yaml: {len(entities)} entities configured")
        except Exception as e:
            print(f"   ❌ config/views.yaml: Error reading file - {e}")
            return False
    else:
        print("   ❌ config/views.yaml: File not found")
        return False
    
    # Test columns cache
    cache_path = Path("config/columns_cache.json")
    if cache_path.exists():
        print("   ✅ config/columns_cache.json: Cache file exists")
    else:
        print("   ℹ️  config/columns_cache.json: Cache file will be created on first run")
    
    return True

def main():
    print("=== Pytitan Data Service Setup Test ===\n")
    
    tests = [
        test_environment,
        test_private_key, 
        test_config_files,
        test_app_imports,
        test_snowflake_connection
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"   ❌ Test failed with exception: {e}")
            results.append(False)
    
    print(f"\n📊 TEST RESULTS:")
    passed = sum(results)
    total = len(results)
    
    if passed == total:
        print(f"   🎉 All tests passed! ({passed}/{total})")
        print(f"\n✅ Your Pytitan data service is ready to run!")
        print(f"   Start the server with: uvicorn app.main:app --reload")
    else:
        print(f"   ⚠️  {passed}/{total} tests passed")
        print(f"\n❌ Please fix the failing tests before running the application")
        print(f"   Check the SETUP_GUIDE.md for detailed instructions")

if __name__ == "__main__":
    main()
