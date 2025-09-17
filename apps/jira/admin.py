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

    def get_urls(self):
        """Add custom URLs for bulk operations"""
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path(
                'bulk-assign-projects-to-product/',
                self.admin_site.admin_view(self.bulk_assign_projects_to_product_view),
                name='jira_bulk_assign_projects_to_product',
            ),
        ]
        return custom_urls + urls
    
    def bulk_assign_projects_to_product_view(self, request):
        """View for bulk assigning JIRA projects to a product"""
        from django.shortcuts import render, redirect
        from django.contrib import messages
        from apps.products.models import Product
        
        # Get project IDs from session
        project_ids = request.session.get('bulk_assign_jira_project_ids', [])
        if not project_ids:
            messages.error(request, 'No projects selected for bulk assignment.')
            return redirect('admin:jira_jiraproject_changelist')
        
        projects = JiraProject.objects.filter(id__in=project_ids).select_related('jira_organization', 'product')
        
        if request.method == 'POST':
            product_id = request.POST.get('product')
            
            if product_id:
                try:
                    product = Product.objects.get(id=product_id)
                    
                    # Update projects
                    updated_count = projects.update(product=product)
                    
                    messages.success(
                        request,
                        f'Successfully assigned {updated_count} JIRA projects to "{product.name}"'
                    )
                    
                    # Clear session
                    del request.session['bulk_assign_jira_project_ids']
                    
                except Product.DoesNotExist:
                    messages.error(request, 'Selected product does not exist.')
            else:
                # Unassign from product
                updated_count = projects.update(product=None)
                messages.success(
                    request,
                    f'Successfully unassigned {updated_count} JIRA projects from any product'
                )
                
                # Clear session
                del request.session['bulk_assign_jira_project_ids']
            
            return redirect('admin:jira_jiraproject_changelist')
        
        # Group projects by organization for display
        organizations_with_projects = {}
        for project in projects:
            org_name = project.jira_organization.name
            if org_name not in organizations_with_projects:
                organizations_with_projects[org_name] = []
            organizations_with_projects[org_name].append(project)
        
        # Get all products for selection
        products = Product.objects.all().order_by('name')
        
        context = {
            'title': 'Bulk Assign JIRA Projects to Product',
            'organizations_with_projects': organizations_with_projects,
            'products': products,
            'projects_count': len(project_ids),
            'opts': JiraProject._meta,
            'has_change_permission': True,
        }
        
        return render(request, 'admin/jira/bulk_assign_projects_to_product.html', context)

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


@admin.register(JiraIssue)
class JiraIssueAdmin(admin.ModelAdmin):
    list_display = [
        'jira_key', 'summary_short', 'jira_project', 'issue_type', 'status_display', 
        'priority', 'assignee_display', 'sentry_link', 'jira_created', 'jira_updated'
    ]
    list_filter = [
        'issue_type', 'status_category',
        'priority', 'created_from_sentry', 'jira_created', 'jira_project__jira_organization', 'jira_project',
    ]
    search_fields = ['jira_key', 'summary', 'description', 'assignee_display_name', 'reporter_display_name']
    readonly_fields = [
        'jira_id', 'jira_key', 'self_url', 'jira_created', 'jira_updated', 
        'created_from_sentry', 'created_at', 'updated_at'
    ]
    
    fieldsets = (
        ('Issue Info', {
            'fields': ('jira_project', 'jira_key', 'jira_id', 'summary', 'description')
        }),
        ('Classification', {
            'fields': ('issue_type', 'status', 'status_category', 'priority')
        }),
        ('People', {
            'fields': (
                ('assignee_account_id', 'assignee_display_name', 'assignee_email'),
                ('reporter_account_id', 'reporter_display_name', 'reporter_email')
            )
        }),
        ('Sentry Integration', {
            'fields': ('sentry_issue', 'created_from_sentry', 'sentry_sync_enabled', 'last_sentry_sync'),
            'description': 'Integration with Sentry error tracking'
        }),
        ('Metadata', {
            'fields': ('labels', 'components', 'fix_versions'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('jira_created', 'jira_updated', 'resolution_date', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
        ('URLs', {
            'fields': ('self_url',),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'jira_project', 'jira_project__jira_organization', 'sentry_issue'
        )
    
    def summary_short(self, obj):
        """Display shortened summary"""
        if len(obj.summary) > 60:
            return obj.summary[:60] + '...'
        return obj.summary
    summary_short.short_description = 'Summary'
    
    def status_display(self, obj):
        """Display status with color coding"""
        colors = {
            'new': '#6c757d',          # Gray for new
            'indeterminate': '#fd7e14', # Orange for in progress  
            'done': '#198754'          # Green for done
        }
        color = colors.get(obj.status_category, '#6c757d')
        
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.status
        )
    status_display.short_description = 'Status'
    
    def assignee_display(self, obj):
        """Display assignee with email if available"""
        if obj.assignee_display_name:
            if obj.assignee_email:
                return format_html(
                    '<span title="{}">{}</span>',
                    obj.assignee_email, obj.assignee_display_name
                )
            return obj.assignee_display_name
        return format_html('<span style="color: #999;">Unassigned</span>')
    assignee_display.short_description = 'Assignee'
    
    def sentry_link(self, obj):
        """Display link to Sentry issue if connected"""
        if obj.sentry_issue:
            url = reverse('admin:sentry_sentryissue_change', args=[obj.sentry_issue.pk])
            return format_html(
                '<a href="{}" title="{}">🔗 Sentry</a>',
                url, obj.sentry_issue.title[:50]
            )
        elif obj.created_from_sentry:
            return format_html('<span style="color: #dc3545;">❌ Orphaned</span>')
        return '-'
    sentry_link.short_description = 'Sentry Link'


@admin.register(SentryJiraLink)
class SentryJiraLinkAdmin(admin.ModelAdmin):
    list_display = [
        'link_id', 'sentry_issue_display', 'jira_issue_display', 'link_type',
        'sync_status', 'created_by_user', 'created_at'
    ]
    list_filter = [
        'link_type', 'sync_sentry_to_jira', 'sync_jira_to_sentry', 
        'jira_issue__jira_project__jira_organization', 'created_at'
    ]
    search_fields = [
        'sentry_issue__title', 'jira_issue__jira_key', 'jira_issue__summary',
        'creation_notes', 'created_by_user__username'
    ]
    readonly_fields = ['created_at', 'updated_at', 'last_sync_sentry_to_jira', 'last_sync_jira_to_sentry']
    
    fieldsets = (
        ('Link Info', {
            'fields': ('sentry_issue', 'jira_issue', 'link_type', 'created_by_user')
        }),
        ('Sync Settings', {
            'fields': (
                'sync_sentry_to_jira', 'sync_jira_to_sentry',
                'last_sync_sentry_to_jira', 'last_sync_jira_to_sentry'
            )
        }),
        ('Notes & Errors', {
            'fields': ('creation_notes', 'sync_errors'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'sentry_issue', 'sentry_issue__project', 'jira_issue', 
            'jira_issue__jira_project', 'created_by_user'
        )
    
    def link_id(self, obj):
        """Display a short identifier for the link"""
        return f"S{obj.sentry_issue.id}-J{obj.jira_issue.id}"
    link_id.short_description = 'Link ID'
    
    def sentry_issue_display(self, obj):
        """Display Sentry issue with link to admin"""
        url = reverse('admin:sentry_sentryissue_change', args=[obj.sentry_issue.pk])
        title = obj.sentry_issue.title
        if len(title) > 40:
            title = title[:40] + '...'
        
        return format_html(
            '<a href="{}" title="{}">{}</a>',
            url, obj.sentry_issue.title, title
        )
    sentry_issue_display.short_description = 'Sentry Issue'
    
    def jira_issue_display(self, obj):
        """Display JIRA issue with link to admin and external JIRA"""
        admin_url = reverse('admin:jira_jiraissue_change', args=[obj.jira_issue.pk])
        jira_url = obj.jira_issue.jira_url
        
        if jira_url:
            return format_html(
                '<a href="{}">{}</a> | <a href="{}" target="_blank">JIRA</a>',
                admin_url, obj.jira_issue.jira_key, jira_url
            )
        else:
            return format_html('<a href="{}">{}</a>', admin_url, obj.jira_issue.jira_key)
    jira_issue_display.short_description = 'JIRA Issue'
    
    def sync_status(self, obj):
        """Display sync status with indicators"""
        sentry_to_jira = '✅' if obj.sync_sentry_to_jira else '❌'
        jira_to_sentry = '✅' if obj.sync_jira_to_sentry else '❌'
        
        return format_html(
            '<span title="Sentry → JIRA">{}</span> | <span title="JIRA → Sentry">{}</span>',
            sentry_to_jira, jira_to_sentry
        )
    sync_status.short_description = 'Sync Status'


@admin.register(JiraSyncLog)
class JiraSyncLogAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'jira_organization', 'sync_type', 'status_display', 
        'duration_display', 'projects_synced', 'issues_synced', 'started_at'
    ]
    list_filter = ['jira_organization', 'sync_type', 'status', 'started_at']
    search_fields = ['jira_organization__name', 'error_message']
    readonly_fields = [
        'jira_organization', 'sync_type', 'status', 'started_at', 'completed_at',
        'duration_seconds', 'projects_synced', 'issues_synced', 'error_message', 'error_details'
    ]
    
    fieldsets = (
        ('Sync Info', {
            'fields': ('jira_organization', 'sync_type', 'status')
        }),
        ('Results', {
            'fields': ('projects_synced', 'issues_synced', 'duration_seconds')
        }),
        ('Timing', {
            'fields': ('started_at', 'completed_at')
        }),
        ('Errors', {
            'fields': ('error_message', 'error_details'),
            'classes': ('collapse',)
        }),
    )
    
    def has_add_permission(self, request):
        return False  # Sync logs are created automatically
    
    def status_display(self, obj):
        """Display status with color coding"""
        colors = {
            'started': '#6c757d',    # Gray
            'success': '#198754',    # Green
            'failed': '#dc3545',     # Red
            'partial': '#fd7e14'     # Orange
        }
        color = colors.get(obj.status, '#6c757d')
        
        icon_map = {
            'started': '🔄',
            'success': '✅',
            'failed': '❌',
            'partial': '⚠️'
        }
        icon = icon_map.get(obj.status, '❓')
        
        return format_html(
            '<span style="color: {};">{} {}</span>',
            color, icon, obj.get_status_display()
        )
    status_display.short_description = 'Status'
    
    def duration_display(self, obj):
        """Display duration in human readable format"""
        if obj.duration_seconds is not None:
            if obj.duration_seconds < 60:
                return f"{obj.duration_seconds:.1f}s"
            else:
                minutes = int(obj.duration_seconds // 60)
                seconds = int(obj.duration_seconds % 60)
                return f"{minutes}m {seconds}s"
        return '-'
    duration_display.short_description = 'Duration'