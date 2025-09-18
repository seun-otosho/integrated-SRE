from django.urls import path
from . import views

app_name = 'dashboards'

urlpatterns = [
    # Dashboard views
    path('', views.dashboard_list, name='dashboard_list'),
    path('executive/', views.executive_dashboard, name='executive'),
    path('product/', views.product_dashboard, name='product'),
    path('product/<int:product_id>/', views.product_dashboard, name='product_detail'),
    path('environment/', views.environment_dashboard, name='environment'),
    path('custom/<int:dashboard_id>/', views.custom_dashboard, name='custom'),
    
    # API endpoints
    path('api/<str:dashboard_type>/', views.dashboard_api, name='api'),
]