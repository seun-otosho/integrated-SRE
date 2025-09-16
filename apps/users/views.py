from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Sum, Count
from django.utils import timezone
from datetime import timedelta
from .models import User
from .serializers import (
    UserSerializer, UserProfileSerializer, UserStatsSerializer
)

import logging

logger = logging.getLogger(__name__)

class UserProfileView(APIView):
    """View for user profile management"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Get current user profile"""
        try:
            serializer = UserSerializer(request.user)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error fetching user profile: {str(e)}")
            return Response(
                {'error': 'Failed to fetch profile'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def put(self, request):
        """Update user profile"""
        try:
            serializer = UserProfileSerializer(
                request.user,
                data=request.data,
                partial=True
            )
            
            if serializer.is_valid():
                serializer.save()
                
                # Return updated user data
                user_serializer = UserSerializer(request.user)
                
                logger.info(f"Profile updated for user: {request.user.email}")
                
                return Response({
                    'message': 'Profile updated successfully',
                    'user': user_serializer.data
                }, status=status.HTTP_200_OK)
            
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
            
        except Exception as e:
            logger.error(f"Error updating user profile: {str(e)}")
            return Response(
                {'error': 'Failed to update profile'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def update_user_role(request):
    """Update user role (admin only)"""
    try:
        # Check if user is admin
        if not request.user.is_super_admin():
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        user_id = request.data.get('user_id')
        new_role = request.data.get('role')
        
        if not user_id or not new_role:
            return Response(
                {'error': 'User ID and role are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if new_role not in [choice[0] for choice in User.UserRole.choices]:
            return Response(
                {'error': 'Invalid role'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            user = User.objects.get(id=user_id)
            user.role = new_role
            user.save()
            
            logger.info(f"User role updated: {user.email} -> {new_role}")
            
            return Response({
                'message': 'User role updated successfully',
                'user': UserSerializer(user).data
            }, status=status.HTTP_200_OK)
            
        except User.DoesNotExist:
            return Response(
                {'error': 'User not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
    except Exception as e:
        logger.error(f"Error updating user role: {str(e)}")
        return Response(
            {'error': 'Failed to update user role'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )