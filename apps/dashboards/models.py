from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class Dashboard(models.Model):
    """Custom dashboard configurations"""
    
    class DashboardType(models.TextChoices):
        EXECUTIVE = 'executive', 'Executive Overview'
        PRODUCT = 'product', 'Product Health'
        ENVIRONMENT = 'environment', 'Environment Status'
        TEAM = 'team', 'Team Performance'
        QUALITY = 'quality', 'Quality Metrics'
    
    name = models.CharField(max_length=200)
    dashboard_type = models.CharField(max_length=20, choices=DashboardType.choices)
    description = models.TextField(blank=True)
    
    # Access control
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_dashboards')
    is_public = models.BooleanField(default=True, help_text="Visible to all users")
    allowed_users = models.ManyToManyField(User, blank=True, related_name='accessible_dashboards')
    
    # Configuration
    config = models.JSONField(default=dict, help_text="Dashboard configuration and widget settings")
    refresh_interval = models.PositiveIntegerField(default=300, help_text="Auto-refresh interval in seconds")
    
    # Filters
    default_product_filter = models.ForeignKey(
        "products.Product", 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        help_text="Default product filter for this dashboard"
    )
    default_environment_filter = models.CharField(
        max_length=100, 
        blank=True, 
        help_text="Default environment filter (production, staging, etc.)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'dashboards'
        verbose_name = 'Dashboard'
        verbose_name_plural = 'Dashboards'
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.get_dashboard_type_display()})"


class DashboardWidget(models.Model):
    """Individual widgets on dashboards"""
    
    class WidgetType(models.TextChoices):
        METRIC_CARD = 'metric_card', 'Metric Card'
        CHART_LINE = 'chart_line', 'Line Chart'
        CHART_BAR = 'chart_bar', 'Bar Chart'
        CHART_PIE = 'chart_pie', 'Pie Chart'
        TABLE = 'table', 'Data Table'
        HEATMAP = 'heatmap', 'Heatmap'
        STATUS_GRID = 'status_grid', 'Status Grid'
    
    dashboard = models.ForeignKey(Dashboard, on_delete=models.CASCADE, related_name='widgets')
    widget_type = models.CharField(max_length=20, choices=WidgetType.choices)
    title = models.CharField(max_length=200)
    
    # Layout
    row = models.PositiveIntegerField(default=0)
    column = models.PositiveIntegerField(default=0)
    width = models.PositiveIntegerField(default=6, help_text="Width in grid columns (1-12)")
    height = models.PositiveIntegerField(default=4, help_text="Height in grid rows")
    
    # Data configuration
    data_source = models.CharField(max_length=100, help_text="Source of data (sentry, jira, sonarcloud, combined)")
    query_config = models.JSONField(default=dict, help_text="Query configuration for data retrieval")
    
    # Display configuration
    display_config = models.JSONField(default=dict, help_text="Widget display settings")
    
    # Refresh settings
    auto_refresh = models.BooleanField(default=True)
    cache_duration = models.PositiveIntegerField(default=60, help_text="Cache duration in seconds")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'dashboard_widgets'
        verbose_name = 'Dashboard Widget'
        verbose_name_plural = 'Dashboard Widgets'
        ordering = ['dashboard', 'row', 'column']
    
    def __str__(self):
        return f"{self.dashboard.name} - {self.title}"


# Import cache models
from .models_cache import DashboardSnapshot, DashboardRefreshLog