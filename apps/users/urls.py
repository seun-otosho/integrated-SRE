from django.urls import path
from . import views

app_name = 'users'

urlpatterns = [
    # User profile endpoints
    path('profile/', views.UserProfileView.as_view(), name='user_profile'),

    
    # Admin endpoints
    path('update-role/', views.update_user_role, name='update_user_role'),
]