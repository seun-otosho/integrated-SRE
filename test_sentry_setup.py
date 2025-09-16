#!/usr/bin/env python
"""
Test script to verify the Sentry Management System setup
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
django.setup()

def test_models():
    """Test that all models can be imported and basic operations work"""
    print("🧪 Testing models...")
    
    try:
        from apps.sentry.models import (
            SentryOrganization, SentryProject, SentryIssue, 
            SentryEvent, SentrySyncLog
        )
        
        # Test model creation (without saving)
        org = SentryOrganization(
            sentry_id="test",
            slug="test-org",
            name="Test Organization",
            api_token="test-token"
        )
        
        print("✅ Models imported successfully")
        return True
    except Exception as e:
        print(f"❌ Model test failed: {e}")
        return False

def test_client():
    """Test that the Sentry client can be instantiated"""
    print("🌐 Testing Sentry API client...")
    
    try:
        from apps.sentry.client import SentryAPIClient
        
        client = SentryAPIClient("dummy-token")
        print("✅ Sentry client created successfully")
        return True
    except Exception as e:
        print(f"❌ Client test failed: {e}")
        return False

def test_services():
    """Test that services can be imported"""
    print("⚙️ Testing services...")
    
    try:
        from apps.sentry.services import SentrySyncService, sync_all_organizations
        print("✅ Services imported successfully")
        return True
    except Exception as e:
        print(f"❌ Services test failed: {e}")
        return False

def test_admin():
    """Test that admin interface is properly configured"""
    print("👤 Testing admin configuration...")
    
    try:
        from django.contrib import admin
        from apps.sentry.models import SentryOrganization
        
        if SentryOrganization in admin.site._registry:
            print("✅ Admin configuration loaded successfully")
            return True
        else:
            print("❌ Admin configuration not found")
            return False
    except Exception as e:
        print(f"❌ Admin test failed: {e}")
        return False

def test_urls():
    """Test that URLs can be resolved"""
    print("🔗 Testing URL configuration...")
    
    try:
        from django.urls import reverse
        
        # Test main dashboard URL
        dashboard_url = reverse('sentry:dashboard')
        organizations_url = reverse('sentry:organizations')
        
        print("✅ URLs resolved successfully")
        print(f"   Dashboard: {dashboard_url}")
        print(f"   Organizations: {organizations_url}")
        return True
    except Exception as e:
        print(f"❌ URL test failed: {e}")
        return False

def test_management_command():
    """Test that management command exists"""
    print("💻 Testing management command...")
    
    try:
        from django.core.management import get_commands
        commands = get_commands()
        
        if 'sync_sentry' in commands:
            print("✅ Management command 'sync_sentry' available")
            return True
        else:
            print("❌ Management command 'sync_sentry' not found")
            return False
    except Exception as e:
        print(f"❌ Management command test failed: {e}")
        return False

def main():
    print("🔍 Sentry Management System - Setup Test")
    print("=" * 50)
    
    tests = [
        test_models,
        test_client,
        test_services,
        test_admin,
        test_urls,
        test_management_command
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()
    
    print("=" * 50)
    print(f"📊 Test Results: {passed}/{total} passed")
    
    if passed == total:
        print("🎉 All tests passed! Your Sentry Management System is ready to use.")
        print("\n📋 Next steps:")
        print("1. Start the server: python manage.py runserver")
        print("2. Go to http://localhost:8000/admin/sentry/sentryorganization/add/")
        print("3. Add your Sentry organization with API token")
        print("4. Visit http://localhost:8000/sentry/ to see the dashboard")
    else:
        print("⚠️ Some tests failed. Please check the error messages above.")
        return False
    
    return True

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)