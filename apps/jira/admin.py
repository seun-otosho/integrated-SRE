from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Q

from .models import (
    JiraOrganization, JiraProject, JiraIssue, 
    SentryJiraLink, JiraSyncLog
)
from .services import sync_jira_organization


@admin.register(JiraOrganization)
class JiraOrganizationAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'base_url', 'connection_status_display', 'sync_enabled', 
        'projects_count', 'last_sync_display', 'sync_actions'
    ]
    list_filter = ['connection_status', 'sync_enabled', 'created_at']
    search_fields = ['name', 'base_url', 'username']
    readonly_fields = ['connection_status', 'last_connection_test', 'connection_error', 'last_sync', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Organization Info', {
            'fields': ('name', 'base_url')
        }),
        ('Authentication', {
            'fields': ('username', 'api_token'),
            'description': 'Use your JIRA email and API token. Create API token at: Account Settings > Security > API tokens'
        }),
        ('Sync Settings', {
            'fields': ('sync_enabled', 'sync_interval_hours', 'last_sync')
        }),
        ('Connection Status', {
            'fields': ('connection_status', 'last_connection_test', 'connection_error'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['sync_selected_organizations', 'test_connections', 'enable_sync', 'disable_sync']
    
    def connection_status_display(self, obj):
        status_colors = {
            'connected': 'green',
            'failed': 'red',
            'unauthorized': 'orange',
            'unknown': 'gray'
        }
        color = status_colors.get(obj.connection_status, 'gray')
        
        if obj.connection_status == 'connected':
            icon = '✅'
        elif obj.connection_status == 'failed':
            icon = '❌'
        elif obj.connection_status == 'unauthorized':
            icon = '🔒'
        else:
            icon = '❓'
        
        return format_html(
            '<span style="color: {};">{} {}</span>',
            color, icon, obj.get_connection_status_display()
        )
    connection_status_display.short_description = 'Connection'
    
    def last_sync_display(self, obj):
        if obj.last_sync:
            time_diff = timezone.now() - obj.last_sync
            if time_diff < timedelta(hours=1):
                return format_html('<span style="color: green;">{}min ago</span>', int(time_diff.total_seconds() / 60))
            elif time_diff < timedelta(hours=24):
                return format_html('<span style="color: orange;">{}h ago</span>', int(time_diff.total_seconds() / 3600))
            else:
                return format_html('<span style="color: red;">{}d ago</span>', time_diff.days)
        return format_html('<span style="color: gray;">Never</span>')
    last_sync_display.short_description = 'Last Sync'
    
    def projects_count(self, obj):
        count = obj.projects.count()
        url = reverse('admin:jira_jiraproject_changelist') + f'?jira_organization__id__exact={obj.id}'
        return format_html('<a href="{}">{} projects</a>', url, count)
    projects_count.short_description = 'Projects'
    
    def sync_actions(self, obj):
        test_url = f"javascript:testJiraConnection('{obj.pk}')"
        return format_html(
            '<a class="button" href="javascript:void(0)" onclick="testJiraConnection({})">Test Connection</a>',
            obj.pk
        )
    sync_actions.short_description = 'Actions'
    
    def sync_selected_organizations(self, request, queryset):
        synced_count = 0
        for org in queryset.filter(sync_enabled=True):
            try:
                sync_jira_organization(org.id)
                synced_count += 1
            except Exception as e:
                self.message_user(request, f'Failed to sync {org.name}: {str(e)}', level='ERROR')
        
        self.message_user(request, f'Successfully triggered sync for {synced_count} organizations.')
    sync_selected_organizations.short_description = 'Sync selected organizations'
    
    def test_connections(self, request, queryset):
        tested_count = 0
        for org in queryset:
            try:
                from .client import JiraAPIClient
                client = JiraAPIClient(org.base_url, org.username, org.api_token)
                success, message = client.test_connection()
                
                org.last_connection_test = timezone.now()
                if success:
                    org.connection_status = 'connected'
                    org.connection_error = ''
                else:
                    org.connection_status = 'failed'
                    org.connection_error = message
                org.save()
                tested_count += 1
                
            except Exception as e:
                self.message_user(request, f'Failed to test {org.name}: {str(e)}', level='ERROR')
        
        self.message_user(request, f'Tested connection for {tested_count} organizations.')
    test_connections.short_description = 'Test connections'
    
    def enable_sync(self, request, queryset):
        count = queryset.update(sync_enabled=True)
        self.message_user(request, f'Enabled sync for {count} organizations.')
    enable_sync.short_description = 'Enable sync'
    
    def disable_sync(self, request, queryset):
        count = queryset.update(sync_enabled=False)
        self.message_user(request, f'Disabled sync for {count} organizations.')
    disable_sync.short_description = 'Disable sync'

    class Media:
        js = ('admin/js/jira_admin.js',)


@admin.register(JiraProject)
class JiraProjectAdmin(admin.ModelAdmin):
    list_display = [
        'jira_key', 'name', 'jira_organization', 'product_display', 
        'project_type', 'sync_enabled', 'total_issues', 'open_issues', 'jira_link'
    ]
    list_filter = ['jira_organization', 'product', 'project_type', 'sync_enabled', 'created_at']
    search_fields = ['jira_key', 'name', 'description', 'product__name']
    readonly_fields = ['jira_id', 'self_url', 'avatar_url', 'created_at', 'updated_at', 'last_issue_sync']
    actions = ['bulk_assign_to_product', 'enable_sync', 'disable_sync', 'sync_issues']
    
    fieldsets = (
        ('Project Info', {
            'fields': ('jira_organization', 'jira_key', 'jira_id', 'name', 'description', 'project_type')
        }),
        ('Product Mapping', {
            'fields': ('product',),
            'description': 'Link this JIRA project to a business product for better organization'
        }),
        ('Project Details', {
            'fields': ('lead_account_id', 'lead_display_name', 'category_name')
        }),
        ('Sync Settings', {
            'fields': ('sync_enabled', 'sync_issues', 'max_issues_to_sync', 'last_issue_sync')
        }),
        ('Statistics', {
            'fields': ('total_issues', 'open_issues', 'in_progress_issues', 'done_issues')
        }),
        ('URLs', {
            'fields': ('self_url', 'avatar_url'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def product_display(self, obj):
        if obj.product:
            url = reverse('admin:products_product_change', args=[obj.product.pk])
            return format_html('<a href="{}">{}</a>', url, obj.product.hierarchy_path)
        return format_html('<span style="color: #999;">No product assigned</span>')
    product_display.short_description = 'Product'
    
    def jira_link(self, obj):
        if obj.jira_url:
            return format_html('<a href="{}" target="_blank">Open in JIRA</a>', obj.jira_url)
        return '-'
    jira_link.short_description = 'JIRA Link'
    
    def bulk_assign_to_product(self, request, queryset):
        from django.http import HttpResponseRedirect
        from django.urls import reverse
        
        project_ids = list(queryset.values_list('id', flat=True))
        request.session['bulk_assign_jira_project_ids'] = project_ids
        
        url = reverse('admin:jira_bulk_assign_projects_to_product')
        return HttpResponseRedirect(url)
    bulk_assign_to_product.short_description = 'Bulk assign to product'
    
    def enable_sync(self, request, queryset):
        count = queryset.update(sync_enabled=True)
        self.message_user(request, f'Enabled sync for {count} projects.')
    enable_sync.short_description = 'Enable sync'
    
    def disable_sync(self, request, queryset):
        count = queryset.update(sync_enabled=False)
        self.message_user(request, f'Disabled sync for {count} projects.')
    disable_sync.short_description = 'Disable sync'
    
    def sync_issues(self, request, queryset):
        synced_count = 0
        for project in queryset.filter(sync_enabled=True):
            try:
                from .services import JiraSyncService
                service = JiraSyncService(project.jira_organization)
                service._sync_project_issues(project)
                synced_count += 1
            except Exception as e:
                self.message_user(request, f'Failed to sync {project.jira_key}: {str(e)}', level='ERROR')
        
        self.message_user(request, f'Successfully synced issues for {synced_count} projects.')
    sync_issues.short_description = 'Sync project issues'