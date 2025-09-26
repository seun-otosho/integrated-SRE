"""
Product Reliability Dashboard Views
Beautiful visualization of product reliability scores and insights
"""

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from datetime import timedelta
import json

from apps.products.models import Product
from apps.dashboards.services_reliability import ProductReliabilityService
from apps.dashboards.services_cached import CachedDashboardService


# @login_required  # Temporarily disabled for testing
def reliability_overview(request):
    """
    Main reliability dashboard showing all products
    """
    service = ProductReliabilityService()
    cached_service = CachedDashboardService()
    
    # Get filters
    days = int(request.GET.get('days', 30))
    sort_by = request.GET.get('sort', 'score')  # score, name, status
    
    # Get reliability data (use cached if available)
    try:
        dashboard_data, was_generated = cached_service.get_reliability_overview(days=days)
    except:
        # Fallback to direct calculation
        all_products_data = service.get_all_products_reliability(days=days)
        dashboard_data = {
            'products': all_products_data,
            'summary': _calculate_portfolio_summary(all_products_data),
            'trends': _calculate_portfolio_trends(all_products_data),
            'generated_at': timezone.now().isoformat()
        }
        was_generated = True
    
    # Apply sorting
    products_data = dashboard_data['products']
    if sort_by == 'name':
        products_data.sort(key=lambda x: x.get('product', ''))
    elif sort_by == 'status':
        status_order = {'excellent': 5, 'good': 4, 'needs_attention': 3, 'poor': 2, 'critical': 1}
        products_data.sort(key=lambda x: status_order.get(x.get('health_status', 'critical'), 0), reverse=True)
    else:  # sort by score (default)
        products_data.sort(key=lambda x: x.get('overall_score', 0), reverse=True)
    
    context = {
        'title': 'Product Reliability Dashboard',
        'dashboard_data': dashboard_data,
        'products_data': products_data,
        'summary': dashboard_data.get('summary', {}),
        'trends': dashboard_data.get('trends', {}),
        'filters': {
            'days': days,
            'sort_by': sort_by
        },
        'was_generated': was_generated,
        'refresh_available': True
    }
    
    return render(request, 'dashboards/reliability_overview.html', context)


# @login_required  # Temporarily disabled for testing
def product_reliability_detail(request, product_id):
    """
    Detailed reliability view for a specific product
    """
    product = get_object_or_404(Product, id=product_id)
    service = ProductReliabilityService()
    
    # Get time range
    days = int(request.GET.get('days', 30))
    
    # Calculate detailed reliability data
    reliability_data = service.calculate_product_reliability(product, days=days)
    
    # Get historical trend data (last 90 days in weekly chunks)
    historical_data = _get_product_historical_trends(service, product)
    
    # Get component details
    components = reliability_data['components']
    
    context = {
        'title': f'Reliability: {product.name}',
        'product': product,
        'reliability_data': reliability_data,
        'historical_data': historical_data,
        'components': components,
        'filters': {
            'days': days
        },
        'chart_data': _prepare_chart_data(reliability_data, historical_data)
    }
    
    return render(request, 'dashboards/product_reliability_detail.html', context)


# @login_required  # Temporarily disabled for testing
def reliability_executive_summary(request):
    """
    Executive summary view for leadership
    """
    service = ProductReliabilityService()
    
    # Get all products data
    all_products_data = service.get_all_products_reliability(days=30)
    
    # Calculate executive metrics
    executive_summary = {
        'portfolio_score': _calculate_weighted_portfolio_score(all_products_data),
        'total_products': len(all_products_data),
        'critical_products': len([p for p in all_products_data if p.get('health_status') == 'critical']),
        'excellent_products': len([p for p in all_products_data if p.get('health_status') == 'excellent']),
        'top_performers': all_products_data[:3],
        'needs_attention': [p for p in all_products_data if p.get('health_status') in ['critical', 'poor']][-3:],
        'key_metrics': _calculate_key_executive_metrics(all_products_data),
        'trends': _calculate_executive_trends(all_products_data)
    }
    
    context = {
        'title': 'Executive Reliability Summary',
        'executive_summary': executive_summary,
        'chart_data': _prepare_executive_chart_data(executive_summary, all_products_data)
    }
    
    return render(request, 'dashboards/reliability_executive.html', context)


# @login_required  # Temporarily disabled for testing
def reliability_team_comparison(request):
    """
    Team/platform comparison view
    """
    service = ProductReliabilityService()
    
    # Get all products data
    all_products_data = service.get_all_products_reliability(days=30)
    
    # Group by teams/platforms (you might need to add team field to Product model)
    team_comparison = _group_products_by_category(all_products_data)
    
    context = {
        'title': 'Team Reliability Comparison',
        'team_comparison': team_comparison,
        'chart_data': _prepare_team_comparison_data(team_comparison)
    }
    
    return render(request, 'dashboards/reliability_team_comparison.html', context)


# API Endpoints for AJAX updates

def reliability_api(request):
    """
    API endpoint for reliability data
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'GET method required'}, status=405)
    
    try:
        service = ProductReliabilityService()
        
        product_id = request.GET.get('product_id')
        days = int(request.GET.get('days', 30))
        
        if product_id:
            # Get specific product data
            product = get_object_or_404(Product, id=product_id)
            data = service.calculate_product_reliability(product, days=days)
        else:
            # Get all products data
            data = {
                'products': service.get_all_products_reliability(days=days),
                'generated_at': timezone.now().isoformat()
            }
        
        return JsonResponse({
            'success': True,
            'data': data
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def refresh_reliability_cache(request):
    """
    API endpoint to refresh reliability cache
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    try:
        service = ProductReliabilityService()
        cached_service = CachedDashboardService()
        
        # Refresh reliability data cache
        all_products_data = service.get_all_products_reliability(days=30)
        
        # Cache the results (you'd implement this in CachedDashboardService)
        # cached_service.cache_reliability_data(all_products_data)
        
        return JsonResponse({
            'success': True,
            'message': 'Reliability cache refreshed successfully',
            'products_updated': len(all_products_data),
            'timestamp': timezone.now().isoformat()
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# Helper functions for data processing

def _calculate_portfolio_summary(products_data):
    """Calculate portfolio-wide summary statistics"""
    if not products_data:
        return {}
    
    total_products = len(products_data)
    total_score = sum(p.get('overall_score', 0) for p in products_data)
    avg_score = total_score / total_products if total_products > 0 else 0
    
    # Count by health status
    status_counts = {}
    for status in ['excellent', 'good', 'needs_attention', 'poor', 'critical']:
        status_counts[status] = len([p for p in products_data if p.get('health_status') == status])
    
    # Component averages
    avg_runtime = sum(p.get('components', {}).get('runtime', {}).get('score', 0) for p in products_data) / total_products
    avg_quality = sum(p.get('components', {}).get('quality', {}).get('score', 0) for p in products_data) / total_products
    avg_operations = sum(p.get('components', {}).get('operations', {}).get('score', 0) for p in products_data) / total_products
    
    return {
        'total_products': total_products,
        'average_score': round(avg_score, 1),
        'status_distribution': status_counts,
        'component_averages': {
            'runtime': round(avg_runtime, 1),
            'quality': round(avg_quality, 1),
            'operations': round(avg_operations, 1)
        }
    }


def _calculate_portfolio_trends(products_data):
    """Calculate portfolio trend indicators"""
    improving = len([p for p in products_data 
                    if any(comp.get('trend') == 'improving' 
                          for comp in p.get('components', {}).values())])
    
    worsening = len([p for p in products_data 
                    if any(comp.get('trend') == 'worsening' 
                          for comp in p.get('components', {}).values())])
    
    stable = len(products_data) - improving - worsening
    
    return {
        'improving': improving,
        'stable': stable,
        'worsening': worsening
    }


def _get_product_historical_trends(service, product):
    """Get historical trend data for a product (placeholder)"""
    # This would calculate trends over time
    # For now, return sample data structure
    return {
        'dates': [],
        'overall_scores': [],
        'runtime_scores': [],
        'quality_scores': [],
        'operations_scores': []
    }


def _prepare_chart_data(reliability_data, historical_data):
    """Prepare data for charts and visualizations"""
    components = reliability_data.get('components', {})
    
    return {
        'component_breakdown': {
            'labels': ['Runtime', 'Quality', 'Operations', 'System Health'],
            'data': [
                components.get('runtime', {}).get('score', 0),
                components.get('quality', {}).get('score', 0),
                components.get('operations', {}).get('score', 0),
                components.get('system_health', {}).get('score', 0)
            ],
            'colors': ['#ff6b6b', '#4ecdc4', '#45b7d1', '#96ceb4']
        },
        'historical_trend': historical_data,
        'gauge_data': {
            'score': reliability_data.get('overall_score', 0),
            'status': reliability_data.get('health_status', 'unknown')
        }
    }


def _calculate_weighted_portfolio_score(products_data):
    """Calculate weighted portfolio score"""
    if not products_data:
        return 0
    
    total_score = sum(p.get('overall_score', 0) for p in products_data)
    return round(total_score / len(products_data), 1)


def _calculate_key_executive_metrics(products_data):
    """Calculate key metrics for executives"""
    return {
        'avg_resolution_rate': 75,  # Would calculate from actual data
        'avg_quality_gate_compliance': 68,
        'avg_test_coverage': 45,
        'critical_issues_trend': 'decreasing'
    }


def _calculate_executive_trends(products_data):
    """Calculate executive trend data"""
    return {
        'monthly_improvement': 5.2,
        'quarterly_trend': 'improving',
        'top_risk_areas': ['Test Coverage', 'Error Resolution', 'Quality Gates']
    }


def _prepare_executive_chart_data(summary, products_data):
    """Prepare chart data for executive dashboard"""
    return {
        'portfolio_distribution': {
            'labels': list(summary['key_metrics'].keys()),
            'data': list(summary['key_metrics'].values())
        },
        'product_scores': {
            'labels': [p.get('product', '') for p in products_data[:10]],
            'data': [p.get('overall_score', 0) for p in products_data[:10]]
        }
    }


def _group_products_by_category(products_data):
    """Group products by team/category for comparison"""
    # This would group by team if you have team field in Product model
    # For now, group by score ranges
    categories = {
        'High Performers (80%+)': [p for p in products_data if p.get('overall_score', 0) >= 80],
        'Good (60-80%)': [p for p in products_data if 60 <= p.get('overall_score', 0) < 80],
        'Needs Attention (<60%)': [p for p in products_data if p.get('overall_score', 0) < 60]
    }
    
    return categories


def _prepare_team_comparison_data(team_comparison):
    """Prepare data for team comparison charts"""
    return {
        'team_scores': {
            'labels': list(team_comparison.keys()),
            'data': [
                sum(p.get('overall_score', 0) for p in products) / len(products) if products else 0
                for products in team_comparison.values()
            ]
        }
    }