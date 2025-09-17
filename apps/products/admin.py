from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Count, Q
from .models import Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'parent', 'owner_team', 'priority', 'is_active', 'sentry_projects_count', 'jira_projects_count', 'total_issues_count', 'unresolved_issues_count', 'hierarchy_path']
    list_filter = ['parent', 'priority', 'is_active', 'owner_team', 'created_at']
    search_fields = ['name', 'parent__name', 'description', 'owner_team']
    readonly_fields = ['created_at', 'updated_at']
    actions = ['bulk_assign_projects', 'activate_products', 'deactivate_products']
    
    fieldsets = (
        ('Product Information', {
            'fields': ('name', 'parent', 'description')
        }),
        ('Product Details', {
            'fields': ('owner_team', 'priority', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('parent').annotate(
            projects_count=Count('sentryproject', distinct=True),
            jira_projects_count=Count('jira_projects', distinct=True),
            total_issues=Count('sentryproject__issues', distinct=True),
            unresolved_issues=Count('sentryproject__issues', 
                                  filter=Q(sentryproject__issues__status='unresolved'), 
                                  distinct=True)
        )
    
    def sentry_projects_count(self, obj):
        count = obj.projects_count if hasattr(obj, 'projects_count') else obj.sentryproject_set.count()
        if count > 0:
            url = reverse('admin:sentry_sentryproject_changelist') + f'?product__id__exact={obj.id}'
            return format_html('<a href="{}">{} projects</a>', url, count)
        return '0 projects'
    sentry_projects_count.short_description = 'Sentry Projects'
    
    def jira_projects_count(self, obj):
        count = obj.jira_projects_count if hasattr(obj, 'jira_projects_count') else obj.jira_projects.count()
        if count > 0:
            # Check if JIRA app is installed
            try:
                url = reverse('admin:jira_jiraproject_changelist') + f'?product__id__exact={obj.id}'
                return format_html('<a href=\"{}\">{} projects</a>', url, count)
            except:
                return f'{count} projects'
        return '0 projects'
    jira_projects_count.short_description = 'JIRA Projects'
    
    def total_issues_count(self, obj):
        count = obj.total_issues if hasattr(obj, 'total_issues') else 0
        if count > 0:
            return format_html('<span style="color: #666;">{}</span>', count)
        return '0'
    total_issues_count.short_description = 'Total Issues'
    
    def unresolved_issues_count(self, obj):
        count = obj.unresolved_issues if hasattr(obj, 'unresolved_issues') else 0
        if count > 0:
            return format_html('<span style="color: #dc3545; font-weight: bold;">{}</span>', count)
        return '0'
    unresolved_issues_count.short_description = 'Unresolved Issues'
    
    def hierarchy_path(self, obj):
        """Show the full hierarchy path"""
        path = []
        current = obj
        while current:
            path.insert(0, current.name)
            current = current.parent
        return ' → '.join(path)
    hierarchy_path.short_description = 'Hierarchy Path'
    
    def bulk_assign_projects(self, request, queryset):
        """Custom action to bulk assign projects to selected products"""
        if queryset.count() != 1:
            self.message_user(request, 'Please select exactly one product for bulk project assignment.', level='ERROR')
            return
        
        product = queryset.first()
        
        # Redirect to bulk assignment view
        from django.http import HttpResponseRedirect
        from django.urls import reverse
        
        url = reverse('admin:products_bulk_assign_projects', args=[product.id])
        return HttpResponseRedirect(url)
    
    bulk_assign_projects.short_description = 'Bulk assign Sentry projects'
    
    def activate_products(self, request, queryset):
        """Activate selected products"""
        count = queryset.update(is_active=True)
        self.message_user(request, f'Successfully activated {count} products.')
    activate_products.short_description = 'Activate selected products'
    
    def deactivate_products(self, request, queryset):
        """Deactivate selected products"""
        count = queryset.update(is_active=False)
        self.message_user(request, f'Successfully deactivated {count} products.')
    deactivate_products.short_description = 'Deactivate selected products'
    
    def get_urls(self):
        """Add custom URLs for bulk assignment"""
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:product_id>/bulk-assign-projects/',
                self.admin_site.admin_view(self.bulk_assign_projects_view),
                name='products_bulk_assign_projects',
            ),
        ]
        return custom_urls + urls
    
    def bulk_assign_projects_view(self, request, product_id):
        """View for bulk assigning projects to a product"""
        from django.shortcuts import get_object_or_404, render, redirect
        from django.contrib import messages
        from apps.sentry.models import SentryProject
        
        product = get_object_or_404(Product, id=product_id)
        
        if request.method == 'POST':
            project_ids = request.POST.getlist('projects')
            
            if project_ids:
                # Update selected projects
                updated_count = SentryProject.objects.filter(
                    id__in=project_ids
                ).update(product=product)
                
                messages.success(
                    request, 
                    f'Successfully assigned {updated_count} projects to "{product.name}"'
                )
            else:
                messages.warning(request, 'No projects were selected.')
            
            return redirect('admin:products_product_changelist')
        
        # Get all projects grouped by organization
        organizations_with_projects = []
        from apps.sentry.models import SentryOrganization
        
        for org in SentryOrganization.objects.all():
            projects = org.projects.select_related('product').order_by('name')
            if projects.exists():
                organizations_with_projects.append({
                    'organization': org,
                    'projects': projects
                })
        
        context = {
            'product': product,
            'organizations_with_projects': organizations_with_projects,
            'title': f'Bulk Assign Projects to "{product.name}"',
            'opts': self.model._meta,
            'has_change_permission': True,
        }
        
        return render(request, 'admin/products/bulk_assign_projects.html', context)
