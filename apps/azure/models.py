from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

User = get_user_model()


class AzureConfiguration(models.Model):
    """Azure Application Insights and Log Analytics configuration"""
    
    class ConfigType(models.TextChoices):
        APPLICATION_INSIGHTS = 'app_insights', 'Application Insights'
        LOG_ANALYTICS = 'log_analytics', 'Log Analytics Workspace'
        RESOURCE_GROUP = 'resource_group', 'Resource Group'
        SUBSCRIPTION = 'subscription', 'Subscription'
    
    name = models.CharField(max_length=200, help_text="Friendly name for this configuration")
    config_type = models.CharField(max_length=20, choices=ConfigType.choices)
    
    # Azure identifiers
    subscription_id = models.CharField(max_length=100, help_text="Azure Subscription ID")
    resource_group = models.CharField(max_length=100, blank=True, help_text="Resource Group name")
    workspace_id = models.CharField(max_length=100, blank=True, help_text="Log Analytics Workspace ID")
    application_id = models.CharField(max_length=100, blank=True, help_text="Application Insights Application ID")
    
    # Authentication
    tenant_id = models.CharField(max_length=100, help_text="Azure AD Tenant ID")
    client_id = models.CharField(max_length=100, help_text="Service Principal Client ID")
    client_secret = models.CharField(max_length=500, help_text="Service Principal Client Secret")
    
    # Configuration
    environment_filter = models.CharField(
        max_length=100, 
        default='production',
        help_text="Environment to monitor (production, staging, etc.)"
    )
    resource_tags = models.JSONField(
        default=dict,
        help_text="Resource tags to filter on (e.g., {'Environment': 'production'})"
    )
    
    # Association with products
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Associate with specific product"
    )
    
    # Settings
    is_active = models.BooleanField(default=True)
    sync_interval_minutes = models.PositiveIntegerField(default=60, help_text="How often to sync data")
    retention_days = models.PositiveIntegerField(default=90, help_text="How long to keep synced data")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_sync = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'azure_configurations'
        verbose_name = 'Azure Configuration'
        verbose_name_plural = 'Azure Configurations'
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.get_config_type_display()})"
    
    @property
    def needs_sync(self):
        """Check if this configuration needs syncing"""
        if not self.last_sync:
            return True
        return timezone.now() - self.last_sync > timedelta(minutes=self.sync_interval_minutes)


class AzureResource(models.Model):
    """Azure resources being monitored"""
    
    class ResourceType(models.TextChoices):
        WEB_APP = 'webapp', 'Web App'
        FUNCTION_APP = 'function', 'Function App'
        SQL_DATABASE = 'sql_db', 'SQL Database'
        COSMOS_DB = 'cosmos_db', 'Cosmos DB'
        STORAGE_ACCOUNT = 'storage', 'Storage Account'
        KEY_VAULT = 'keyvault', 'Key Vault'
        APPLICATION_GATEWAY = 'app_gateway', 'Application Gateway'
        LOAD_BALANCER = 'load_balancer', 'Load Balancer'
        VIRTUAL_MACHINE = 'vm', 'Virtual Machine'
        CONTAINER_INSTANCE = 'container', 'Container Instance'
        OTHER = 'other', 'Other'
    
    configuration = models.ForeignKey(AzureConfiguration, on_delete=models.CASCADE, related_name='resources')
    
    # Resource identification
    resource_id = models.CharField(max_length=500, unique=True, help_text="Full Azure Resource ID")
    name = models.CharField(max_length=200)
    resource_type = models.CharField(max_length=20, choices=ResourceType.choices)
    location = models.CharField(max_length=100, help_text="Azure region")
    
    # Resource details
    resource_group = models.CharField(max_length=100)
    subscription_id = models.CharField(max_length=100)
    tags = models.JSONField(default=dict, help_text="Resource tags")
    
    # Monitoring settings
    is_monitored = models.BooleanField(default=True)
    custom_metrics = models.JSONField(default=list, help_text="Custom metrics to collect")
    
    # Product association
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Associated product"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_seen = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'azure_resources'
        verbose_name = 'Azure Resource'
        verbose_name_plural = 'Azure Resources'
        ordering = ['name']
        indexes = [
            models.Index(fields=['resource_type', 'is_monitored']),
            models.Index(fields=['resource_group']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.get_resource_type_display()})"


class AzureMetric(models.Model):
    """Azure metrics data"""
    
    class MetricType(models.TextChoices):
        PERFORMANCE = 'performance', 'Performance'
        AVAILABILITY = 'availability', 'Availability'
        USAGE = 'usage', 'Resource Usage'
        COST = 'cost', 'Cost'
        CUSTOM = 'custom', 'Custom'
    
    class Severity(models.TextChoices):
        INFO = 'info', 'Info'
        WARNING = 'warning', 'Warning'
        ERROR = 'error', 'Error'
        CRITICAL = 'critical', 'Critical'
    
    resource = models.ForeignKey(AzureResource, on_delete=models.CASCADE, related_name='metrics')
    
    # Metric identification
    metric_name = models.CharField(max_length=200)
    metric_type = models.CharField(max_length=20, choices=MetricType.choices)
    namespace = models.CharField(max_length=200, help_text="Azure metric namespace")
    
    # Metric data
    timestamp = models.DateTimeField(db_index=True)
    value = models.FloatField()
    unit = models.CharField(max_length=50, help_text="Metric unit (e.g., 'Percent', 'Count')")
    
    # Aggregation info
    aggregation_type = models.CharField(max_length=50, default='Average', help_text="Average, Maximum, Minimum, etc.")
    time_grain = models.CharField(max_length=20, default='PT1M', help_text="Time grain (e.g., PT1M for 1 minute)")
    
    # Analysis
    severity = models.CharField(max_length=10, choices=Severity.choices, default=Severity.INFO)
    threshold_breached = models.BooleanField(default=False)
    
    # Additional data
    dimensions = models.JSONField(default=dict, help_text="Metric dimensions")
    metadata = models.JSONField(default=dict, help_text="Additional metric metadata")
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'azure_metrics'
        verbose_name = 'Azure Metric'
        verbose_name_plural = 'Azure Metrics'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['resource', 'metric_name', '-timestamp']),
            models.Index(fields=['metric_type', '-timestamp']),
            models.Index(fields=['severity', '-timestamp']),
        ]
    
    def __str__(self):
        return f"{self.resource.name} - {self.metric_name}: {self.value} {self.unit}"


class AzureLog(models.Model):
    """Azure Log Analytics data"""
    
    class LogLevel(models.TextChoices):
        TRACE = 'trace', 'Trace'
        DEBUG = 'debug', 'Debug'
        INFO = 'info', 'Information'
        WARNING = 'warning', 'Warning'
        ERROR = 'error', 'Error'
        CRITICAL = 'critical', 'Critical'
    
    resource = models.ForeignKey(AzureResource, on_delete=models.CASCADE, related_name='logs')
    
    # Log identification
    log_type = models.CharField(max_length=100, help_text="Type of log (Application, System, etc.)")
    source = models.CharField(max_length=200, help_text="Log source")
    
    # Log data
    timestamp = models.DateTimeField(db_index=True)
    level = models.CharField(max_length=10, choices=LogLevel.choices)
    message = models.TextField()
    
    # Structured data
    properties = models.JSONField(default=dict, help_text="Structured log properties")
    custom_dimensions = models.JSONField(default=dict, help_text="Custom dimensions")
    
    # Analysis
    is_exception = models.BooleanField(default=False)
    exception_type = models.CharField(max_length=200, blank=True)
    stack_trace = models.TextField(blank=True)
    
    # Correlation
    operation_id = models.CharField(max_length=100, blank=True, help_text="Operation correlation ID")
    session_id = models.CharField(max_length=100, blank=True)
    user_id = models.CharField(max_length=100, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'azure_logs'
        verbose_name = 'Azure Log'
        verbose_name_plural = 'Azure Logs'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['resource', '-timestamp']),
            models.Index(fields=['level', '-timestamp']),
            models.Index(fields=['is_exception', '-timestamp']),
            models.Index(fields=['operation_id']),
        ]
    
    def __str__(self):
        return f"{self.resource.name} - {self.level}: {self.message[:100]}"


class AzureAlert(models.Model):
    """Azure alerts and incidents"""
    
    class AlertType(models.TextChoices):
        METRIC = 'metric', 'Metric Alert'
        LOG = 'log', 'Log Alert'
        ACTIVITY = 'activity', 'Activity Alert'
        SERVICE_HEALTH = 'service_health', 'Service Health'
    
    class AlertStatus(models.TextChoices):
        ACTIVE = 'active', 'Active'
        RESOLVED = 'resolved', 'Resolved'
        SUPPRESSED = 'suppressed', 'Suppressed'
    
    class AlertSeverity(models.TextChoices):
        SEV0 = 'sev0', 'Sev0 - Critical'
        SEV1 = 'sev1', 'Sev1 - Error'
        SEV2 = 'sev2', 'Sev2 - Warning'
        SEV3 = 'sev3', 'Sev3 - Informational'
        SEV4 = 'sev4', 'Sev4 - Verbose'
    
    configuration = models.ForeignKey(AzureConfiguration, on_delete=models.CASCADE, related_name='alerts')
    resource = models.ForeignKey(AzureResource, on_delete=models.CASCADE, null=True, blank=True, related_name='alerts')
    
    # Alert identification
    alert_id = models.CharField(max_length=200, unique=True)
    alert_type = models.CharField(max_length=20, choices=AlertType.choices)
    name = models.CharField(max_length=300)
    description = models.TextField()
    
    # Alert details
    severity = models.CharField(max_length=10, choices=AlertSeverity.choices)
    status = models.CharField(max_length=20, choices=AlertStatus.choices)
    
    # Timing
    fired_at = models.DateTimeField()
    resolved_at = models.DateTimeField(null=True, blank=True)
    
    # Alert data
    condition = models.JSONField(default=dict, help_text="Alert condition details")
    context = models.JSONField(default=dict, help_text="Alert context and metadata")
    
    # Integration
    linked_jira_issue = models.ForeignKey(
        'jira.JiraIssue',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Linked JIRA issue"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'azure_alerts'
        verbose_name = 'Azure Alert'
        verbose_name_plural = 'Azure Alerts'
        ordering = ['-fired_at']
        indexes = [
            models.Index(fields=['status', '-fired_at']),
            models.Index(fields=['severity', '-fired_at']),
            models.Index(fields=['alert_type', '-fired_at']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.get_severity_display()}) - {self.get_status_display()}"
    
    @property
    def duration(self):
        """Calculate alert duration"""
        end_time = self.resolved_at or timezone.now()
        return end_time - self.fired_at
    
    @property
    def is_active(self):
        """Check if alert is currently active"""
        return self.status == self.AlertStatus.ACTIVE


class AzureSyncLog(models.Model):
    """Log of Azure data synchronization operations"""
    
    class SyncType(models.TextChoices):
        FULL = 'full', 'Full Sync'
        INCREMENTAL = 'incremental', 'Incremental Sync'
        METRICS_ONLY = 'metrics', 'Metrics Only'
        LOGS_ONLY = 'logs', 'Logs Only'
        ALERTS_ONLY = 'alerts', 'Alerts Only'
    
    configuration = models.ForeignKey(AzureConfiguration, on_delete=models.CASCADE, related_name='sync_logs')
    
    # Sync details
    sync_type = models.CharField(max_length=20, choices=SyncType.choices)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Results
    success = models.BooleanField(default=False)
    resources_processed = models.PositiveIntegerField(default=0)
    metrics_collected = models.PositiveIntegerField(default=0)
    logs_collected = models.PositiveIntegerField(default=0)
    alerts_processed = models.PositiveIntegerField(default=0)
    
    # Error handling
    errors = models.JSONField(default=list, help_text="List of errors encountered")
    warnings = models.JSONField(default=list, help_text="List of warnings")
    
    # Performance
    duration_seconds = models.FloatField(null=True, blank=True)
    api_calls_made = models.PositiveIntegerField(default=0)
    
    class Meta:
        db_table = 'azure_sync_logs'
        verbose_name = 'Azure Sync Log'
        verbose_name_plural = 'Azure Sync Logs'
        ordering = ['-started_at']
    
    def __str__(self):
        status = "✅" if self.success else "❌"
        duration = f" ({self.duration_seconds:.1f}s)" if self.duration_seconds else ""
        return f"{status} {self.get_sync_type_display()} - {self.started_at.strftime('%Y-%m-%d %H:%M')}{duration}"
    
    def save(self, *args, **kwargs):
        # Calculate duration if both start and end times are available
        if self.started_at and self.completed_at and not self.duration_seconds:
            delta = self.completed_at - self.started_at
            self.duration_seconds = delta.total_seconds()
        super().save(*args, **kwargs)