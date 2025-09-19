"""
Azure Integration Views
"""

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.utils import timezone
from datetime import timedelta
import json

from .models import AzureConfiguration, AzureResource, AzureMetric, AzureAlert
from .services import AzureDataService
from .client import AzureClient, AzureAuthenticationError, AzureAPIError
from apps.products.models import Product


# @login_required  # Temporarily disabled for testing
def azure_dashboard(request):
    """Main Azure integration dashboard"""
    # Get summary statistics
    total_configs = AzureConfiguration.objects.filter(is_active=True).count()
    total_resources = AzureResource.objects.filter(is_monitored=True).count()
    active_alerts = AzureAlert.objects.filter(status=AzureAlert.AlertStatus.ACTIVE).count()
    
    # Get recent sync status
    recent_syncs = []
    for config in AzureConfiguration.objects.filter(is_active=True)[:5]:
        recent_syncs.append({
            'name': config.name,
            'last_sync': config.last_sync,
            'needs_sync': config.needs_sync,
            'environment': config.environment_filter
        })
    
    # Get resource breakdown by type
    resource_breakdown = {}
    for choice in AzureResource.ResourceType.choices:
        count = AzureResource.objects.filter(
            resource_type=choice[0], 
            is_monitored=True
        ).count()
        if count > 0:
            resource_breakdown[choice[1]] = count
    
    context = {
        'total_configs': total_configs,
        'total_resources': total_resources,
        'active_alerts': active_alerts,
        'recent_syncs': recent_syncs,
        'resource_breakdown': resource_breakdown,
        'title': 'Azure Integration Dashboard'
    }
    
    return render(request, 'azure/dashboard.html', context)


# @login_required  # Temporarily disabled for testing
def infrastructure_dashboard(request):
    """Azure infrastructure monitoring dashboard"""
    product_filter = request.GET.get('product')
    environment_filter = request.GET.get('environment')
    
    # Get dashboard data
    service = AzureDataService()
    dashboard_data = service.get_infrastructure_dashboard_data(
        product_id=product_filter,
        environment=environment_filter
    )
    
    # Get filter options
    products = Product.objects.all().order_by('name')
    environments = AzureConfiguration.objects.filter(is_active=True).values_list(
        'environment_filter', flat=True
    ).distinct().order_by('environment_filter')
    
    context = {
        'dashboard_data': dashboard_data,
        'products': products,
        'environments': environments,
        'selected_product': product_filter,
        'selected_environment': environment_filter,
        'title': 'Azure Infrastructure Dashboard'
    }
    
    return render(request, 'azure/infrastructure_dashboard.html', context)


# @login_required  # Temporarily disabled for testing
def performance_dashboard(request):
    """Azure performance monitoring dashboard"""
    # Get time range from request
    hours = int(request.GET.get('hours', 24))
    end_time = timezone.now()
    start_time = end_time - timedelta(hours=hours)
    
    # Get performance metrics
    performance_metrics = AzureMetric.objects.filter(
        metric_type=AzureMetric.MetricType.PERFORMANCE,
        timestamp__gte=start_time
    ).select_related('resource')
    
    # Group by resource and metric
    metrics_by_resource = {}
    for metric in performance_metrics:
        resource_name = metric.resource.name
        if resource_name not in metrics_by_resource:
            metrics_by_resource[resource_name] = {}
        
        if metric.metric_name not in metrics_by_resource[resource_name]:
            metrics_by_resource[resource_name][metric.metric_name] = []
        
        metrics_by_resource[resource_name][metric.metric_name].append({
            'timestamp': metric.timestamp.isoformat(),
            'value': metric.value,
            'unit': metric.unit
        })
    
    context = {
        'metrics_by_resource': metrics_by_resource,
        'time_range_hours': hours,
        'start_time': start_time.isoformat(),
        'end_time': end_time.isoformat(),
        'title': 'Azure Performance Dashboard'
    }
    
    return render(request, 'azure/performance_dashboard.html', context)


# @login_required  # Temporarily disabled for testing
def cost_dashboard(request):
    """Azure cost analysis dashboard"""
    # Placeholder for cost dashboard - would integrate with Azure Cost Management API
    context = {
        'title': 'Azure Cost Dashboard',
        'message': 'Cost dashboard coming soon - requires Azure Cost Management API integration'
    }
    
    return render(request, 'azure/cost_dashboard.html', context)


# @login_required  # Temporarily disabled for testing
def resource_list(request):
    """List all Azure resources"""
    resources = AzureResource.objects.filter(is_monitored=True).select_related(
        'configuration', 'product'
    ).order_by('name')
    
    # Apply filters
    resource_type = request.GET.get('type')
    if resource_type:
        resources = resources.filter(resource_type=resource_type)
    
    product_id = request.GET.get('product')
    if product_id:
        resources = resources.filter(product_id=product_id)
    
    context = {
        'resources': resources,
        'resource_types': AzureResource.ResourceType.choices,
        'products': Product.objects.all(),
        'title': 'Azure Resources'
    }
    
    return render(request, 'azure/resource_list.html', context)


# @login_required  # Temporarily disabled for testing
def resource_detail(request, resource_id):
    """Detailed view of a specific Azure resource"""
    resource = get_object_or_404(AzureResource, id=resource_id)
    
    # Get recent metrics (last 24 hours)
    end_time = timezone.now()
    start_time = end_time - timedelta(hours=24)
    
    recent_metrics = AzureMetric.objects.filter(
        resource=resource,
        timestamp__gte=start_time
    ).order_by('-timestamp')
    
    # Get recent alerts
    recent_alerts = AzureAlert.objects.filter(
        resource=resource
    ).order_by('-fired_at')[:10]
    
    context = {
        'resource': resource,
        'recent_metrics': recent_metrics,
        'recent_alerts': recent_alerts,
        'title': f'Azure Resource: {resource.name}'
    }
    
    return render(request, 'azure/resource_detail.html', context)


# @login_required  # Temporarily disabled for testing
def configuration_list(request):
    """List Azure configurations"""
    configurations = AzureConfiguration.objects.filter(is_active=True)
    
    context = {
        'configurations': configurations,
        'title': 'Azure Configurations'
    }
    
    return render(request, 'azure/configuration_list.html', context)


# @login_required  # Temporarily disabled for testing
def configuration_detail(request, config_id):
    """Detailed view of Azure configuration"""
    config = get_object_or_404(AzureConfiguration, id=config_id)
    
    # Get associated resources
    resources = config.resources.all()
    
    # Get recent sync logs
    recent_syncs = config.sync_logs.order_by('-started_at')[:10]
    
    context = {
        'config': config,
        'resources': resources,
        'recent_syncs': recent_syncs,
        'title': f'Azure Config: {config.name}'
    }
    
    return render(request, 'azure/configuration_detail.html', context)


# API Views

@require_POST
def test_connection_api(request):
    """API endpoint to test Azure connection"""
    try:
        data = json.loads(request.body)
        config_id = data.get('config_id')
        
        if not config_id:
            return JsonResponse({'success': False, 'error': 'config_id required'})
        
        config = get_object_or_404(AzureConfiguration, id=config_id)
        client = AzureClient(config)
        
        result = client.test_connection()
        client.close()
        
        return JsonResponse(result)
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@require_POST
def sync_data_api(request):
    """API endpoint to trigger Azure data sync"""
    try:
        data = json.loads(request.body)
        config_id = data.get('config_id')
        force = data.get('force', False)
        
        service = AzureDataService()
        
        if config_id:
            # Sync specific configuration
            config = get_object_or_404(AzureConfiguration, id=config_id)
            result = service.sync_configuration(config)
        else:
            # Sync all configurations
            result = service.sync_all_configurations(force=force)
        
        return JsonResponse({
            'success': True,
            'result': result
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


def metrics_api(request):
    """API endpoint to get metrics data"""
    try:
        resource_id = request.GET.get('resource_id')
        metric_name = request.GET.get('metric_name')
        hours = int(request.GET.get('hours', 24))
        
        end_time = timezone.now()
        start_time = end_time - timedelta(hours=hours)
        
        metrics = AzureMetric.objects.filter(
            timestamp__gte=start_time
        )
        
        if resource_id:
            metrics = metrics.filter(resource_id=resource_id)
        
        if metric_name:
            metrics = metrics.filter(metric_name=metric_name)
        
        metrics_data = []
        for metric in metrics.order_by('timestamp'):
            metrics_data.append({
                'timestamp': metric.timestamp.isoformat(),
                'value': metric.value,
                'unit': metric.unit,
                'metric_name': metric.metric_name,
                'resource': metric.resource.name
            })
        
        return JsonResponse({
            'success': True,
            'data': metrics_data,
            'count': len(metrics_data)
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})