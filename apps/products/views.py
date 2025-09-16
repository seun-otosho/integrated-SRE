from django.shortcuts import render, get_object_or_404
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Q
from django.http import JsonResponse

from .models import Product
from apps.sentry.models import SentryProject, SentryIssue


@staff_member_required
def products_overview(request):
    """Overview of all products with their Sentry statistics"""
    
    # Get root products (no parent) with aggregated stats
    root_products = Product.objects.filter(parent=None).annotate(
        direct_projects_count=Count('sentryproject', distinct=True),
        total_issues_count=Count('sentryproject__issues', distinct=True),
        unresolved_issues_count=Count(
            'sentryproject__issues', 
            filter=Q(sentryproject__issues__status='unresolved'), 
            distinct=True
        )
    ).order_by('name')
    
    # Calculate hierarchical stats for each root product
    products_with_stats = []
    for product in root_products:
        stats = product.get_issue_stats()
        products_with_stats.append({
            'product': product,
            'direct_projects': product.sentry_projects_count,
            'total_projects': product.total_sentry_projects_count,
            'stats': stats,
            'children': product.sub_products.all()
        })
    
    # Recent issues across all products
    recent_issues = SentryIssue.objects.filter(
        project__product__isnull=False
    ).select_related('project', 'project__product').order_by('-last_seen')[:10]
    
    # Unassigned projects (not linked to any product)
    unassigned_projects = SentryProject.objects.filter(product=None).count()
    
    context = {
        'products_with_stats': products_with_stats,
        'recent_issues': recent_issues,
        'unassigned_projects': unassigned_projects,
        'total_products': Product.objects.count(),
    }
    
    return render(request, 'products/overview.html', context)


@staff_member_required
def product_detail(request, product_id):
    """Detailed view of a specific product"""
    product = get_object_or_404(Product, id=product_id)
    
    # Get all descendant products
    all_descendants = product.all_descendants
    all_product_ids = [product.id] + [p.id for p in all_descendants]
    
    # Projects directly linked to this product and its descendants
    projects = SentryProject.objects.filter(
        product_id__in=all_product_ids
    ).select_related('organization').annotate(
        issues_count=Count('issues'),
        unresolved_count=Count('issues', filter=Q(issues__status='unresolved'))
    )
    
    # Issue statistics
    stats = product.get_issue_stats()
    
    # Recent issues for this product tree
    recent_issues = SentryIssue.objects.filter(
        project__product_id__in=all_product_ids
    ).select_related('project').order_by('-last_seen')[:20]
    
    # Sub-products with their stats
    sub_products_with_stats = []
    for sub_product in product.sub_products.all():
        sub_stats = sub_product.get_issue_stats()
        sub_products_with_stats.append({
            'product': sub_product,
            'stats': sub_stats,
            'projects_count': sub_product.total_sentry_projects_count
        })
    
    context = {
        'product': product,
        'projects': projects,
        'stats': stats,
        'recent_issues': recent_issues,
        'sub_products_with_stats': sub_products_with_stats,
        'all_descendants': all_descendants,
    }
    
    return render(request, 'products/detail.html', context)


@staff_member_required
def product_issues(request, product_id):
    """All issues for a product and its descendants"""
    product = get_object_or_404(Product, id=product_id)
    
    # Get all descendant products
    all_descendants = product.all_descendants
    all_product_ids = [product.id] + [p.id for p in all_descendants]
    
    # Filter issues
    status_filter = request.GET.get('status', '')
    level_filter = request.GET.get('level', '')
    
    issues = SentryIssue.objects.filter(
        project__product_id__in=all_product_ids
    ).select_related('project', 'project__organization')
    
    if status_filter:
        issues = issues.filter(status=status_filter)
    
    if level_filter:
        issues = issues.filter(level=level_filter)
    
    issues = issues.order_by('-last_seen')[:100]  # Limit for performance
    
    # Issue counts by status and level
    status_counts = SentryIssue.objects.filter(
        project__product_id__in=all_product_ids
    ).values('status').annotate(count=Count('id'))
    
    level_counts = SentryIssue.objects.filter(
        project__product_id__in=all_product_ids
    ).values('level').annotate(count=Count('id'))
    
    context = {
        'product': product,
        'issues': issues,
        'status_filter': status_filter,
        'level_filter': level_filter,
        'status_counts': status_counts,
        'level_counts': level_counts,
    }
    
    return render(request, 'products/issues.html', context)


@staff_member_required
def products_hierarchy(request):
    """Hierarchical view of all products"""
    
    def build_tree(parent=None, level=0):
        """Recursively build product tree"""
        products = Product.objects.filter(parent=parent).annotate(
            projects_count=Count('sentryproject', distinct=True),
            issues_count=Count('sentryproject__issues', distinct=True),
            unresolved_count=Count(
                'sentryproject__issues',
                filter=Q(sentryproject__issues__status='unresolved'),
                distinct=True
            )
        )
        
        tree = []
        for product in products:
            children = build_tree(product, level + 1)
            tree.append({
                'product': product,
                'level': level,
                'children': children,
                'stats': product.get_issue_stats()
            })
        
        return tree
    
    # Build the complete hierarchy tree
    hierarchy = build_tree()
    
    context = {
        'hierarchy': hierarchy,
    }
    
    return render(request, 'products/hierarchy.html', context)
