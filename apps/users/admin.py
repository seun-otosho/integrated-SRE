from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from .models import User

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin configuration for User model"""
    
    list_display = (
        'email', 'username', 'first_name', 'last_name', 'role', 'is_active', 'date_joined'
    )
    list_filter = (
        'role', 'is_active', 'is_staff', 'date_joined', 'created_at'
    )
    search_fields = ('email', 'username', 'first_name', 'last_name', )
    ordering = ('-date_joined',)
    
    fieldsets = (
        (None, {
            'fields': ('username', 'email', 'password')
        }),
        ('Personal Info', {
            'fields': ('first_name', 'last_name', )
        }),
        ('Account Settings', {
            'fields': ('role', 'is_active', 'is_staff', 'is_superuser')
        }),
        ('Important dates', {
            'fields': ('last_login', 'date_joined', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'username', 'email', 'first_name', 'last_name', 'password1', 'password2', 'role', 'account_type',
            ),
        }),
    )
    
    readonly_fields = ('date_joined', 'last_login', 'created_at', 'updated_at')
    
    def get_queryset(self, request):
        """Optimize queryset"""
        return super().get_queryset(request).select_related()
    
    actions = ['activate_users', 'deactivate_users', 'make_admin', 'make_regular_user']
    
    def activate_users(self, request, queryset):
        """Activate selected users"""
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} users were successfully activated.')
    activate_users.short_description = "Activate selected users"
    
    def deactivate_users(self, request, queryset):
        """Deactivate selected users"""
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} users were successfully deactivated.')
    deactivate_users.short_description = "Deactivate selected users"
    
    def make_admin(self, request, queryset):
        """Make selected users admin"""
        updated = queryset.update(role='admin')
        self.message_user(request, f'{updated} users were made admin.')
    make_admin.short_description = "Make selected users admin"
    
    def make_regular_user(self, request, queryset):
        """Make selected users regular"""
        updated = queryset.update(role='member')
        self.message_user(request, f'{updated} users were made regular users.')
    make_regular_user.short_description = "Make selected users regular"

