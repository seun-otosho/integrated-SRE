from django.urls import path
from . import views

app_name = 'azure'

urlpatterns = [
    # Dashboard views
    path('', views.azure_dashboard, name='dashboard'),
    path('infrastructure/', views.infrastructure_dashboard, name='infrastructure'),
    path('performance/', views.performance_dashboard, name='performance'),
    path('cost/', views.cost_dashboard, name='cost'),
    
    # API endpoints
    path('api/test-connection/', views.test_connection_api, name='test_connection_api'),
    path('api/sync/', views.sync_data_api, name='sync_data_api'),
    path('api/metrics/', views.metrics_api, name='metrics_api'),
    
    # Resource views
    path('resources/', views.resource_list, name='resource_list'),
    path('resources/<int:resource_id>/', views.resource_detail, name='resource_detail'),
    
    # Configuration views
    path('config/', views.configuration_list, name='configuration_list'),
    path('config/<int:config_id>/', views.configuration_detail, name='configuration_detail'),
]