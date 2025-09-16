"""
Factory classes for users app models.
"""
import factory
from django.contrib.auth import get_user_model
from apps.users.models import Customer, BankAccount

User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    """Factory for creating User instances."""
    
    class Meta:
        model = User
    
    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@example.com")
    first_name = factory.Faker('first_name')
    last_name = factory.Faker('last_name')
    role = User.UserRole.MEMBER
    account_type = User.AccountType.INDIVIDUAL
    is_active = True


class AdminUserFactory(UserFactory):
    """Factory for creating admin User instances."""
    
    role = User.UserRole.ADMIN
    is_staff = True


class SuperAdminUserFactory(UserFactory):
    """Factory for creating super admin User instances."""
    
    role = User.UserRole.SUPER_ADMIN
    is_staff = True
    is_superuser = True


class CustomerFactory(factory.django.DjangoModelFactory):
    """Factory for creating Customer instances."""
    
    class Meta:
        model = Customer
    
    name = factory.Faker('name')
    user = factory.SubFactory(UserFactory)
    address = factory.Faker('address')
    city = factory.Faker('city')
    state = factory.Faker('state')
    country = 'Nigeria'
    phone_number = factory.Faker('phone_number')
    date_of_birth = factory.Faker('date_of_birth')
    occupation = factory.Faker('job')
    total_contributions = factory.Faker('pydecimal', left_digits=8, right_digits=2, positive=True)
    total_groups = factory.Faker('pyint', min_value=0, max_value=10)


class BankAccountFactory(factory.django.DjangoModelFactory):
    """Factory for creating BankAccount instances."""
    
    class Meta:
        model = BankAccount
    
    customer = factory.SubFactory(CustomerFactory)
    bank_name = factory.Faker('company')
    account_number = factory.Faker('numerify', text='##########')
    account_name = factory.LazyAttribute(lambda obj: obj.customer.name)
    is_primary = True