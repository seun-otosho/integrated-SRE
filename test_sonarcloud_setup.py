#!/usr/bin/env python
"""
Test script to verify the SonarCloud Integration setup
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
django.setup()

def test_sonarcloud_models():
    """Test that all SonarCloud models can be imported and basic operations work"""
    print("🧪 Testing SonarCloud models...")
    
    try:
        from apps.sonarcloud.models import (
            SonarCloudOrganization, SonarCloudProject, QualityMeasurement,
            CodeIssue, SonarSyncLog
        )
        
        # Test model creation (without saving)
        org = SonarCloudOrganization(
            name="Test SonarCloud Org",
            organization_key="test-org",
            api_token="test-token"
        )
        
        print("✅ SonarCloud models imported successfully")
        return True
    except Exception as e:
        print(f"❌ SonarCloud model test failed: {e}")
        return False

def test_sonarcloud_client():
    """Test that the SonarCloud client can be instantiated"""
    print("🌐 Testing SonarCloud API client...")
    
    try:
        from apps.sonarcloud.client import SonarCloudAPIClient
        
        client = SonarCloudAPIClient(api_token="dummy-token")
        print("✅ SonarCloud client created successfully")
        return True
    except Exception as e:
        print(f"❌ SonarCloud client test failed: {e}")
        return False

def test_sonarcloud_services():
    """Test that SonarCloud services can be imported"""
    print("⚙️ Testing SonarCloud services...")
    
    try:
        from apps.sonarcloud.services import SonarCloudSyncService, sync_sonarcloud_organization
        print("✅ SonarCloud services imported successfully")
        return True
    except Exception as e:
        print(f"❌ SonarCloud services test failed: {e}")
        return False

def test_sonarcloud_admin():
    """Test that SonarCloud admin interface is properly configured"""
    print("👤 Testing SonarCloud admin configuration...")
    
    try:
        from django.contrib import admin
        from apps.sonarcloud.models import SonarCloudOrganization
        
        if SonarCloudOrganization in admin.site._registry:
            print("✅ SonarCloud admin configuration loaded successfully")
            return True
        else:
            print("❌ SonarCloud admin configuration not found")
            return False
    except Exception as e:
        print(f"❌ SonarCloud admin test failed: {e}")
        return False

def test_sonarcloud_urls():
    """Test that SonarCloud URLs can be resolved"""
    print("🔗 Testing SonarCloud URL configuration...")
    
    try:
        from django.urls import reverse
        
        # Test main SonarCloud URLs
        dashboard_url = reverse('sonarcloud:dashboard')
        organizations_url = reverse('sonarcloud:organizations')
        
        print("✅ SonarCloud URLs resolved successfully")
        print(f"   Dashboard: {dashboard_url}")
        print(f"   Organizations: {organizations_url}")
        return True
    except Exception as e:
        print(f"❌ SonarCloud URL test failed: {e}")
        return False

def test_sonarcloud_management_command():
    """Test that SonarCloud management command exists"""
    print("💻 Testing SonarCloud management command...")
    
    try:
        from django.core.management import get_commands
        commands = get_commands()
        
        if 'sync_sonarcloud' in commands:
            print("✅ Management command 'sync_sonarcloud' available")
            return True
        else:
            print("❌ Management command 'sync_sonarcloud' not found")
            return False
    except Exception as e:
        print(f"❌ SonarCloud management command test failed: {e}")
        return False

def test_product_integration():
    """Test that SonarCloud integrates with Products"""
    print("🔗 Testing Product integration...")
    
    try:
        # Test that SonarCloud projects can reference Products
        from apps.sonarcloud.models import SonarCloudProject
        from apps.products.models import Product
        
        # Check that foreign key relationship exists
        project_fields = [f.name for f in SonarCloudProject._meta.get_fields()]
        
        if 'product' in project_fields:
            print("✅ Product integration configured successfully")
            return True
        else:
            print("❌ Product integration not found")
            return False
    except Exception as e:
        print(f"❌ Product integration test failed: {e}")
        return False

def test_client_utility_functions():
    """Test utility functions in the client"""
    print("🔧 Testing client utility functions...")
    
    try:
        from apps.sonarcloud.client import (
            parse_sonar_datetime, convert_rating_to_letter, convert_technical_debt
        )
        
        # Test rating conversion
        assert convert_rating_to_letter('1') == 'A'
        assert convert_rating_to_letter('5') == 'E'
        
        # Test debt conversion
        assert convert_technical_debt('30min') == 30
        assert convert_technical_debt('2h') == 120
        
        print("✅ Client utility functions working correctly")
        return True
    except Exception as e:
        print(f"❌ Client utility functions test failed: {e}")
        return False

def main():
    print("📊 SonarCloud Integration - Setup Test")
    print("=" * 50)
    
    tests = [
        test_sonarcloud_models,
        test_sonarcloud_client,
        test_sonarcloud_services,
        test_sonarcloud_admin,
        test_sonarcloud_urls,
        test_sonarcloud_management_command,
        test_product_integration,
        test_client_utility_functions
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
        print("🎉 All tests passed! Your SonarCloud Integration is ready to use.")
        print("\n📋 Next steps:")
        print("1. Start the server: python manage.py runserver")
        print("2. Go to http://localhost:8000/admin/sonarcloud/sonarcloudorganization/add/")
        print("3. Add your SonarCloud organization with API token")
        print("4. Visit http://localhost:8000/sonarcloud/ to see the dashboard")
        print("5. Run: python manage.py sync_sonarcloud --test-connection")
        print("\n💡 To get a SonarCloud API token:")
        print("   - Go to https://sonarcloud.io/account/security")
        print("   - Generate a new token with appropriate permissions")
    else:
        print("⚠️ Some tests failed. Please check the error messages above.")
        return False
    
    return True

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)