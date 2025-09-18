"""
Async dashboard views for improved performance and loading experience
"""

from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.cache import cache_page
from django.core.cache import cache
from .services import DashboardDataService
from apps.products.models import Product
import asyncio
import threading
import time


def async_executive_dashboard(request):
    """Async version of executive dashboard with loading optimization"""
    product_filter = request.GET.get('product')
    environment_filter = request.GET.get('environment')
    
    # Check if we have cached data first
    cache_key = f"executive_overview_{product_filter}_{environment_filter}"
    cached_data = cache.get(cache_key)
    
    if cached_data:
        # Return immediately with cached data
        context = {
            'dashboard_data': cached_data,
            'products': Product.objects.all().order_by('name'),
            'environments': _get_environments(),
            'selected_product': product_filter,
            'selected_environment': environment_filter,
            'title': 'Executive Dashboard',
            'loading_time': 'Cached (instant)',
            'cache_hit': True
        }
        return render(request, 'dashboards/executive_dashboard_async.html', context)
    
    # If no cache, return loading template and trigger background processing
    if request.GET.get('ajax') == 'true':
        # This is an AJAX request for data
        service = DashboardDataService()
        start_time = time.time()
        data = service.get_executive_overview(product_filter, environment_filter)
        end_time = time.time()
        
        data['loading_time'] = f"{end_time - start_time:.2f}s"
        data['cache_hit'] = False
        
        return JsonResponse(data)
    
    # Initial page load - return loading template
    context = {
        'products': Product.objects.all().order_by('name'),
        'environments': _get_environments(),
        'selected_product': product_filter,
        'selected_environment': environment_filter,
        'title': 'Executive Dashboard',
        'ajax_url': f"/dashboards/api/executive/?ajax=true&product={product_filter or ''}&environment={environment_filter or ''}"
    }
    
    return render(request, 'dashboards/executive_dashboard_loading.html', context)


def _get_environments():
    """Get unique environments from Sentry"""
    from apps.sentry.models import SentryIssue
    return SentryIssue.objects.exclude(
        environment__isnull=True
    ).exclude(
        environment__exact=''
    ).values_list('environment', flat=True).distinct().order_by('environment')


def dashboard_performance_info(request):
    """Return performance information about dashboard loading"""
    service = DashboardDataService()
    
    # Time different operations
    operations = {}
    
    # Test summary cards
    start = time.time()
    service._get_summary_cards()
    operations['summary_cards'] = time.time() - start
    
    # Test health trends
    start = time.time()
    service._get_health_trends()
    operations['health_trends'] = time.time() - start
    
    # Test critical issues
    start = time.time()
    service._get_critical_issues()
    operations['critical_issues'] = time.time() - start
    
    # Test integration stats
    start = time.time()
    service._get_integration_stats()
    operations['integration_stats'] = time.time() - start
    
    total_time = sum(operations.values())
    
    return JsonResponse({
        'operations': operations,
        'total_time': total_time,
        'cache_timeout': 300,  # 5 minutes
        'recommendations': _get_performance_recommendations(operations)
    })


def _get_performance_recommendations(operations):
    """Get performance optimization recommendations"""
    recommendations = []
    
    if operations.get('health_trends', 0) > 2:
        recommendations.append("Consider reducing the date range for health trends to improve performance")
    
    if operations.get('critical_issues', 0) > 1:
        recommendations.append("Critical issues query is slow - consider indexing or limiting results")
    
    if sum(operations.values()) > 5:
        recommendations.append("Total loading time > 5s - consider implementing background processing")
    
    if not recommendations:
        recommendations.append("Dashboard performance is optimal!")
    
    return recommendations