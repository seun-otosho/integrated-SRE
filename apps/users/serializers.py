from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from .models import User

class UserSerializer(serializers.ModelSerializer):
    """Serializer for User model"""
    
    full_name = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'full_name',
            'phone_number', 'role', 'account_type', 'address', 'city', 'state',
            'country', 'profile_picture', 'date_of_birth', 'occupation',
            'total_contributions', 'total_groups', 'is_active', 'date_joined',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'username', 'total_contributions', 'total_groups',
            'is_active', 'date_joined', 'created_at', 'updated_at'
        ]
    
    def get_full_name(self, obj):
        return obj.get_full_name()

class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer for user profile updates"""
    
    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'phone_number', 'address',
            'city', 'state', 'country', 'profile_picture',
            'date_of_birth', 'occupation'
        ]
    
    def validate_phone_number(self, value):
        if value and not value.replace('+', '').replace('-', '').replace(' ', '').isdigit():
            raise serializers.ValidationError("Invalid phone number format")
        return value

class UserRegistrationSerializer(serializers.ModelSerializer):
    """Serializer for user registration"""
    
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)
    
    class Meta:
        model = User
        fields = [
            'email', 'password', 'password_confirm', 'first_name', 'last_name',
            'phone_number', 'account_type'
        ]
    
    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError("Passwords don't match")
        return attrs
    
    def validate_email(self, value):
        if User.objects.filter(email=value.lower()).exists():
            raise serializers.ValidationError("User with this email already exists")
        return value.lower()
    
    def create(self, validated_data):
        validated_data.pop('password_confirm')
        password = validated_data.pop('password')
        
        # Create username from email
        email = validated_data['email']
        username = email.split('@')[0]
        counter = 1
        original_username = username
        while User.objects.filter(username=username).exists():
            username = f"{original_username}{counter}"
            counter += 1
        
        validated_data['username'] = username
        
        user = User.objects.create_user(password=password, **validated_data)
        return user

class UserStatsSerializer(serializers.ModelSerializer):
    """Serializer for user statistics"""
    
    active_groups = serializers.SerializerMethodField()
    pending_contributions = serializers.SerializerMethodField()
    completed_contributions = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'total_contributions', 'total_groups', 'active_groups',
            'pending_contributions', 'completed_contributions'
        ]
    
    def get_active_groups(self, obj):
        from apps.groups.models import GroupMember
        return GroupMember.objects.filter(
            user=obj,
            status='active'
        ).count()
    
    def get_pending_contributions(self, obj):
        from apps.contributions.models import Contribution
        return Contribution.objects.filter(
            member=obj,
            status='pending'
        ).count()
    
    def get_completed_contributions(self, obj):
        from apps.contributions.models import Contribution
        return Contribution.objects.filter(
            member=obj,
            status='completed'
        ).count()

class PublicUserSerializer(serializers.ModelSerializer):
    """Serializer for public user information (limited fields)"""
    
    full_name = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id', 'full_name', 'profile_picture', 'role'
        ]
    
    def get_full_name(self, obj):
        return obj.get_full_name()