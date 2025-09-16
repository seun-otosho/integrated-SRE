from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Count, Q
from .models import Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'parent', 'sentry_projects_count', 'total_issues_count', 'unresolved_issues_count', 'hierarchy_path']
    list_filter = ['parent', 'created_at']
    search_fields = ['name', 'parent__name']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Product Information', {
            'fields': ('name', 'parent')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('parent').annotate(
            projects_count=Count('sentryproject', distinct=True),
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
