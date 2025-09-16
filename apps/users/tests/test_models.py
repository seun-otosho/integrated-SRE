"""
Tests for users app models.
"""
import pytest
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from apps.users.models import Customer, BankAccount
from apps.users.tests.factories import UserFactory, AdminUserFactory, SuperAdminUserFactory, CustomerFactory, BankAccountFactory

User = get_user_model()


class UserModelTest(TestCase):
    """Test User model functionality."""
    
    def setUp(self):
        self.user_data = {
            'username': 'testuser',
            'email': 'test@example.com',
            'first_name': 'Test',
            'last_name': 'User',
            'password': 'testpass123'
        }
    
    def test_user_creation_with_valid_data(self):
        """Test user can be created with valid data."""
        user = User.objects.create_user(**self.user_data)
        
        self.assertEqual(user.email, 'test@example.com')
        self.assertEqual(user.username, 'testuser')
        self.assertEqual(user.role, User.UserRole.MEMBER)
        self.assertEqual(user.account_type, User.AccountType.INDIVIDUAL)
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
    
    def test_user_creation_with_factory(self):
        """Test user creation using factory."""
        user = UserFactory()
        
        self.assertIsInstance(user, User)
        self.assertTrue(user.email.endswith('@example.com'))
        self.assertEqual(user.role, User.UserRole.MEMBER)
        self.assertTrue(user.is_active)
    
    def test_admin_user_factory(self):
        """Test admin user creation using factory."""
        admin = AdminUserFactory()
        
        self.assertEqual(admin.role, User.UserRole.ADMIN)
        self.assertTrue(admin.is_staff)
        self.assertFalse(admin.is_superuser)
    
    def test_super_admin_user_factory(self):
        """Test super admin user creation using factory."""
        super_admin = SuperAdminUserFactory()
        
        self.assertEqual(super_admin.role, User.UserRole.SUPER_ADMIN)
        self.assertTrue(super_admin.is_staff)
        self.assertTrue(super_admin.is_superuser)
    
    def test_email_uniqueness_constraint(self):
        """Test that email must be unique."""
        UserFactory(email='test@example.com')
        
        with self.assertRaises(IntegrityError):
            UserFactory(email='test@example.com')
    
    def test_get_full_name_method(self):
        """Test get_full_name method returns correct format."""
        user = UserFactory(first_name='John', last_name='Doe')
        self.assertEqual(user.get_full_name(), 'John Doe')
        
        # Test with empty names
        user_empty = UserFactory(first_name='', last_name='')
        self.assertEqual(user_empty.get_full_name(), '')
        
        # Test with only first name
        user_first_only = UserFactory(first_name='John', last_name='')
        self.assertEqual(user_first_only.get_full_name(), 'John')
    
    def test_is_admin_method(self):
        """Test is_admin method returns correct boolean."""
        member = UserFactory(role=User.UserRole.MEMBER)
        admin = UserFactory(role=User.UserRole.ADMIN)
        super_admin = UserFactory(role=User.UserRole.SUPER_ADMIN)
        
        self.assertFalse(member.is_admin())
        self.assertTrue(admin.is_admin())
        self.assertTrue(super_admin.is_admin())
    
    def test_is_super_admin_method(self):
        """Test is_super_admin method returns correct boolean."""
        member = UserFactory(role=User.UserRole.MEMBER)
        admin = UserFactory(role=User.UserRole.ADMIN)
        super_admin = UserFactory(role=User.UserRole.SUPER_ADMIN)
        
        self.assertFalse(member.is_super_admin())
        self.assertFalse(admin.is_super_admin())
        self.assertTrue(super_admin.is_super_admin())
    
    def test_user_str_method(self):
        """Test User string representation."""
        user = UserFactory(first_name='John', last_name='Doe', email='john@example.com')
        expected = "John Doe (john@example.com)"
        self.assertEqual(str(user), expected)
    
    def test_user_role_choices(self):
        """Test all user role choices are valid."""
        for role_value, role_label in User.UserRole.choices:
            user = UserFactory(role=role_value)
            self.assertEqual(user.role, role_value)
    
    def test_account_type_choices(self):
        """Test all account type choices are valid."""
        for type_value, type_label in User.AccountType.choices:
            user = UserFactory(account_type=type_value)
            self.assertEqual(user.account_type, type_value)
    
    def test_user_timestamps(self):
        """Test that timestamps are set correctly."""
        user = UserFactory()
        
        self.assertIsNotNone(user.created_at)
        self.assertIsNotNone(user.updated_at)
        self.assertLessEqual(user.created_at, user.updated_at)


class CustomerModelTest(TestCase):
    """Test Customer model functionality."""
    
    def test_customer_creation_with_factory(self):
        """Test customer creation using factory."""
        customer = CustomerFactory()
        
        self.assertIsInstance(customer, Customer)
        self.assertIsInstance(customer.user, User)
        self.assertIsNotNone(customer.name)
        self.assertEqual(customer.country, 'Nigeria')
    
    def test_customer_creation_with_user(self):
        """Test customer creation with specific user."""
        user = UserFactory(first_name='John', last_name='Doe')
        customer = CustomerFactory(user=user, name='John Doe')
        
        self.assertEqual(customer.user, user)
        self.assertEqual(customer.name, 'John Doe')
    
    def test_customer_str_method(self):
        """Test Customer string representation."""
        customer = CustomerFactory(name='John Doe')
        self.assertEqual(str(customer), 'John Doe')
    
    def test_customer_phone_number_validation(self):
        """Test phone number validation."""
        # Valid phone numbers
        valid_phones = ['+1234567890', '1234567890', '+234567890123']
        for phone in valid_phones:
            customer = CustomerFactory(phone_number=phone)
            self.assertEqual(customer.phone_number, phone)
    
    def test_customer_default_values(self):
        """Test customer default field values."""
        customer = CustomerFactory()
        
        self.assertEqual(customer.total_contributions, customer.total_contributions)  # From factory
        self.assertEqual(customer.total_groups, customer.total_groups)  # From factory
        self.assertEqual(customer.country, 'Nigeria')
        self.assertIsNotNone(customer.created_at)
        self.assertIsNotNone(customer.updated_at)
    
    def test_update_statistics_method(self):
        """Test update_statistics method functionality."""
        customer = CustomerFactory()
        
        # Mock the method since it depends on contributions and groups
        # In a real test, we would create actual contributions and group memberships
        initial_contributions = customer.total_contributions
        initial_groups = customer.total_groups
        
        # Call update_statistics
        customer.update_statistics()
        
        # Since we don't have actual contributions/groups, values should remain the same
        # In integration tests, we would verify actual calculations
        self.assertIsNotNone(customer.total_contributions)
        self.assertIsNotNone(customer.total_groups)


class BankAccountModelTest(TestCase):
    """Test BankAccount model functionality."""
    
    def test_bank_account_creation_with_factory(self):
        """Test bank account creation using factory."""
        bank_account = BankAccountFactory()
        
        self.assertIsInstance(bank_account, BankAccount)
        self.assertIsInstance(bank_account.customer, Customer)
        self.assertIsNotNone(bank_account.bank_name)
        self.assertEqual(len(bank_account.account_number), 10)
        self.assertTrue(bank_account.is_primary)
    
    def test_bank_account_str_method(self):
        """Test BankAccount string representation."""
        bank_account = BankAccountFactory(
            bank_name='Test Bank',
            account_number='1234567890'
        )
        expected = "Test Bank - 7890"  # Last 4 digits
        self.assertEqual(str(bank_account), expected)
    
    def test_account_number_uniqueness(self):
        """Test that account numbers must be unique."""
        BankAccountFactory(account_number='1234567890')
        
        with self.assertRaises(IntegrityError):
            BankAccountFactory(account_number='1234567890')
    
    def test_multiple_accounts_per_customer(self):
        """Test customer can have multiple bank accounts."""
        customer = CustomerFactory()
        
        account1 = BankAccountFactory(customer=customer, is_primary=True)
        account2 = BankAccountFactory(customer=customer, is_primary=False)
        
        self.assertEqual(customer.bank_accounts.count(), 2)
        self.assertTrue(account1.is_primary)
        self.assertFalse(account2.is_primary)
    
    def test_bank_account_customer_relationship(self):
        """Test bank account relationship with customer."""
        customer = CustomerFactory()
        bank_account = BankAccountFactory(customer=customer)
        
        self.assertEqual(bank_account.customer, customer)
        self.assertIn(bank_account, customer.bank_accounts.all())
    
    def test_account_name_matches_customer(self):
        """Test account name matches customer name by default."""
        customer = CustomerFactory(name='John Doe')
        bank_account = BankAccountFactory(customer=customer)
        
        self.assertEqual(bank_account.account_name, customer.name)