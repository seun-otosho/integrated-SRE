from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Q

from .models import (
    SonarCloudOrganization, SonarCloudProject, QualityMeasurement,
    CodeIssue, SonarSyncLog
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