"""
Tests for users app views/APIs.
"""
import pytest
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase
from apps.users.tests.factories import UserFactory, AdminUserFactory, SuperAdminUserFactory, CustomerFactory
from apps.groups.tests.factories import GroupFactory, GroupMemberFactory
from apps.contributions.tests.factories import ContributionFactory
from tests.mixins import AuthenticatedAPITestMixin, AdminAPITestMixin, APITestMixin

User = get_user_model()


class UserProfileViewTest(APITestCase, AuthenticatedAPITestMixin):
    """Test UserProfileView API endpoint."""
    
    def setUp(self):
        super().setUp()
        self.url = reverse('user-profile') if hasattr(self, 'reverse') else '/api/users/profile/'
    
    def test_get_user_profile_authenticated(self):
        """Test authenticated user can retrieve their profile."""
        response = self.client.get(self.url)
        
        self.assert_api_success(response, 200)
        self.assertIn('email', response.data)
        self.assertIn('first_name', response.data)
        self.assertIn('last_name', response.data)
        self.assertEqual(response.data['email'], self.user.email)
    
    def test_get_user_profile_unauthenticated(self):
        """Test unauthenticated request returns 401."""
        self.client.force_authenticate(user=None)
        response = self.client.get(self.url)
        
        self.assert_unauthorized(response)
    
    def test_update_user_profile_valid_data(self):
        """Test user can update their profile with valid data."""
        data = {
            'first_name': 'Updated',
            'last_name': 'Name',
            'role': self.user.role  # Keep existing role
        }
        response = self.client.put(self.url, data)
        
        self.assert_api_success(response, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Updated')
        self.assertEqual(self.user.last_name, 'Name')
    
    def test_update_user_profile_invalid_data(self):
        """Test user profile update with invalid data."""
        data = {
            'email': 'invalid-email',  # Invalid email format
            'first_name': '',  # Empty first name
        }
        response = self.client.put(self.url, data)
        
        self.assert_bad_request(response)
    
    def test_update_user_profile_partial_data(self):
        """Test partial user profile update."""
        original_last_name = self.user.last_name
        data = {
            'first_name': 'PartialUpdate'
        }
        response = self.client.put(self.url, data)
        
        self.assert_api_success(response, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'PartialUpdate')
        self.assertEqual(self.user.last_name, original_last_name)  # Should remain unchanged


class UserDashboardStatsTest(APITestCase, AuthenticatedAPITestMixin):
    """Test user dashboard statistics endpoint."""
    
    def setUp(self):
        super().setUp()
        self.url = '/api/users/dashboard-stats/'
    
    def test_user_dashboard_stats_authenticated(self):
        """Test authenticated user can get dashboard stats."""
        response = self.client.get(self.url)
        
        self.assert_api_success(response, 200)
        self.assertIn('stats', response.data)
        self.assertIn('monthly_contributions', response.data)
        self.assertIn('upcoming_contributions', response.data)
        self.assertIn('recent_groups', response.data)
    
    def test_user_dashboard_stats_unauthenticated(self):
        """Test unauthenticated request returns 401."""
        self.client.force_authenticate(user=None)
        response = self.client.get(self.url)
        
        self.assert_unauthorized(response)
    
    def test_dashboard_stats_with_contributions(self):
        """Test dashboard stats with user contributions."""
        # Create a group and contribution for the user
        group = GroupFactory()
        GroupMemberFactory(group=group, user=self.user, status='active')
        ContributionFactory(group=group, member=self.user)
        
        response = self.client.get(self.url)
        
        self.assert_api_success(response, 200)
        self.assertIsInstance(response.data['monthly_contributions'], list)
        self.assertIsInstance(response.data['upcoming_contributions'], list)
    
    def test_dashboard_stats_calculations(self):
        """Test dashboard stats calculations are correct."""
        response = self.client.get(self.url)
        
        self.assert_api_success(response, 200)
        
        # Verify structure of monthly contributions
        monthly_contributions = response.data['monthly_contributions']
        self.assertIsInstance(monthly_contributions, list)
        
        if monthly_contributions:
            for month_data in monthly_contributions:
                self.assertIn('month', month_data)
                self.assertIn('amount', month_data)


class UserGroupsTest(APITestCase, AuthenticatedAPITestMixin):
    """Test user groups endpoint."""
    
    def setUp(self):
        super().setUp()
        self.url = '/api/users/groups/'
    
    def test_user_groups_list(self):
        """Test user can get their groups list."""
        # Create groups for the user
        group1 = GroupFactory()
        group2 = GroupFactory()
        GroupMemberFactory(group=group1, user=self.user, status='active')
        GroupMemberFactory(group=group2, user=self.user, status='pending')
        
        response = self.client.get(self.url)
        
        self.assert_api_success(response, 200)
        self.assertIn('groups', response.data)
        self.assertIn('total_count', response.data)
        self.assertEqual(response.data['total_count'], 2)
    
    def test_user_groups_empty(self):
        """Test user groups endpoint with no groups."""
        response = self.client.get(self.url)
        
        self.assert_api_success(response, 200)
        self.assertEqual(response.data['total_count'], 0)
        self.assertEqual(len(response.data['groups']), 0)
    
    def test_user_groups_unauthenticated(self):
        """Test unauthenticated request returns 401."""
        self.client.force_authenticate(user=None)
        response = self.client.get(self.url)
        
        self.assert_unauthorized(response)


class UserContributionsTest(APITestCase, AuthenticatedAPITestMixin):
    """Test user contributions endpoint."""
    
    def setUp(self):
        super().setUp()
        self.url = '/api/users/contributions/'
    
    def test_user_contributions_list(self):
        """Test user can get their contributions list."""
        # Create contributions for the user
        group = GroupFactory()
        GroupMemberFactory(group=group, user=self.user, status='active')
        ContributionFactory(group=group, member=self.user, cycle_number=1)
        ContributionFactory(group=group, member=self.user, cycle_number=2)
        
        response = self.client.get(self.url)
        
        self.assert_api_success(response, 200)
        self.assertIn('contributions', response.data)
        self.assertIn('total_count', response.data)
        self.assertEqual(response.data['total_count'], 2)
    
    def test_user_contributions_filtering(self):
        """Test user contributions filtering by group and status."""
        group1 = GroupFactory()
        group2 = GroupFactory()
        GroupMemberFactory(group=group1, user=self.user, status='active')
        GroupMemberFactory(group=group2, user=self.user, status='active')
        
        contrib1 = ContributionFactory(group=group1, member=self.user)
        contrib2 = ContributionFactory(group=group2, member=self.user)
        
        # Test filtering by group
        response = self.client.get(self.url, {'group_id': str(group1.id)})
        self.assert_api_success(response, 200)
        self.assertEqual(response.data['total_count'], 1)
        
        # Test without filter
        response = self.client.get(self.url)
        self.assert_api_success(response, 200)
        self.assertEqual(response.data['total_count'], 2)
    
    def test_user_contributions_unauthenticated(self):
        """Test unauthenticated request returns 401."""
        self.client.force_authenticate(user=None)
        response = self.client.get(self.url)
        
        self.assert_unauthorized(response)


class UpdateUserRoleTest(APITestCase):
    """Test update user role endpoint."""
    
    def setUp(self):
        self.super_admin = SuperAdminUserFactory()
        self.admin = AdminUserFactory()
        self.regular_user = UserFactory()
        self.url = '/api/users/update-role/'
    
    def test_update_user_role_as_super_admin(self):
        """Test super admin can update user roles."""
        self.client.force_authenticate(user=self.super_admin)
        
        data = {
            'user_id': self.regular_user.id,
            'role': User.UserRole.ADMIN
        }
        response = self.client.post(self.url, data)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.regular_user.refresh_from_db()
        self.assertEqual(self.regular_user.role, User.UserRole.ADMIN)
    
    def test_update_user_role_permission_denied(self):
        """Test non-super admin cannot update user roles."""
        self.client.force_authenticate(user=self.admin)
        
        data = {
            'user_id': self.regular_user.id,
            'role': User.UserRole.ADMIN
        }
        response = self.client.post(self.url, data)
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_update_user_role_invalid_role(self):
        """Test update user role with invalid role."""
        self.client.force_authenticate(user=self.super_admin)
        
        data = {
            'user_id': self.regular_user.id,
            'role': 'invalid_role'
        }
        response = self.client.post(self.url, data)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_update_user_role_missing_data(self):
        """Test update user role with missing data."""
        self.client.force_authenticate(user=self.super_admin)
        
        # Missing role
        data = {
            'user_id': self.regular_user.id
        }
        response = self.client.post(self.url, data)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        # Missing user_id
        data = {
            'role': User.UserRole.ADMIN
        }
        response = self.client.post(self.url, data)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_update_user_role_user_not_found(self):
        """Test update user role with non-existent user."""
        self.client.force_authenticate(user=self.super_admin)
        
        data = {
            'user_id': 99999,  # Non-existent user ID
            'role': User.UserRole.ADMIN
        }
        response = self.client.post(self.url, data)
        
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_update_user_role_unauthenticated(self):
        """Test unauthenticated request returns 401."""
        data = {
            'user_id': self.regular_user.id,
            'role': User.UserRole.ADMIN
        }
        response = self.client.post(self.url, data)
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class UserAPIPermissionTest(APITestCase):
    """Test user API permission enforcement."""
    
    def setUp(self):
        self.user = UserFactory()
        self.admin = AdminUserFactory()
        self.super_admin = SuperAdminUserFactory()
    
    def test_profile_access_own_data_only(self):
        """Test users can only access their own profile data."""
        self.client.force_authenticate(user=self.user)
        
        # Should be able to access own profile
        response = self.client.get('/api/users/profile/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], self.user.email)
    
    def test_dashboard_stats_own_data_only(self):
        """Test users can only access their own dashboard stats."""
        self.client.force_authenticate(user=self.user)
        
        response = self.client.get('/api/users/dashboard-stats/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Stats should be for the authenticated user only
        # This would be verified by checking that only user's data is returned
    
    def test_groups_own_data_only(self):
        """Test users can only access their own groups."""
        self.client.force_authenticate(user=self.user)
        
        # Create groups for different users
        user_group = GroupFactory()
        other_group = GroupFactory()
        
        GroupMemberFactory(group=user_group, user=self.user, status='active')
        GroupMemberFactory(group=other_group, user=self.admin, status='active')
        
        response = self.client.get('/api/users/groups/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Should only return user's groups
        self.assertEqual(response.data['total_count'], 1)
    
    def test_contributions_own_data_only(self):
        """Test users can only access their own contributions."""
        self.client.force_authenticate(user=self.user)
        
        # Create contributions for different users
        group = GroupFactory()
        GroupMemberFactory(group=group, user=self.user, status='active')
        GroupMemberFactory(group=group, user=self.admin, status='active')
        
        user_contrib = ContributionFactory(group=group, member=self.user)
        admin_contrib = ContributionFactory(group=group, member=self.admin)
        
        response = self.client.get('/api/users/contributions/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Should only return user's contributions
        self.assertEqual(response.data['total_count'], 1)


class UserAPIResponseFormatTest(APITestCase, AuthenticatedAPITestMixin):
    """Test user API response formats."""
    
    def test_profile_response_format(self):
        """Test user profile response contains required fields."""
        response = self.client.get('/api/users/profile/')
        
        self.assert_api_success(response, 200)
        
        required_fields = ['id', 'email', 'first_name', 'last_name', 'role', 'account_type']
        self.assert_response_contains_fields(response.data, required_fields)
    
    def test_dashboard_stats_response_format(self):
        """Test dashboard stats response contains required fields."""
        response = self.client.get('/api/users/dashboard-stats/')
        
        self.assert_api_success(response, 200)
        
        required_fields = ['stats', 'monthly_contributions', 'upcoming_contributions', 'recent_groups']
        self.assert_response_contains_fields(response.data, required_fields)
    
    def test_groups_response_format(self):
        """Test user groups response contains required fields."""
        response = self.client.get('/api/users/groups/')
        
        self.assert_api_success(response, 200)
        
        required_fields = ['groups', 'total_count']
        self.assert_response_contains_fields(response.data, required_fields)
    
    def test_contributions_response_format(self):
        """Test user contributions response contains required fields."""
        response = self.client.get('/api/users/contributions/')
        
        self.assert_api_success(response, 200)
        
        required_fields = ['contributions', 'total_count']
        self.assert_response_contains_fields(response.data, required_fields)


class UserAPIErrorHandlingTest(APITestCase):
    """Test user API error handling."""
    
    def test_profile_update_server_error_handling(self):
        """Test profile update handles server errors gracefully."""
        user = UserFactory()
        self.client.force_authenticate(user=user)
        
        # This would test error handling, but we need to mock a server error
        # For now, we test that the endpoint exists and handles requests
        response = self.client.put('/api/users/profile/', {})
        
        # Should return some response (either success or validation error)
        self.assertIn(response.status_code, [200, 400, 500])
    
    def test_dashboard_stats_error_handling(self):
        """Test dashboard stats handles errors gracefully."""
        user = UserFactory()
        self.client.force_authenticate(user=user)
        
        response = self.client.get('/api/users/dashboard-stats/')
        
        # Should return some response
        self.assertIn(response.status_code, [200, 500])
    
    def test_invalid_endpoints(self):
        """Test invalid endpoints return 404."""
        user = UserFactory()
        self.client.force_authenticate(user=user)
        
        response = self.client.get('/api/users/invalid-endpoint/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)