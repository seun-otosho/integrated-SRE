from django.urls import path
from . import views
from . import views_async

app_name = 'dashboards'

urlpatterns = [
    # Dashboard views with instant loading from cache
    path('', views.dashboard_list, name='dashboard_list'),
    path('executive/', views.executive_dashboard, name='executive'),
    path('product/', views.product_dashboard, name='product'),
    path('product/<int:product_id>/', views.product_dashboard, name='product_detail'),
    path('environment/', views.environment_dashboard, name='environment'),
    path('custom/<int:dashboard_id>/', views.custom_dashboard, name='custom'),
    
    # API endpoints for background refresh
    path('api/<str:dashboard_type>/', views.dashboard_api, name='api'),
    path('api/refresh/<str:dashboard_type>/', views.refresh_dashboard_api, name='refresh_api'),
    
    # Async/Loading versions (fallback)
    path('executive/async/', views_async.async_executive_dashboard, name='executive_async'),
    path('performance/', views_async.dashboard_performance_info, name='performance'),
]