from django.urls import path
from . import views

app_name = 'sonarcloud'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('organizations/', views.organizations_list, name='organizations'),
    path('organizations/<int:org_id>/', views.organization_detail, name='organization_detail'),
    path('projects/<int:project_id>/', views.project_detail, name='project_detail'),
    path('sync/<int:org_id>/', views.sync_organization, name='sync_organization'),
    path('test-connection/<int:org_id>/', views.test_connection, name='test_connection'),
]