from django.db.models import Q
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import cache_page
from django.core.paginator import Paginator
from django.db.models import Q

from .models import Dashboard, DashboardWidget
from .services import DashboardDataService
from .services_cached import CachedDashboardService
from apps.products.models import Product


# @login_required  # Temporarily disabled for testing
def dashboard_list(request):
    """List all available dashboards"""
    # dashboards = Dashboard.objects.filter(
    #     Q(is_public=True) | Q(created_by=request.user) | Q(allowed_users=request.user)
    # ).distinct()
    dashboards = Dashboard.objects.all()  # Simplified for testing
    
    context = {
        'dashboards': dashboards,
        'dashboard_types': Dashboard.DashboardType.choices
    }
    
    return render(request, 'dashboards/dashboard_list.html', context)


# @login_required  # Temporarily disabled for testing
def executive_dashboard(request):
    """Executive overview dashboard with instant cached loading"""
    product_filter = request.GET.get('product')
    environment_filter = request.GET.get('environment')
    
    # Use cached service for instant loading
    cached_service = CachedDashboardService()
    data, was_generated = cached_service.get_executive_overview(product_filter, environment_filter)
    
    # Get available filters
    products = Product.objects.all().order_by('name')
    
    # Get unique environments from Sentry
    from apps.sentry.models import SentryIssue
    environments = SentryIssue.objects.exclude(
        environment__isnull=True
    ).exclude(
        environment__exact=''
    ).values_list('environment', flat=True).distinct().order_by('environment')
    
    context = {
        'dashboard_data': data,
        'products': products,
        'environments': environments,
        'selected_product': product_filter,
        'selected_environment': environment_filter,
        'title': 'Executive Dashboard'
    }
    
    return render(request, 'dashboards/executive_dashboard.html', context)


# @login_required  # Temporarily disabled for testing
def product_dashboard(request, product_id=None):
    """Product health dashboard with instant cached loading"""
    environment_filter = request.GET.get('environment')
    
    if product_id:
        product = get_object_or_404(Product, id=product_id)
    else:
        product = None
    
    # Use cached service for instant loading
    cached_service = CachedDashboardService()
    data, was_generated = cached_service.get_product_health_dashboard(product_id, environment_filter)
    
    # Get available filters
    products = Product.objects.all().order_by('name')
    environments = []
    
    if product:
        # Get environments for this product
        from apps.sentry.models import SentryIssue
        environments = SentryIssue.objects.filter(
            project__product=product
        ).exclude(
            environment__isnull=True
        ).exclude(
            environment__exact=''
        ).values_list('environment', flat=True).distinct().order_by('environment')
    
    context = {
        'dashboard_data': data,
        'product': product,
        'products': products,
        'environments': environments,
        'selected_environment': environment_filter,
        'title': f'Product Dashboard - {product.name}' if product else 'Product Dashboard'
    }
    
    return render(request, 'dashboards/product_dashboard.html', context)


# @login_required  # Temporarily disabled for testing
def environment_dashboard(request):
    """Environment status dashboard with instant cached loading"""
    environment = request.GET.get('environment', 'production')
    product_filter = request.GET.get('product')
    
    # Use cached service for instant loading
    cached_service = CachedDashboardService()
    data, was_generated = cached_service.get_environment_dashboard(environment, product_filter)
    
    # Get available filters
    products = Product.objects.all().order_by('name')
    
    from apps.sentry.models import SentryIssue
    environments = SentryIssue.objects.exclude(
        environment__isnull=True
    ).exclude(
        environment__exact=''
    ).values_list('environment', flat=True).distinct().order_by('environment')
    
    context = {
        'dashboard_data': data,
        'products': products,
        'environments': environments,
        'selected_product': product_filter,
        'selected_environment': environment,
        'title': f'Environment Dashboard - {environment.title()}'
    }
    
    return render(request, 'dashboards/environment_dashboard.html', context)


# @login_required  # Temporarily disabled for testing
@cache_page(60)  # Cache for 1 minute
def dashboard_api(request, dashboard_type):
    """API endpoint for dashboard data"""
    product_filter = request.GET.get('product')
    environment_filter = request.GET.get('environment')
    
    service = DashboardDataService()
    
    if dashboard_type == 'executive':
        data = service.get_executive_overview(product_filter, environment_filter)
    elif dashboard_type == 'product':
        product_id = request.GET.get('product_id')
        data = service.get_product_health_dashboard(product_id, environment_filter)
    elif dashboard_type == 'environment':
        data = service.get_environment_dashboard(environment_filter, product_filter)
    else:
        return JsonResponse({'error': 'Invalid dashboard type'}, status=400)
    
    return JsonResponse(data)


# @login_required  # Temporarily disabled for testing
def custom_dashboard(request, dashboard_id):
    """Display a custom dashboard"""
    dashboard = get_object_or_404(Dashboard, id=dashboard_id)
    
    # Check permissions (temporarily disabled for testing)
    # if not dashboard.is_public:
    #     if dashboard.created_by != request.user and not dashboard.allowed_users.filter(id=request.user.id).exists():
    #         return render(request, 'dashboards/access_denied.html', {'dashboard': dashboard})
    
    widgets = dashboard.widgets.all().order_by('row', 'column')
    
    context = {
        'dashboard': dashboard,
        'widgets': widgets,
        'title': dashboard.name
    }
    
    return render(request, 'dashboards/custom_dashboard.html', context)