from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model
import json

User = get_user_model()


class SentryOrganization(models.Model):
    """Represents a Sentry organization"""
    sentry_id = models.CharField(max_length=100, unique=True)
    slug = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=200)
    avatar_url = models.URLField(blank=True, null=True)
    date_created = models.DateTimeField(auto_now_add=True)
    
    # API Configuration
    api_token = models.CharField(max_length=200, help_text="Sentry API token")
    api_url = models.URLField(default="https://sentry.io/api/0/", help_text="Sentry API base URL")
    
    # Sync settings
    sync_enabled = models.BooleanField(default=True)
    sync_interval_hours = models.PositiveIntegerField(default=3)
    last_sync = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'sentry_organizations'
        verbose_name = 'Sentry Organization'
        verbose_name_plural = 'Sentry Organizations'
    
    def __str__(self):
        return f"{self.name} ({self.slug})"


class SentryProject(models.Model):
    """Represents a Sentry project"""
    organization = models.ForeignKey(SentryOrganization, on_delete=models.CASCADE, related_name='projects')
    sentry_id = models.CharField(max_length=100)
    slug = models.CharField(max_length=100)
    name = models.CharField(max_length=200)
    platform = models.CharField(max_length=50, blank=True, null=True)
    status = models.CharField(max_length=50, default='active')
    
    # Project details
    date_created = models.DateTimeField()
    first_event = models.DateTimeField(null=True, blank=True)
    has_access = models.BooleanField(default=True)
    is_public = models.BooleanField(default=False)
    is_bookmarked = models.BooleanField(default=False)
    
    # Statistics
    total_issues = models.PositiveIntegerField(default=0)
    resolved_issues = models.PositiveIntegerField(default=0)
    unresolved_issues = models.PositiveIntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'sentry_projects'
        verbose_name = 'Sentry Project'
        verbose_name_plural = 'Sentry Projects'
        unique_together = ['organization', 'sentry_id']
    
    def __str__(self):
        return f"{self.organization.slug}/{self.slug}"


class SentryIssue(models.Model):
    """Represents a Sentry issue"""
    
    class Status(models.TextChoices):
        UNRESOLVED = 'unresolved', 'Unresolved'
        RESOLVED = 'resolved', 'Resolved'
        IGNORED = 'ignored', 'Ignored'
    
    class Level(models.TextChoices):
        DEBUG = 'debug', 'Debug'
        INFO = 'info', 'Info'
        WARNING = 'warning', 'Warning'
        ERROR = 'error', 'Error'
        FATAL = 'fatal', 'Fatal'
    
    project = models.ForeignKey(SentryProject, on_delete=models.CASCADE, related_name='issues')
    sentry_id = models.CharField(max_length=100)
    title = models.CharField(max_length=500)
    culprit = models.CharField(max_length=500, blank=True, null=True)
    permalink = models.URLField()
    
    # Issue details
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UNRESOLVED)
    level = models.CharField(max_length=20, choices=Level.choices, default=Level.ERROR)
    type = models.CharField(max_length=100, blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)
    
    # Statistics
    count = models.PositiveIntegerField(default=0)
    user_count = models.PositiveIntegerField(default=0)
    
    # Timestamps
    first_seen = models.DateTimeField()
    last_seen = models.DateTimeField()
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'sentry_issues'
        verbose_name = 'Sentry Issue'
        verbose_name_plural = 'Sentry Issues'
        unique_together = ['project', 'sentry_id']
        ordering = ['-last_seen']
    
    def __str__(self):
        return f"{self.title} ({self.status})"


class SentryEvent(models.Model):
    """Represents a Sentry event"""
    issue = models.ForeignKey(SentryIssue, on_delete=models.CASCADE, related_name='events')
    sentry_id = models.CharField(max_length=100)
    
    # Event details
    event_id = models.CharField(max_length=100)
    message = models.TextField(blank=True, null=True)
    platform = models.CharField(max_length=50, blank=True, null=True)
    environment = models.CharField(max_length=100, blank=True, null=True)
    release = models.CharField(max_length=200, blank=True, null=True)
    
    # User info
    user_id = models.CharField(max_length=100, blank=True, null=True)
    user_email = models.EmailField(blank=True, null=True)
    user_ip = models.GenericIPAddressField(blank=True, null=True)
    
    # Context data
    context = models.JSONField(default=dict, blank=True)
    tags = models.JSONField(default=dict, blank=True)
    extra = models.JSONField(default=dict, blank=True)
    
    date_created = models.DateTimeField()
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'sentry_events'
        verbose_name = 'Sentry Event'
        verbose_name_plural = 'Sentry Events'
        unique_together = ['issue', 'sentry_id']
        ordering = ['-date_created']
    
    def __str__(self):
        return f"Event {self.event_id} - {self.issue.title}"


class SentrySyncLog(models.Model):
    """Log of sync operations"""
    
    class Status(models.TextChoices):
        STARTED = 'started', 'Started'
        SUCCESS = 'success', 'Success'
        FAILED = 'failed', 'Failed'
        PARTIAL = 'partial', 'Partial Success'
    
    organization = models.ForeignKey(SentryOrganization, on_delete=models.CASCADE, related_name='sync_logs')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.STARTED)
    
    # Sync details
    projects_synced = models.PositiveIntegerField(default=0)
    issues_synced = models.PositiveIntegerField(default=0)
    events_synced = models.PositiveIntegerField(default=0)
    
    # Error tracking
    error_message = models.TextField(blank=True, null=True)
    error_details = models.JSONField(default=dict, blank=True)
    
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.FloatField(null=True, blank=True)
    
    class Meta:
        db_table = 'sentry_sync_logs'
        verbose_name = 'Sentry Sync Log'
        verbose_name_plural = 'Sentry Sync Logs'
        ordering = ['-started_at']
    
    def __str__(self):
        return f"Sync {self.started_at.strftime('%Y-%m-%d %H:%M')} - {self.status}"