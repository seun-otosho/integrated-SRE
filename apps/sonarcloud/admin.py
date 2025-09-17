from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Q

from .models import (
    SonarCloudOrganization, SonarCloudProject, QualityMeasurement,
    CodeIssue, SonarSyncLog, SentrySonarLink, JiraSonarLink, QualityIssueTicket
)
from .services import sync_sonarcloud_organization


@admin.register(SonarCloudOrganization)
class SonarCloudOrganizationAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'organization_key', 'connection_status_display', 'sync_enabled', 
        'projects_count', 'last_sync_display', 'sync_actions'
    ]
    list_filter = ['connection_status', 'sync_enabled', 'created_at']
    search_fields = ['name', 'organization_key', 'description']
    readonly_fields = ['connection_status', 'last_connection_test', 'connection_error', 'last_sync', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Organization Info', {
            'fields': ('name', 'organization_key', 'description')
        }),
        ('Authentication', {
            'fields': ('api_token',),
            'description': 'Create API token at: SonarCloud Account > Security > Generate Tokens'
        }),
        ('URLs', {
            'fields': ('url', 'avatar_url'),
            'classes': ('collapse',)
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
        url = reverse('admin:sonarcloud_sonarcloudproject_changelist') + f'?sonarcloud_organization__id__exact={obj.id}'
        return format_html('<a href="{}">{} projects</a>', url, count)
    projects_count.short_description = 'Projects'
    
    def sync_actions(self, obj):
        return format_html(
            '<a class="button" href="javascript:void(0)" onclick="testSonarConnection({})">Test Connection</a>',
            obj.pk
        )
    sync_actions.short_description = 'Actions'
    
    def sync_selected_organizations(self, request, queryset):
        synced_count = 0
        for org in queryset.filter(sync_enabled=True):
            try:
                sync_sonarcloud_organization(org.id)
                synced_count += 1
            except Exception as e:
                self.message_user(request, f'Failed to sync {org.name}: {str(e)}', level='ERROR')
        
        self.message_user(request, f'Successfully triggered sync for {synced_count} organizations.')
    sync_selected_organizations.short_description = 'Sync selected organizations'
    
    def test_connections(self, request, queryset):
        tested_count = 0
        for org in queryset:
            try:
                from .client import SonarCloudAPIClient
                client = SonarCloudAPIClient(org.api_token)
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
        js = ('admin/js/sonarcloud_admin.js',)


@admin.register(SonarCloudProject)
class SonarCloudProjectAdmin(admin.ModelAdmin):
    list_display = [
        'project_key', 'name', 'sonarcloud_organization', 'product_display', 
        'quality_gate_display', 'overall_rating_display', 'coverage_display',
        'lines_of_code', 'technical_debt_display', 'sonarcloud_link'
    ]
    list_filter = [
        'sonarcloud_organization', 'product', 'quality_gate_status', 
        'reliability_rating', 'security_rating', 'maintainability_rating',
        'sync_enabled', 'last_analysis'
    ]
    search_fields = ['project_key', 'name', 'description', 'product__name']
    readonly_fields = [
        'project_key', 'last_analysis', 'created_at', 'updated_at', 'last_measure_sync',
        'quality_gate_status', 'reliability_rating', 'security_rating', 'maintainability_rating',
        'lines_of_code', 'coverage', 'duplication', 'technical_debt',
        'bugs', 'vulnerabilities', 'security_hotspots', 'code_smells'
    ]
    actions = ['bulk_assign_to_product', 'enable_sync', 'disable_sync', 'sync_measures']
    
    fieldsets = (
        ('Project Info', {
            'fields': ('sonarcloud_organization', 'project_key', 'name', 'description', 'visibility')
        }),
        ('Product Mapping', {
            'fields': ('product',),
            'description': 'Link this SonarCloud project to a business product for better organization'
        }),
        ('Project Details', {
            'fields': ('language', 'main_branch', 'last_analysis')
        }),
        ('Quality Gate & Ratings', {
            'fields': ('quality_gate_status', 'reliability_rating', 'security_rating', 'maintainability_rating')
        }),
        ('Code Metrics', {
            'fields': ('lines_of_code', 'coverage', 'duplication', 'technical_debt')
        }),
        ('Issues', {
            'fields': ('bugs', 'vulnerabilities', 'security_hotspots', 'code_smells')
        }),
        ('Sync Settings', {
            'fields': ('sync_enabled', 'sync_measures', 'sync_issues', 'last_measure_sync')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('sonarcloud_organization', 'product')
    
    def product_display(self, obj):
        if obj.product:
            url = reverse('admin:products_product_change', args=[obj.product.pk])
            return format_html('<a href="{}">{}</a>', url, obj.product.hierarchy_path)
        return format_html('<span style="color: #999;">No product assigned</span>')
    product_display.short_description = 'Product'
    
    def quality_gate_display(self, obj):
        colors = {
            'OK': 'green',
            'ERROR': 'red',
            'WARN': 'orange',
            'NONE': 'gray'
        }
        color = colors.get(obj.quality_gate_status, 'gray')
        
        icons = {
            'OK': '✅',
            'ERROR': '❌',
            'WARN': '⚠️',
            'NONE': '❓'
        }
        icon = icons.get(obj.quality_gate_status, '❓')
        
        return format_html(
            '<span style="color: {};">{} {}</span>',
            color, icon, obj.get_quality_gate_status_display()
        )
    quality_gate_display.short_description = 'Quality Gate'
    
    def overall_rating_display(self, obj):
        ratings = [obj.reliability_rating, obj.security_rating, obj.maintainability_rating]
        rating_labels = ['R', 'S', 'M']  # Reliability, Security, Maintainability
        
        html_parts = []
        for rating, label in zip(ratings, rating_labels):
            if rating:
                color = {
                    'A': 'green', 'B': 'yellowgreen', 'C': 'orange', 'D': 'orangered', 'E': 'red'
                }.get(rating, 'gray')
                html_parts.append(f'<span style="color: {color}; font-weight: bold;" title="{label}">{rating}</span>')
            else:
                html_parts.append('<span style="color: gray;">-</span>')
        
        return format_html(' / '.join(html_parts))
    overall_rating_display.short_description = 'R/S/M Ratings'
    
    def coverage_display(self, obj):
        if obj.coverage is not None:
            color = 'green' if obj.coverage >= 80 else 'orange' if obj.coverage >= 60 else 'red'
            coverage_str = f"{obj.coverage:.1f}%"
            return format_html('<span style="color: {};">{}</span>', color, coverage_str)
        return '-'
    coverage_display.short_description = 'Coverage'
    
    def technical_debt_display(self, obj):
        if obj.technical_debt > 0:
            hours = obj.technical_debt / 60
            if hours >= 24:
                days = hours / 24
                return format_html('<span style="color: red;">{:.1f}d</span>', days)
            elif hours >= 1:
                return format_html('<span style="color: orange;">{:.1f}h</span>', hours)
            else:
                return format_html('<span style="color: green;">{}min</span>', obj.technical_debt)
        return '0'
    technical_debt_display.short_description = 'Tech Debt'
    
    def sonarcloud_link(self, obj):
        if obj.sonarcloud_url:
            return format_html('<a href="{}" target="_blank">Open in SonarCloud</a>', obj.sonarcloud_url)
        return '-'
    sonarcloud_link.short_description = 'SonarCloud Link'
    
    def bulk_assign_to_product(self, request, queryset):
        from django.http import HttpResponseRedirect
        from django.urls import reverse
        
        project_ids = list(queryset.values_list('id', flat=True))
        request.session['bulk_assign_sonarcloud_project_ids'] = project_ids
        
        url = reverse('admin:sonarcloud_bulk_assign_projects_to_product')
        return HttpResponseRedirect(url)
    
    def get_urls(self):
        """Add custom URLs for bulk operations"""
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path(
                'bulk-assign-projects-to-product/',
                self.admin_site.admin_view(self.bulk_assign_projects_to_product_view),
                name='sonarcloud_bulk_assign_projects_to_product',
            ),
        ]
        return custom_urls + urls
    
    def bulk_assign_projects_to_product_view(self, request):
        """View for bulk assigning SonarCloud projects to a product"""
        from django.shortcuts import render, redirect
        from django.contrib import messages
        from apps.products.models import Product
        
        # Get project IDs from session
        project_ids = request.session.get('bulk_assign_sonarcloud_project_ids', [])
        if not project_ids:
            messages.error(request, 'No projects selected for bulk assignment.')
            return redirect('admin:sonarcloud_sonarcloudproject_changelist')
        
        projects = SonarCloudProject.objects.filter(id__in=project_ids).select_related('sonarcloud_organization', 'product')
        
        if request.method == 'POST':
            product_id = request.POST.get('product')
            
            if product_id:
                try:
                    product = Product.objects.get(id=product_id)
                    
                    # Update projects
                    updated_count = projects.update(product=product)
                    
                    messages.success(
                        request,
                        f'Successfully assigned {updated_count} SonarCloud projects to "{product.name}"'
                    )
                    
                    # Clear session
                    del request.session['bulk_assign_sonarcloud_project_ids']
                    
                except Product.DoesNotExist:
                    messages.error(request, 'Selected product does not exist.')
            else:
                # Unassign from product
                updated_count = projects.update(product=None)
                messages.success(
                    request,
                    f'Successfully unassigned {updated_count} SonarCloud projects from any product'
                )
                
                # Clear session
                del request.session['bulk_assign_sonarcloud_project_ids']
            
            return redirect('admin:sonarcloud_sonarcloudproject_changelist')
        
        # Group projects by organization for display
        organizations_with_projects = {}
        for project in projects:
            org_name = project.sonarcloud_organization.name
            if org_name not in organizations_with_projects:
                organizations_with_projects[org_name] = []
            organizations_with_projects[org_name].append(project)
        
        # Get all products for selection
        products = Product.objects.all().order_by('name')
        
        context = {
            'title': 'Bulk Assign SonarCloud Projects to Product',
            'organizations_with_projects': organizations_with_projects,
            'products': products,
            'projects_count': len(project_ids),
            'opts': SonarCloudProject._meta,
            'has_change_permission': True,
        }
        
        return render(request, 'admin/sonarcloud/bulk_assign_projects_to_product.html', context)
    bulk_assign_to_product.short_description = 'Bulk assign to product'
    
    def enable_sync(self, request, queryset):
        count = queryset.update(sync_enabled=True)
        self.message_user(request, f'Enabled sync for {count} projects.')
    enable_sync.short_description = 'Enable sync'
    
    def disable_sync(self, request, queryset):
        count = queryset.update(sync_enabled=False)
        self.message_user(request, f'Disabled sync for {count} projects.')
    disable_sync.short_description = 'Disable sync'
    
    def sync_measures(self, request, queryset):
        synced_count = 0
        for project in queryset.filter(sync_enabled=True):
            try:
                from .services import SonarCloudSyncService
                service = SonarCloudSyncService(project.sonarcloud_organization)
                service._sync_project_measures(project)
                synced_count += 1
            except Exception as e:
                self.message_user(request, f'Failed to sync {project.project_key}: {str(e)}', level='ERROR')
        
        self.message_user(request, f'Successfully synced measures for {synced_count} projects.')
    sync_measures.short_description = 'Sync project measures'


@admin.register(QualityMeasurement)
class QualityMeasurementAdmin(admin.ModelAdmin):
    list_display = [
        'project', 'analysis_date', 'branch', 'quality_gate_status', 
        'overall_rating_display', 'coverage', 'lines_of_code', 'technical_debt_display'
    ]
    list_filter = [
        'project__sonarcloud_organization', 'project', 'quality_gate_status', 
        'reliability_rating', 'security_rating', 'maintainability_rating',
        'analysis_date'
    ]
    search_fields = ['project__project_key', 'project__name', 'branch']
    readonly_fields = ['created_at']
    date_hierarchy = 'analysis_date'
    
    fieldsets = (
        ('Measurement Info', {
            'fields': ('project', 'analysis_date', 'branch', 'quality_gate_status')
        }),
        ('Ratings', {
            'fields': ('reliability_rating', 'security_rating', 'maintainability_rating')
        }),
        ('Code Metrics', {
            'fields': ('lines_of_code', 'coverage', 'duplication', 'technical_debt')
        }),
        ('Issues', {
            'fields': ('bugs', 'vulnerabilities', 'security_hotspots', 'code_smells')
        }),
        ('Complexity', {
            'fields': ('complexity', 'cognitive_complexity', 'classes', 'functions'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def has_add_permission(self, request):
        return False  # Measurements are created automatically
    
    def overall_rating_display(self, obj):
        ratings = [obj.reliability_rating, obj.security_rating, obj.maintainability_rating]
        rating_labels = ['R', 'S', 'M']
        
        html_parts = []
        for rating, label in zip(ratings, rating_labels):
            if rating:
                color = {
                    'A': 'green', 'B': 'yellowgreen', 'C': 'orange', 'D': 'orangered', 'E': 'red'
                }.get(rating, 'gray')
                html_parts.append(f'<span style="color: {color}; font-weight: bold;" title="{label}">{rating}</span>')
            else:
                html_parts.append('<span style="color: gray;">-</span>')
        
        return format_html(' / '.join(html_parts))
    overall_rating_display.short_description = 'R/S/M Ratings'
    
    def technical_debt_display(self, obj):
        if obj.technical_debt > 0:
            hours = obj.technical_debt / 60
            if hours >= 24:
                days = hours / 24
                return f'{days:.1f}d'
            elif hours >= 1:
                return f'{hours:.1f}h'
            else:
                return f'{obj.technical_debt}min'
        return '0'
    technical_debt_display.short_description = 'Tech Debt'


@admin.register(CodeIssue)
class CodeIssueAdmin(admin.ModelAdmin):
    list_display = [
        'sonarcloud_key', 'message_short', 'project', 'type', 'severity_display',
        'component_short', 'line', 'status', 'debt_display', 'creation_date'
    ]
    list_filter = [
        'project__sonarcloud_organization', 'project', 'type', 'severity', 
        'status', 'creation_date'
    ]
    search_fields = ['sonarcloud_key', 'message', 'component', 'rule']
    readonly_fields = [
        'sonarcloud_key', 'rule', 'creation_date', 'update_date', 'created_at', 'updated_at'
    ]
    date_hierarchy = 'creation_date'
    
    fieldsets = (
        ('Issue Info', {
            'fields': ('project', 'sonarcloud_key', 'rule', 'type', 'severity')
        }),
        ('Content', {
            'fields': ('message', 'component', 'line')
        }),
        ('Status', {
            'fields': ('status', 'resolution')
        }),
        ('Effort', {
            'fields': ('effort', 'debt')
        }),
        ('Timestamps', {
            'fields': ('creation_date', 'update_date', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('project', 'project__sonarcloud_organization')
    
    def message_short(self, obj):
        if len(obj.message) > 80:
            return obj.message[:80] + '...'
        return obj.message
    message_short.short_description = 'Message'
    
    def severity_display(self, obj):
        colors = {
            'BLOCKER': '#d04437',
            'CRITICAL': '#ff5722', 
            'MAJOR': '#ff9800',
            'MINOR': '#ffeb3b',
            'INFO': '#2196f3'
        }
        color = colors.get(obj.severity, '#666666')
        
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.severity
        )
    severity_display.short_description = 'Severity'
    
    def component_short(self, obj):
        # Show just the filename, not the full path
        if '/' in obj.component:
            return obj.component.split('/')[-1]
        return obj.component
    component_short.short_description = 'File'
    
    def debt_display(self, obj):
        if obj.debt > 0:
            if obj.debt >= 60:
                hours = obj.debt / 60
                return f'{hours:.1f}h'
            else:
                return f'{obj.debt}min'
        return '0'
    debt_display.short_description = 'Debt'


@admin.register(SonarSyncLog)
class SonarSyncLogAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'sonarcloud_organization', 'sync_type', 'status_display', 
        'duration_display', 'projects_synced', 'measures_synced', 'issues_synced', 'started_at'
    ]
    list_filter = ['sonarcloud_organization', 'sync_type', 'status', 'started_at']
    search_fields = ['sonarcloud_organization__name', 'error_message']
    readonly_fields = [
        'sonarcloud_organization', 'sync_type', 'status', 'started_at', 'completed_at',
        'duration_seconds', 'projects_synced', 'measures_synced', 'issues_synced', 
        'error_message', 'error_details'
    ]
    
    fieldsets = (
        ('Sync Info', {
            'fields': ('sonarcloud_organization', 'sync_type', 'status')
        }),
        ('Results', {
            'fields': ('projects_synced', 'measures_synced', 'issues_synced', 'duration_seconds')
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
        colors = {
            'started': '#6c757d',
            'success': '#198754',
            'failed': '#dc3545',
            'partial': '#fd7e14'
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
        if obj.duration_seconds is not None:
            if obj.duration_seconds < 60:
                return f"{obj.duration_seconds:.1f}s"
            else:
                minutes = int(obj.duration_seconds // 60)
                seconds = int(obj.duration_seconds % 60)
                return f"{minutes}m {seconds}s"
        return '-'
    duration_display.short_description = 'Duration'


@admin.register(SentrySonarLink)
class SentrySonarLinkAdmin(admin.ModelAdmin):
    list_display = [
        'link_id', 'sentry_project_display', 'sonarcloud_project_display', 'link_type',
        'quality_gate_status', 'created_by_user', 'created_at'
    ]
    list_filter = [
        'link_type', 'block_releases_on_quality_gate', 
        'sonarcloud_project__sonarcloud_organization', 'created_at'
    ]
    search_fields = [
        'sentry_project__name', 'sonarcloud_project__name', 'creation_notes'
    ]
    readonly_fields = ['created_at', 'updated_at', 'last_quality_sync']
    
    fieldsets = (
        ('Link Info', {
            'fields': ('sentry_project', 'sonarcloud_project', 'link_type', 'created_by_user')
        }),
        ('Quality Gate Settings', {
            'fields': (
                'block_releases_on_quality_gate', 'minimum_coverage_threshold', 
                'maximum_debt_threshold'
            )
        }),
        ('Sync Tracking', {
            'fields': ('last_quality_sync', 'quality_sync_errors'),
            'classes': ('collapse',)
        }),
        ('Notes', {
            'fields': ('creation_notes',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'sentry_project', 'sentry_project__organization', 
            'sonarcloud_project', 'sonarcloud_project__sonarcloud_organization',
            'created_by_user'
        )
    
    def link_id(self, obj):
        return f"S{obj.sentry_project.id}-SC{obj.sonarcloud_project.id}"
    link_id.short_description = 'Link ID'
    
    def sentry_project_display(self, obj):
        url = reverse('admin:sentry_sentryproject_change', args=[obj.sentry_project.pk])
        return format_html('<a href="{}">{}</a>', url, obj.sentry_project)
    sentry_project_display.short_description = 'Sentry Project'
    
    def sonarcloud_project_display(self, obj):
        url = reverse('admin:sonarcloud_sonarcloudproject_change', args=[obj.sonarcloud_project.pk])
        return format_html('<a href="{}">{}</a>', url, obj.sonarcloud_project)
    sonarcloud_project_display.short_description = 'SonarCloud Project'
    
    def quality_gate_status(self, obj):
        status = obj.current_quality_status
        if status['status'] == 'ok':
            return format_html('<span style="color: green;">✅ Passed</span>')
        elif status['status'] == 'blocked':
            issues = ', '.join(status.get('issues', []))
            return format_html('<span style="color: red;">❌ Blocked</span><br><small>{}</small>', issues)
        else:
            return format_html('<span style="color: gray;">❓ {}</span>', status.get('message', 'Unknown'))
    quality_gate_status.short_description = 'Quality Status'


@admin.register(JiraSonarLink)
class JiraSonarLinkAdmin(admin.ModelAdmin):
    list_display = [
        'link_id', 'jira_project_display', 'sonarcloud_project_display', 'link_type',
        'automation_status', 'tickets_created_count', 'created_by_user', 'created_at'
    ]
    list_filter = [
        'link_type', 'auto_create_security_tickets', 'auto_create_debt_tickets',
        'sonarcloud_project__sonarcloud_organization', 'created_at'
    ]
    search_fields = [
        'jira_project__jira_key', 'jira_project__name', 'sonarcloud_project__name'
    ]
    readonly_fields = ['created_at', 'updated_at', 'last_ticket_creation_sync', 'tickets_created_count']
    actions = ['process_automated_tickets']
    
    fieldsets = (
        ('Link Info', {
            'fields': ('jira_project', 'sonarcloud_project', 'link_type', 'created_by_user')
        }),
        ('Automation Settings', {
            'fields': (
                'auto_create_security_tickets', 'auto_create_debt_tickets', 'auto_create_coverage_tickets'
            )
        }),
        ('Thresholds', {
            'fields': (
                'security_severity_threshold', 'debt_threshold_hours', 'coverage_drop_threshold'
            )
        }),
        ('JIRA Ticket Settings', {
            'fields': (
                'default_issue_type', 'default_priority', 'security_issue_type', 'security_priority'
            )
        }),
        ('Sync Tracking', {
            'fields': ('last_ticket_creation_sync', 'tickets_created_count'),
            'classes': ('collapse',)
        }),
        ('Notes', {
            'fields': ('creation_notes',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'jira_project', 'jira_project__jira_organization',
            'sonarcloud_project', 'sonarcloud_project__sonarcloud_organization',
            'created_by_user'
        )
    
    def link_id(self, obj):
        return f"J{obj.jira_project.id}-SC{obj.sonarcloud_project.id}"
    link_id.short_description = 'Link ID'
    
    def jira_project_display(self, obj):
        url = reverse('admin:jira_jiraproject_change', args=[obj.jira_project.pk])
        return format_html('<a href="{}">{}</a>', url, obj.jira_project)
    jira_project_display.short_description = 'JIRA Project'
    
    def sonarcloud_project_display(self, obj):
        url = reverse('admin:sonarcloud_sonarcloudproject_change', args=[obj.sonarcloud_project.pk])
        return format_html('<a href="{}">{}</a>', url, obj.sonarcloud_project)
    sonarcloud_project_display.short_description = 'SonarCloud Project'
    
    def automation_status(self, obj):
        statuses = []
        if obj.auto_create_security_tickets:
            statuses.append('🔒 Security')
        if obj.auto_create_debt_tickets:
            statuses.append('🔧 Debt')
        if obj.auto_create_coverage_tickets:
            statuses.append('📊 Coverage')
        
        if statuses:
            return format_html('<span style="color: green;">{}</span>', ' | '.join(statuses))
        else:
            return format_html('<span style="color: gray;">Manual only</span>')
    automation_status.short_description = 'Automation'
    
    def process_automated_tickets(self, request, queryset):
        from .services_integration import JiraQualityService
        service = JiraQualityService()
        
        total_tickets = 0
        for link in queryset:
            try:
                results = service.process_automated_ticket_creation(link)
                tickets_created = (
                    results['security_tickets'] + 
                    results['debt_tickets'] + 
                    results['coverage_tickets']
                )
                total_tickets += tickets_created
                
                if results['errors']:
                    for error in results['errors']:
                        self.message_user(request, f'{link}: {error}', level='WARNING')
                        
            except Exception as e:
                self.message_user(request, f'Failed to process {link}: {str(e)}', level='ERROR')
        
        self.message_user(request, f'Successfully created {total_tickets} automated tickets.')
    process_automated_tickets.short_description = 'Process automated ticket creation'


@admin.register(QualityIssueTicket)
class QualityIssueTicketAdmin(admin.ModelAdmin):
    list_display = [
        'ticket_id', 'jira_issue_display', 'sonarcloud_issue_display', 
        'creation_reason', 'auto_created', 'sync_enabled', 'created_at'
    ]
    list_filter = [
        'creation_reason', 'auto_created', 'sync_enabled',
        'jira_sonar_link__jira_project__jira_organization', 'created_at'
    ]
    search_fields = [
        'jira_issue__jira_key', 'jira_issue__summary', 
        'sonarcloud_issue__sonarcloud_key', 'sonarcloud_issue__message'
    ]
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Ticket Link Info', {
            'fields': ('sonarcloud_issue', 'jira_issue', 'jira_sonar_link')
        }),
        ('Creation Context', {
            'fields': ('creation_reason', 'auto_created')
        }),
        ('Sync Settings', {
            'fields': ('sync_enabled',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'sonarcloud_issue', 'sonarcloud_issue__project',
            'jira_issue', 'jira_issue__jira_project',
            'jira_sonar_link'
        )
    
    def ticket_id(self, obj):
        return f"{obj.jira_issue.jira_key}←{obj.sonarcloud_issue.sonarcloud_key}"
    ticket_id.short_description = 'Ticket ID'
    
    def jira_issue_display(self, obj):
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
    
    def sonarcloud_issue_display(self, obj):
        admin_url = reverse('admin:sonarcloud_codeissue_change', args=[obj.sonarcloud_issue.pk])
        message = obj.sonarcloud_issue.message
        if len(message) > 50:
            message = message[:50] + '...'
        
        return format_html('<a href="{}" title="{}">{}</a>', 
                          admin_url, obj.sonarcloud_issue.message, message)
    sonarcloud_issue_display.short_description = 'SonarCloud Issue'