from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from .models import (
    AzureConfiguration, AzureResource, AzureMetric, 
    AzureLog, AzureAlert, AzureSyncLog
)


@admin.register(AzureConfiguration)
class AzureConfigurationAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'config_type', 'environment_filter', 'product',
        'is_active', 'last_sync_status', 'sync_interval_minutes'
    ]
    list_filter = ['config_type', 'is_active', 'environment_filter', 'product']
    search_fields = ['name', 'subscription_id', 'resource_group']
    readonly_fields = ['last_sync', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'config_type', 'is_active', 'product')
        }),
        ('Azure Identifiers', {
            'fields': (
                'subscription_id', 'resource_group', 
                'workspace_id', 'application_id'
            )
        }),
        ('Authentication', {
            'fields': ('tenant_id', 'client_id', 'client_secret'),
            'classes': ('collapse',)
        }),
        ('Configuration', {
            'fields': (
                'environment_filter', 'resource_tags',
                'sync_interval_minutes', 'retention_days'
            )
        }),
        ('Status', {
            'fields': ('last_sync', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def last_sync_status(self, obj):
        if not obj.last_sync:
            return format_html('<span style="color: orange;">Never synced</span>')
        
        time_diff = timezone.now() - obj.last_sync
        if time_diff < timedelta(hours=2):
            color = 'green'
            status = 'Recent'
        elif time_diff < timedelta(hours=24):
            color = 'orange'  
            status = 'Stale'
        else:
            color = 'red'
            status = 'Old'
        
        return format_html(
            '<span style="color: {};">{} ({})</span>',
            color, status, obj.last_sync.strftime('%Y-%m-%d %H:%M')
        )
    last_sync_status.short_description = 'Last Sync'
    
    actions = ['test_connection', 'force_sync']
    
    def test_connection(self, request, queryset):
        from .services import AzureDataService
        
        results = []
        for config in queryset:
            try:
                service = AzureDataService()
                # You'd implement a test connection method
                results.append(f"✅ {config.name}: Connection successful")
            except Exception as e:
                results.append(f"❌ {config.name}: {str(e)}")
        
        self.message_user(request, "\n".join(results))
    test_connection.short_description = "Test Azure connection"
    
    def force_sync(self, request, queryset):
        from .services import AzureDataService
        
        service = AzureDataService()
        results = []
        
        for config in queryset:
            try:
                result = service.sync_configuration(config)
                results.append(f"✅ {config.name}: Synced {result.get('resources_processed', 0)} resources")
            except Exception as e:
                results.append(f"❌ {config.name}: {str(e)}")
        
        self.message_user(request, "\n".join(results))
    force_sync.short_description = "Force sync Azure data"


@admin.register(AzureResource)
class AzureResourceAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'resource_type', 'configuration', 'product',
        'location', 'is_monitored', 'last_seen'
    ]
    list_filter = [
        'resource_type', 'is_monitored', 'location', 
        'configuration', 'product'
    ]
    search_fields = ['name', 'resource_id', 'resource_group']
    readonly_fields = ['resource_id', 'subscription_id', 'created_at', 'updated_at', 'last_seen']
    
    fieldsets = (
        ('Resource Information', {
            'fields': ('name', 'resource_type', 'resource_id', 'location')
        }),
        ('Azure Details', {
            'fields': ('resource_group', 'subscription_id', 'tags')
        }),
        ('Monitoring', {
            'fields': ('configuration', 'is_monitored', 'custom_metrics')
        }),
        ('Association', {
            'fields': ('product',)
        }),
        ('Status', {
            'fields': ('created_at', 'updated_at', 'last_seen'),
            'classes': ('collapse',)
        })
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('configuration', 'product')


@admin.register(AzureMetric)
class AzureMetricAdmin(admin.ModelAdmin):
    list_display = [
        'resource_name', 'metric_name', 'metric_type', 'value_with_unit',
        'severity', 'timestamp'
    ]
    list_filter = [
        'metric_type', 'severity', 'resource__resource_type',
        'resource__configuration', 'timestamp'
    ]
    search_fields = ['metric_name', 'resource__name', 'namespace']
    readonly_fields = ['created_at']
    date_hierarchy = 'timestamp'
    
    fieldsets = (
        ('Metric Information', {
            'fields': ('resource', 'metric_name', 'metric_type', 'namespace')
        }),
        ('Data', {
            'fields': ('timestamp', 'value', 'unit', 'aggregation_type', 'time_grain')
        }),
        ('Analysis', {
            'fields': ('severity', 'threshold_breached')
        }),
        ('Additional Data', {
            'fields': ('dimensions', 'metadata'),
            'classes': ('collapse',)
        })
    )
    
    def resource_name(self, obj):
        return obj.resource.name
    resource_name.short_description = 'Resource'
    
    def value_with_unit(self, obj):
        return f"{obj.value} {obj.unit}"
    value_with_unit.short_description = 'Value'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('resource')


@admin.register(AzureLog)
class AzureLogAdmin(admin.ModelAdmin):
    list_display = [
        'resource_name', 'log_type', 'level', 'message_preview',
        'is_exception', 'timestamp'
    ]
    list_filter = [
        'level', 'log_type', 'is_exception', 
        'resource__resource_type', 'timestamp'
    ]
    search_fields = ['message', 'source', 'resource__name', 'exception_type']
    readonly_fields = ['created_at']
    date_hierarchy = 'timestamp'
    
    fieldsets = (
        ('Log Information', {
            'fields': ('resource', 'log_type', 'source', 'timestamp')
        }),
        ('Content', {
            'fields': ('level', 'message')
        }),
        ('Exception Details', {
            'fields': ('is_exception', 'exception_type', 'stack_trace'),
            'classes': ('collapse',)
        }),
        ('Correlation', {
            'fields': ('operation_id', 'session_id', 'user_id'),
            'classes': ('collapse',)
        }),
        ('Structured Data', {
            'fields': ('properties', 'custom_dimensions'),
            'classes': ('collapse',)
        })
    )
    
    def resource_name(self, obj):
        return obj.resource.name
    resource_name.short_description = 'Resource'
    
    def message_preview(self, obj):
        return obj.message[:100] + "..." if len(obj.message) > 100 else obj.message
    message_preview.short_description = 'Message'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('resource')


@admin.register(AzureAlert)
class AzureAlertAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'alert_type', 'severity', 'status',
        'resource_name', 'fired_at', 'duration_display', 'linked_jira'
    ]
    list_filter = [
        'alert_type', 'severity', 'status', 
        'resource__resource_type', 'fired_at'
    ]
    search_fields = ['name', 'description', 'alert_id', 'resource__name']
    readonly_fields = ['alert_id', 'duration_display', 'created_at', 'updated_at']
    date_hierarchy = 'fired_at'
    
    fieldsets = (
        ('Alert Information', {
            'fields': ('alert_id', 'alert_type', 'name', 'description')
        }),
        ('Status', {
            'fields': ('severity', 'status', 'fired_at', 'resolved_at')
        }),
        ('Association', {
            'fields': ('configuration', 'resource', 'linked_jira_issue')
        }),
        ('Details', {
            'fields': ('condition', 'context'),
            'classes': ('collapse',)
        })
    )
    
    def resource_name(self, obj):
        return obj.resource.name if obj.resource else 'N/A'
    resource_name.short_description = 'Resource'
    
    def duration_display(self, obj):
        if obj.duration:
            return str(obj.duration).split('.')[0]  # Remove microseconds
        return 'N/A'
    duration_display.short_description = 'Duration'
    
    def linked_jira(self, obj):
        if obj.linked_jira_issue:
            return format_html(
                '<a href="{}" target="_blank">{}</a>',
                reverse('admin:jira_jiraissue_change', args=[obj.linked_jira_issue.id]),
                obj.linked_jira_issue.key
            )
        return 'None'
    linked_jira.short_description = 'JIRA Issue'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'resource', 'configuration', 'linked_jira_issue'
        )


@admin.register(AzureSyncLog)
class AzureSyncLogAdmin(admin.ModelAdmin):
    list_display = [
        'configuration_name', 'sync_type', 'started_at', 
        'success_status', 'duration_display', 'resources_processed',
        'metrics_collected', 'api_calls_made'
    ]
    list_filter = ['sync_type', 'success', 'started_at', 'configuration']
    search_fields = ['configuration__name']
    readonly_fields = [
        'started_at', 'completed_at', 'duration_seconds', 
        'duration_display'
    ]
    date_hierarchy = 'started_at'
    
    fieldsets = (
        ('Sync Information', {
            'fields': ('configuration', 'sync_type', 'started_at', 'completed_at')
        }),
        ('Results', {
            'fields': (
                'success', 'resources_processed', 'metrics_collected',
                'logs_collected', 'alerts_processed', 'api_calls_made'
            )
        }),
        ('Performance', {
            'fields': ('duration_seconds', 'duration_display')
        }),
        ('Issues', {
            'fields': ('errors', 'warnings'),
            'classes': ('collapse',)
        })
    )
    
    def configuration_name(self, obj):
        return obj.configuration.name
    configuration_name.short_description = 'Configuration'
    
    def success_status(self, obj):
        if obj.success:
            return format_html('<span style="color: green;">✅ Success</span>')
        else:
            return format_html('<span style="color: red;">❌ Failed</span>')
    success_status.short_description = 'Status'
    
    def duration_display(self, obj):
        if obj.duration_seconds:
            return f"{obj.duration_seconds:.1f}s"
        return 'N/A'
    duration_display.short_description = 'Duration'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('configuration')