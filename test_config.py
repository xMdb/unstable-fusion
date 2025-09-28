#!/usr/bin/env python3
"""
Test script to verify the configuration system works
"""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_config():
    """Test the configuration system"""
    try:
        print("Testing configuration system...")
        
        # Test importing config
        print("1. Importing config module...")
        import config
        print("   ✓ Config module imported successfully")
        
        # Test key configuration values
        print("2. Checking key configuration values...")
        print(f"   Database URL: {'✓ Set' if config.DB_URL else '✗ Missing'}")
        print(f"   JWT Secret: {'✓ Set' if config.JWT_SECRET else '✗ Missing'}")
        print(f"   AWS Available: {'✓ Yes' if config.config_manager.aws_available else '✗ No'}")
        print(f"   Frontend Dir: {config.FRONTEND_DIST_DIR}")
        print(f"   Default Model: {config.DEFAULT_MODEL}")
        
        # Test main app import
        print("3. Testing main app import...")
        import main
        print("   ✓ Main app imported successfully")
        
        print("\n✅ All tests passed! Configuration system is working.")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_config()
    sys.exit(0 if success else 1)