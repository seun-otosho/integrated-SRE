from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
import json


class JiraOrganization(models.Model):
    """Represents a JIRA Cloud instance/organization"""
    name = models.CharField(max_length=200, help_text="Display name for this JIRA instance")
    base_url = models.URLField(help_text="JIRA Cloud URL (e.g., https://yourcompany.atlassian.net)")
    username = models.EmailField(help_text="JIRA username (email address)")
    api_token = models.CharField(max_length=200, help_text="JIRA API token")
    
    # Sync settings
    sync_enabled = models.BooleanField(default=True, help_text="Enable automatic syncing")
    sync_interval_hours = models.PositiveIntegerField(default=6, help_text="Hours between syncs")
    last_sync = models.DateTimeField(null=True, blank=True)
    
    # Connection status
    connection_status = models.CharField(
        max_length=20,
        choices=[
            ('unknown', 'Unknown'),
            ('connected', 'Connected'),
            ('failed', 'Connection Failed'),
            ('unauthorized', 'Unauthorized'),
        ],
        default='unknown'
    )
    last_connection_test = models.DateTimeField(null=True, blank=True)
    connection_error = models.TextField(blank=True, help_text="Last connection error message")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'jira_organizations'
        verbose_name = 'JIRA Organization'
        verbose_name_plural = 'JIRA Organizations'
    
    def __str__(self):
        return f"{self.name} ({self.base_url})"
    
    def clean(self):
        """Validate JIRA Cloud URL format"""
        if self.base_url and not self.base_url.endswith('.atlassian.net'):
            if 'atlassian.net' not in self.base_url:
                raise ValidationError("JIRA Cloud URL should end with '.atlassian.net'")


class JiraProject(models.Model):
    """Represents a JIRA project"""
    jira_organization = models.ForeignKey(
        JiraOrganization, 
        on_delete=models.CASCADE, 
        related_name='projects'
    )
    product = models.ForeignKey(
        "products.Product", 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='jira_projects',
        help_text="Link this JIRA project to a business product"
    )
    
    # JIRA project details
    jira_key = models.CharField(max_length=50, help_text="JIRA project key (e.g., 'PROJ')")
    jira_id = models.CharField(max_length=50, help_text="JIRA project ID")
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    project_type = models.CharField(max_length=50, blank=True)  # software, business, service_desk
    
    # Project metadata
    lead_account_id = models.CharField(max_length=100, blank=True)
    lead_display_name = models.CharField(max_length=100, blank=True)
    category_name = models.CharField(max_length=100, blank=True)
    
    # URLs and navigation
    self_url = models.URLField(blank=True)
    avatar_url = models.URLField(blank=True)
    
    # Sync settings specific to this project
    sync_enabled = models.BooleanField(default=True)
    sync_issues = models.BooleanField(default=True, help_text="Sync issues for this project")
    max_issues_to_sync = models.PositiveIntegerField(
        default=1000, 
        help_text="Maximum number of issues to sync (for performance)"
    )
    
    # Statistics
    total_issues = models.PositiveIntegerField(default=0)
    open_issues = models.PositiveIntegerField(default=0)
    in_progress_issues = models.PositiveIntegerField(default=0)
    done_issues = models.PositiveIntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_issue_sync = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'jira_projects'
        verbose_name = 'JIRA Project'
        verbose_name_plural = 'JIRA Projects'
        unique_together = ['jira_organization', 'jira_key']
        ordering = ['name']
    
    def __str__(self):
        return f"{self.jira_key} - {self.name}"
    
    @property
    def jira_url(self):
        """Get the JIRA project URL"""
        if self.jira_organization.base_url:
            return f"{self.jira_organization.base_url}/browse/{self.jira_key}"
        return ""


class JiraIssue(models.Model):
    """Represents a JIRA issue/ticket"""
    
    class IssueType(models.TextChoices):
        BUG = 'Bug', 'Bug'
        TASK = 'Task', 'Task'
        STORY = 'Story', 'Story'
        EPIC = 'Epic', 'Epic'
        SUBTASK = 'Sub-task', 'Sub-task'
        IMPROVEMENT = 'Improvement', 'Improvement'
        NEW_FEATURE = 'New Feature', 'New Feature'
    
    class Priority(models.TextChoices):
        LOWEST = 'Lowest', 'Lowest'
        LOW = 'Low', 'Low'
        MEDIUM = 'Medium', 'Medium'
        HIGH = 'High', 'High'
        HIGHEST = 'Highest', 'Highest'
        CRITICAL = 'Critical', 'Critical'
    
    jira_project = models.ForeignKey(JiraProject, on_delete=models.CASCADE, related_name='issues')
    sentry_issue = models.ForeignKey(
        "sentry.SentryIssue", 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='jira_issues',
        help_text="Linked Sentry issue"
    )
    
    # JIRA issue details
    jira_key = models.CharField(max_length=100, help_text="JIRA issue key (e.g., 'PROJ-123')")
    jira_id = models.CharField(max_length=100, help_text="JIRA issue ID")
    summary = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    
    # Issue classification
    issue_type = models.CharField(max_length=50, choices=IssueType.choices, default=IssueType.BUG)
    status = models.CharField(max_length=50, help_text="Current JIRA status")
    status_category = models.CharField(
        max_length=20,
        choices=[
            ('new', 'To Do'),
            ('indeterminate', 'In Progress'),
            ('done', 'Done'),
        ],
        default='new'
    )
    priority = models.CharField(max_length=50, choices=Priority.choices, default=Priority.MEDIUM)
    
    # People
    assignee_account_id = models.CharField(max_length=100, blank=True)
    assignee_display_name = models.CharField(max_length=100, blank=True)
    assignee_email = models.EmailField(blank=True)
    
    reporter_account_id = models.CharField(max_length=100, blank=True)
    reporter_display_name = models.CharField(max_length=100, blank=True)
    reporter_email = models.EmailField(blank=True)
    
    # Timestamps
    jira_created = models.DateTimeField(help_text="When created in JIRA")
    jira_updated = models.DateTimeField(help_text="Last updated in JIRA")
    resolution_date = models.DateTimeField(null=True, blank=True)
    
    # URLs and metadata
    self_url = models.URLField(blank=True)
    labels = models.JSONField(default=list, blank=True, help_text="JIRA labels")
    components = models.JSONField(default=list, blank=True, help_text="JIRA components")
    fix_versions = models.JSONField(default=list, blank=True, help_text="Fix versions")
    
    # Sentry integration tracking
    created_from_sentry = models.BooleanField(default=False, help_text="Was this created from a Sentry issue?")
    sentry_sync_enabled = models.BooleanField(default=True, help_text="Enable bidirectional sync with Sentry")
    last_sentry_sync = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'jira_issues'
        verbose_name = 'JIRA Issue'
        verbose_name_plural = 'JIRA Issues'
        unique_together = ['jira_project', 'jira_key']
        ordering = ['-jira_updated']
    
    def __str__(self):
        return f"{self.jira_key} - {self.summary[:50]}"
    
    @property
    def jira_url(self):
        """Get the JIRA issue URL"""
        if self.jira_project.jira_organization.base_url:
            return f"{self.jira_project.jira_organization.base_url}/browse/{self.jira_key}"
        return ""
    
    @property
    def is_resolved(self):
        """Check if issue is resolved/done"""
        return self.status_category == 'done'
    
    @property
    def is_in_progress(self):
        """Check if issue is in progress"""
        return self.status_category == 'indeterminate'


class SentryJiraLink(models.Model):
    """Tracks the relationship between Sentry issues and JIRA tickets"""
    sentry_issue = models.ForeignKey("sentry.SentryIssue", on_delete=models.CASCADE)
    jira_issue = models.ForeignKey(JiraIssue, on_delete=models.CASCADE)
    
    # Link metadata
    link_type = models.CharField(
        max_length=20,
        choices=[
            ('manual', 'Manually Created'),
            ('auto', 'Automatically Created'),
            ('imported', 'Imported/Discovered'),
        ],
        default='manual'
    )
    
    # Sync settings
    sync_sentry_to_jira = models.BooleanField(
        default=True, 
        help_text="Sync Sentry issue changes to JIRA"
    )
    sync_jira_to_sentry = models.BooleanField(
        default=True, 
        help_text="Sync JIRA ticket changes to Sentry"
    )
    
    # Creation context
    created_by_user = models.ForeignKey(
        "users.User", 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        help_text="User who created this link"
    )
    creation_notes = models.TextField(blank=True, help_text="Notes about why this link was created")
    
    # Sync tracking
    last_sync_sentry_to_jira = models.DateTimeField(null=True, blank=True)
    last_sync_jira_to_sentry = models.DateTimeField(null=True, blank=True)
    sync_errors = models.JSONField(default=list, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'sentry_jira_links'
        verbose_name = 'Sentry-JIRA Link'
        verbose_name_plural = 'Sentry-JIRA Links'
        unique_together = ['sentry_issue', 'jira_issue']
    
    def __str__(self):
        return f"{self.sentry_issue.title[:30]} ↔ {self.jira_issue.jira_key}"


class JiraSyncLog(models.Model):
    """Log of JIRA sync operations"""
    
    class SyncType(models.TextChoices):
        FULL_SYNC = 'full', 'Full Sync'
        PROJECT_SYNC = 'project', 'Project Sync'
        ISSUE_SYNC = 'issue', 'Issue Sync'
        BIDIRECTIONAL_SYNC = 'bidirectional', 'Bidirectional Sync'
    
    class Status(models.TextChoices):
        STARTED = 'started', 'Started'
        SUCCESS = 'success', 'Success'
        FAILED = 'failed', 'Failed'
        PARTIAL = 'partial', 'Partial Success'
    
    jira_organization = models.ForeignKey(
        JiraOrganization, 
        on_delete=models.CASCADE, 
        related_name='sync_logs'
    )
    sync_type = models.CharField(max_length=20, choices=SyncType.choices, default=SyncType.FULL_SYNC)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.STARTED)
    
    # Sync results
    projects_synced = models.PositiveIntegerField(default=0)
    issues_synced = models.PositiveIntegerField(default=0)
    links_synced = models.PositiveIntegerField(default=0)
    
    # Error tracking
    error_message = models.TextField(blank=True)
    error_details = models.JSONField(default=dict, blank=True)
    
    # Performance tracking
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.FloatField(null=True, blank=True)
    
    class Meta:
        db_table = 'jira_sync_logs'
        verbose_name = 'JIRA Sync Log'
        verbose_name_plural = 'JIRA Sync Logs'
        ordering = ['-started_at']
    
    def __str__(self):
        return f"JIRA Sync {self.started_at.strftime('%Y-%m-%d %H:%M')} - {self.status}"