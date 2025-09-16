#!/usr/bin/env python
"""
Test script to verify the JIRA Integration setup
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
django.setup()

def test_jira_models():
    """Test that all JIRA models can be imported and basic operations work"""
    print("🧪 Testing JIRA models...")
    
    try:
        from apps.jira.models import (
            JiraOrganization, JiraProject, JiraIssue, 
            SentryJiraLink, JiraSyncLog
        )
        
        # Test model creation (without saving)
        org = JiraOrganization(
            name="Test JIRA",
            base_url="https://test.atlassian.net",
            username="test@example.com",
            api_token="test-token"
        )
        
        print("✅ JIRA models imported successfully")
        return True
    except Exception as e:
        print(f"❌ JIRA model test failed: {e}")
        return False

def test_jira_client():
    """Test that the JIRA client can be instantiated"""
    print("🌐 Testing JIRA API client...")
    
    try:
        from apps.jira.client import JiraAPIClient
        
        client = JiraAPIClient(
            base_url="https://test.atlassian.net",
            username="test@example.com", 
            api_token="dummy-token"
        )
        print("✅ JIRA client created successfully")
        return True
    except Exception as e:
        print(f"❌ JIRA client test failed: {e}")
        return False

def test_jira_services():
    """Test that JIRA services can be imported"""
    print("⚙️ Testing JIRA services...")
    
    try:
        from apps.jira.services import JiraSyncService, SentryJiraLinkService
        print("✅ JIRA services imported successfully")
        return True
    except Exception as e:
        print(f"❌ JIRA services test failed: {e}")
        return False

def test_jira_admin():
    """Test that JIRA admin interface is properly configured"""
    print("👤 Testing JIRA admin configuration...")
    
    try:
        from django.contrib import admin
        from apps.jira.models import JiraOrganization
        
        if JiraOrganization in admin.site._registry:
            print("✅ JIRA admin configuration loaded successfully")
            return True
        else:
            print("❌ JIRA admin configuration not found")
            return False
    except Exception as e:
        print(f"❌ JIRA admin test failed: {e}")
        return False

def test_jira_urls():
    """Test that JIRA URLs can be resolved"""
    print("🔗 Testing JIRA URL configuration...")
    
    try:
        from django.urls import reverse
        
        # Test main JIRA URLs
        dashboard_url = reverse('jira:dashboard')
        organizations_url = reverse('jira:organizations')
        
        print("✅ JIRA URLs resolved successfully")
        print(f"   Dashboard: {dashboard_url}")
        print(f"   Organizations: {organizations_url}")
        return True
    except Exception as e:
        print(f"❌ JIRA URL test failed: {e}")
        return False

def test_jira_management_command():
    """Test that JIRA management command exists"""
    print("💻 Testing JIRA management command...")
    
    try:
        from django.core.management import get_commands
        commands = get_commands()
        
        if 'sync_jira' in commands:
            print("✅ Management command 'sync_jira' available")
            return True
        else:
            print("❌ Management command 'sync_jira' not found")
            return False
    except Exception as e:
        print(f"❌ JIRA management command test failed: {e}")
        return False

def test_cross_integration():
    """Test that cross-system integration is working"""
    print("🔗 Testing cross-system integration...")
    
    try:
        # Test that JIRA models can reference Sentry and Products
        from apps.jira.models import JiraProject, SentryJiraLink
        from apps.sentry.models import SentryIssue
        from apps.products.models import Product
        
        # Check that foreign key relationships exist
        jira_project_fields = [f.name for f in JiraProject._meta.get_fields()]
        link_fields = [f.name for f in SentryJiraLink._meta.get_fields()]
        
        if 'product' in jira_project_fields and 'sentry_issue' in link_fields:
            print("✅ Cross-system relationships configured successfully")
            return True
        else:
            print("❌ Cross-system relationships not found")
            return False
    except Exception as e:
        print(f"❌ Cross-integration test failed: {e}")
        return False

def main():
    print("🎯 JIRA Integration - Setup Test")
    print("=" * 50)
    
    tests = [
        test_jira_models,
        test_jira_client,
        test_jira_services,
        test_jira_admin,
        test_jira_urls,
        test_jira_management_command,
        test_cross_integration
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
        print("🎉 All tests passed! Your JIRA Integration is ready to use.")
        print("\n📋 Next steps:")
        print("1. Start the server: python manage.py runserver")
        print("2. Go to http://localhost:8000/admin/jira/jiraorganization/add/")
        print("3. Add your JIRA organization with API token")
        print("4. Visit http://localhost:8000/jira/ to see the dashboard")
        print("5. Run: python manage.py sync_jira --test-connection")
    else:
        print("⚠️ Some tests failed. Please check the error messages above.")
        return False
    
    return True

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)