from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models


class User(AbstractUser):
    """Custom User model with additional fields for Ajo platform"""

    class UserRole(models.TextChoices):
        MEMBER = 'member', 'Member'
        ADMIN = 'admin', 'Admin'
        SUPER_ADMIN = 'super_admin', 'Super Admin'


    # Basic Information
    email = models.EmailField(unique=True)
    # Profile Information
    role = models.CharField(max_length=20, choices=UserRole.choices, default=UserRole.MEMBER)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Email as username
    # USERNAME_FIELD = 'email'
    # REQUIRED_FIELDS = ['username', 'first_name', 'last_name']

    class Meta:
        db_table = 'users'
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def __str__(self):
        return f"{self.get_full_name()} ({self.email})"

    def get_full_name(self):
        """Return the first_name plus the last_name, with a space in between."""
        full_name = f"{self.first_name} {self.last_name}"
        return full_name.strip()

    def is_admin(self):
        """Check if user is admin or super admin"""
        return self.role in [self.UserRole.ADMIN, self.UserRole.SUPER_ADMIN]

    def is_super_admin(self):
        """Check if user is super admin"""
        return self.role == self.UserRole.SUPER_ADMIN

