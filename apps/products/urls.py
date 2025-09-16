from django.urls import path
from . import views

app_name = 'products'

urlpatterns = [
    path('', views.products_overview, name='overview'),
    path('<int:product_id>/', views.product_detail, name='detail'),
    path('<int:product_id>/issues/', views.product_issues, name='issues'),
    path('hierarchy/', views.products_hierarchy, name='hierarchy'),
]