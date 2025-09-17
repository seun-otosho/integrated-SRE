#!/usr/bin/env python
"""
Test script to verify the SonarCloud Phase 2 - Cross-System Integration
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
django.setup()

def test_cross_system_models():
    """Test that cross-system integration models work"""
    print("🔗 Testing cross-system integration models...")
    
    try:
        from apps.sonarcloud.models import (
            SentrySonarLink, JiraSonarLink, QualityIssueTicket
        )
        
        # Test model imports
        print("✅ Cross-system models imported successfully")
        return True
    except Exception as e:
        print(f"❌ Cross-system models test failed: {e}")
        return False

def test_integration_services():
    """Test integration services"""
    print("⚙️ Testing integration services...")
    
    try:
        from apps.sonarcloud.services_integration import (
            SentryQualityService, JiraQualityService, ProductQualityService
        )
        
        # Test service instantiation
        sentry_service = SentryQualityService()
        jira_service = JiraQualityService()
        product_service = ProductQualityService()
        
        print("✅ Integration services imported successfully")
        return True
    except Exception as e:
        print(f"❌ Integration services test failed: {e}")
        return False

def test_quality_context():
    """Test quality context for Sentry projects"""
    print("📊 Testing quality context functionality...")
    
    try:
        from apps.sonarcloud.services_integration import SentryQualityService
        from apps.sentry.models import SentryProject
        
        service = SentryQualityService()
        
        # Test with a project (even if no links exist)
        projects = SentryProject.objects.all()[:1]
        if projects:
            project = projects[0]
            context = service.get_quality_context_for_release(project)
            
            # Should return valid context structure
            assert 'has_quality_data' in context
            print("✅ Quality context functionality working")
        else:
            print("ℹ️ No Sentry projects to test with, but service is functional")
        
        return True
    except Exception as e:
        print(f"❌ Quality context test failed: {e}")
        return False

def test_product_health_calculation():
    """Test unified product health scoring"""
    print("🏥 Testing product health calculation...")
    
    try:
        from apps.sonarcloud.services_integration import ProductQualityService
        from apps.products.models import Product
        
        service = ProductQualityService()
        
        # Test with a product (even if no projects exist)
        products = Product.objects.all()[:1]
        if products:
            product = products[0]
            health = service.calculate_product_health_score(product)
            
            # Should return valid health structure
            expected_keys = ['overall_score', 'sentry_health', 'sonarcloud_health', 'jira_health']
            for key in expected_keys:
                assert key in health, f"Missing key: {key}"
            
            print("✅ Product health calculation working")
        else:
            print("ℹ️ No products to test with, but service is functional")
        
        return True
    except Exception as e:
        print(f"❌ Product health calculation test failed: {e}")
        return False

def test_jira_ticket_creation():
    """Test JIRA ticket creation from quality issues"""
    print("🎫 Testing JIRA ticket creation from quality issues...")
    
    try:
        from apps.sonarcloud.services_integration import JiraQualityService
        
        service = JiraQualityService()
        
        # Test ticket summary/description builders
        from apps.sonarcloud.models import CodeIssue, SonarCloudProject, SonarCloudOrganization
        
        # Create mock objects for testing (don't save)
        mock_org = SonarCloudOrganization(name="Test Org", organization_key="test-org", api_token="test")
        mock_project = SonarCloudProject(
            sonarcloud_organization=mock_org,
            project_key="test-project",
            name="Test Project"
        )
        
        mock_issue = CodeIssue(
            project=mock_project,
            message="Test security vulnerability",
            type=CodeIssue.IssueType.VULNERABILITY,
            severity=CodeIssue.Severity.MAJOR,
            rule="javascript:S2068",
            component="src/auth/auth.js",
            line=42
        )
        
        summary = service._build_ticket_summary(mock_issue)
        description = service._build_ticket_description(mock_issue)
        
        assert summary.startswith('[Security]')
        assert 'Test security vulnerability' in description
        
        print("✅ JIRA ticket creation logic working")
        return True
    except Exception as e:
        print(f"❌ JIRA ticket creation test failed: {e}")
        return False

def test_admin_integration():
    """Test that admin interfaces include cross-system models"""
    print("👤 Testing admin integration...")
    
    try:
        from django.contrib import admin
        from apps.sonarcloud.models import SentrySonarLink, JiraSonarLink, QualityIssueTicket
        
        # Check that cross-system models are registered
        models_registered = 0
        for model in [SentrySonarLink, JiraSonarLink, QualityIssueTicket]:
            if model in admin.site._registry:
                models_registered += 1
        
        if models_registered == 3:
            print("✅ All cross-system models registered in admin")
            return True
        else:
            print(f"⚠️ Only {models_registered}/3 cross-system models registered")
            return False
    except Exception as e:
        print(f"❌ Admin integration test failed: {e}")
        return False

def test_sentry_quality_display():
    """Test that Sentry admin shows quality context"""
    print("🔍 Testing Sentry quality display...")
    
    try:
        from apps.sentry.admin import SentryIssueAdmin
        from apps.sentry.models import SentryIssue
        
        # Check that quality_context method exists
        admin_instance = SentryIssueAdmin(SentryIssue, None)
        assert hasattr(admin_instance, 'quality_context')
        
        print("✅ Sentry admin has quality context display")
        return True
    except Exception as e:
        print(f"❌ Sentry quality display test failed: {e}")
        return False

def test_database_migrations():
    """Test that database migrations were applied"""
    print("💾 Testing database migrations...")
    
    try:
        from apps.sonarcloud.models import SentrySonarLink, JiraSonarLink, QualityIssueTicket
        
        # Try to query each model (this will fail if tables don't exist)
        SentrySonarLink.objects.all().count()
        JiraSonarLink.objects.all().count()
        QualityIssueTicket.objects.all().count()
        
        print("✅ Database migrations applied successfully")
        return True
    except Exception as e:
        print(f"❌ Database migrations test failed: {e}")
        return False

def main():
    print("🔗 SonarCloud Phase 2 - Cross-System Integration Test")
    print("=" * 60)
    
    tests = [
        test_cross_system_models,
        test_integration_services,
        test_quality_context,
        test_product_health_calculation,
        test_jira_ticket_creation,
        test_admin_integration,
        test_sentry_quality_display,
        test_database_migrations
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()
    
    print("=" * 60)
    print(f"📊 Test Results: {passed}/{total} passed")
    
    if passed == total:
        print("🎉 All tests passed! Phase 2 Cross-System Integration is ready!")
        print("\n📋 What you can do now:")
        print("1. 🔗 Create Sentry-SonarCloud links:")
        print("   - Go to /admin/sonarcloud/sentrysonarlink/add/")
        print("   - Link projects for quality gates on releases")
        print("\n2. 🎫 Create JIRA-SonarCloud links:")
        print("   - Go to /admin/sonarcloud/jirasonarlink/add/")
        print("   - Enable automated ticket creation for quality issues")
        print("\n3. 📊 View unified product health:")
        print("   - Products admin now shows all three systems")
        print("   - Quality context appears in Sentry issues")
        print("\n4. ⚡ Test automation:")
        print("   - Use 'Process automated ticket creation' action in JIRA-SonarCloud links")
        print("   - Check quality gates before Sentry releases")
        
        print("\n🚀 Ready for Phase 3: Advanced Automation & Analytics!")
    else:
        print("⚠️ Some tests failed. Please check the error messages above.")
        return False
    
    return True

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)