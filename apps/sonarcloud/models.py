from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
import json

User = get_user_model()


class SonarCloudOrganization(models.Model):
    """Represents a SonarCloud organization"""
    name = models.CharField(max_length=200, help_text="Display name for this SonarCloud organization")
    organization_key = models.CharField(
        max_length=100, 
        unique=True, 
        help_text="SonarCloud organization key (from URL)"
    )
    api_token = models.CharField(max_length=200, help_text="SonarCloud API token")
    
    # SonarCloud organization details
    description = models.TextField(blank=True)
    url = models.URLField(blank=True, help_text="Organization URL on SonarCloud")
    avatar_url = models.URLField(blank=True)
    
    # Sync settings
    sync_enabled = models.BooleanField(default=True, help_text="Enable automatic syncing")
    sync_interval_hours = models.PositiveIntegerField(default=12, help_text="Hours between syncs")
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
        db_table = 'sonarcloud_organizations'
        verbose_name = 'SonarCloud Organization'
        verbose_name_plural = 'SonarCloud Organizations'
    
    def __str__(self):
        return f"{self.name} ({self.organization_key})"
    
    @property
    def sonarcloud_url(self):
        """Get the SonarCloud organization URL"""
        return f"https://sonarcloud.io/organizations/{self.organization_key}"


class SonarCloudProject(models.Model):
    """Represents a SonarCloud project"""
    sonarcloud_organization = models.ForeignKey(
        SonarCloudOrganization, 
        on_delete=models.CASCADE, 
        related_name='projects'
    )
    product = models.ForeignKey(
        "products.Product", 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='sonarcloud_projects',
        help_text="Link this SonarCloud project to a business product"
    )
    
    # SonarCloud project details
    project_key = models.CharField(max_length=200, help_text="SonarCloud project key")
    name = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    visibility = models.CharField(max_length=20, default='public')  # public, private
    
    # Project metadata
    language = models.CharField(max_length=50, blank=True, help_text="Primary programming language")
    main_branch = models.CharField(max_length=100, default='main', help_text="Main branch name")
    
    # Current quality metrics (latest analysis)
    quality_gate_status = models.CharField(
        max_length=20,
        choices=[
            ('OK', 'Passed'),
            ('ERROR', 'Failed'),
            ('WARN', 'Warning'),
            ('NONE', 'No Quality Gate'),
        ],
        default='NONE'
    )
    
    # Quality ratings (A-E scale)
    reliability_rating = models.CharField(max_length=1, blank=True, help_text="A (best) to E (worst)")
    security_rating = models.CharField(max_length=1, blank=True, help_text="A (best) to E (worst)")
    maintainability_rating = models.CharField(max_length=1, blank=True, help_text="A (best) to E (worst)")
    
    # Key metrics
    lines_of_code = models.PositiveIntegerField(default=0)
    coverage = models.FloatField(null=True, blank=True, help_text="Test coverage percentage")
    duplication = models.FloatField(null=True, blank=True, help_text="Code duplication percentage")
    technical_debt = models.PositiveIntegerField(default=0, help_text="Technical debt in minutes")
    
    # Issue counts
    bugs = models.PositiveIntegerField(default=0)
    vulnerabilities = models.PositiveIntegerField(default=0)
    security_hotspots = models.PositiveIntegerField(default=0)
    code_smells = models.PositiveIntegerField(default=0)
    
    # Sync settings
    sync_enabled = models.BooleanField(default=True)
    sync_measures = models.BooleanField(default=True, help_text="Sync quality measures")
    sync_issues = models.BooleanField(default=True, help_text="Sync code issues")
    
    # Timestamps
    last_analysis = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_measure_sync = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'sonarcloud_projects'
        verbose_name = 'SonarCloud Project'
        verbose_name_plural = 'SonarCloud Projects'
        unique_together = ['sonarcloud_organization', 'project_key']
        ordering = ['name']
    
    def __str__(self):
        return f"{self.project_key} - {self.name}"
    
    @property
    def sonarcloud_url(self):
        """Get the SonarCloud project URL"""
        org_key = self.sonarcloud_organization.organization_key
        return f"https://sonarcloud.io/project/overview?id={self.project_key}"
    
    @property
    def overall_quality_score(self):
        """Calculate an overall quality score (0-100)"""
        ratings = [self.reliability_rating, self.security_rating, self.maintainability_rating]
        valid_ratings = [r for r in ratings if r and r in 'ABCDE']
        
        if not valid_ratings:
            return None
        
        # Convert A=100, B=80, C=60, D=40, E=20
        rating_scores = {'A': 100, 'B': 80, 'C': 60, 'D': 40, 'E': 20}
        scores = [rating_scores[r] for r in valid_ratings]
        return sum(scores) / len(scores)
    
    @property
    def quality_status_color(self):
        """Get color for quality gate status"""
        colors = {
            'OK': 'green',
            'ERROR': 'red', 
            'WARN': 'orange',
            'NONE': 'gray'
        }
        return colors.get(self.quality_gate_status, 'gray')


class QualityMeasurement(models.Model):
    """Historical quality measurements for a project"""
    project = models.ForeignKey(SonarCloudProject, on_delete=models.CASCADE, related_name='measurements')
    
    # Measurement metadata
    analysis_date = models.DateTimeField(help_text="When this analysis was performed")
    branch = models.CharField(max_length=100, default='main')
    
    # Quality gate
    quality_gate_status = models.CharField(max_length=20)
    
    # Ratings
    reliability_rating = models.CharField(max_length=1, blank=True)
    security_rating = models.CharField(max_length=1, blank=True)
    maintainability_rating = models.CharField(max_length=1, blank=True)
    
    # Core metrics
    lines_of_code = models.PositiveIntegerField(default=0)
    coverage = models.FloatField(null=True, blank=True)
    duplication = models.FloatField(null=True, blank=True)
    technical_debt = models.PositiveIntegerField(default=0)
    
    # Issue counts
    bugs = models.PositiveIntegerField(default=0)
    vulnerabilities = models.PositiveIntegerField(default=0)
    security_hotspots = models.PositiveIntegerField(default=0)
    code_smells = models.PositiveIntegerField(default=0)
    
    # Additional metrics
    complexity = models.PositiveIntegerField(default=0)
    cognitive_complexity = models.PositiveIntegerField(default=0)
    classes = models.PositiveIntegerField(default=0)
    functions = models.PositiveIntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'sonarcloud_measurements'
        verbose_name = 'Quality Measurement'
        verbose_name_plural = 'Quality Measurements'
        unique_together = ['project', 'analysis_date', 'branch']
        ordering = ['-analysis_date']
    
    def __str__(self):
        return f"{self.project.project_key} - {self.analysis_date.strftime('%Y-%m-%d')}"


class CodeIssue(models.Model):
    """Represents a code issue (bug, vulnerability, code smell)"""
    
    class IssueType(models.TextChoices):
        BUG = 'BUG', 'Bug'
        VULNERABILITY = 'VULNERABILITY', 'Vulnerability'
        CODE_SMELL = 'CODE_SMELL', 'Code Smell'
        SECURITY_HOTSPOT = 'SECURITY_HOTSPOT', 'Security Hotspot'
    
    class Severity(models.TextChoices):
        BLOCKER = 'BLOCKER', 'Blocker'
        CRITICAL = 'CRITICAL', 'Critical'
        MAJOR = 'MAJOR', 'Major'
        MINOR = 'MINOR', 'Minor'
        INFO = 'INFO', 'Info'
    
    project = models.ForeignKey(SonarCloudProject, on_delete=models.CASCADE, related_name='issues')
    sonarcloud_key = models.CharField(max_length=200, unique=True, help_text="SonarCloud issue key")
    
    # Issue details
    rule = models.CharField(max_length=200, help_text="SonarCloud rule identifier")
    severity = models.CharField(max_length=20, choices=Severity.choices)
    type = models.CharField(max_length=20, choices=IssueType.choices)
    
    # Issue content
    message = models.TextField(help_text="Issue description")
    component = models.CharField(max_length=500, help_text="File path")
    line = models.PositiveIntegerField(null=True, blank=True, help_text="Line number")
    
    # Status
    status = models.CharField(max_length=20, default='OPEN')
    resolution = models.CharField(max_length=20, blank=True)
    
    # Effort
    effort = models.CharField(max_length=20, blank=True, help_text="Effort to fix (e.g., '5min')")
    debt = models.PositiveIntegerField(default=0, help_text="Technical debt in minutes")
    
    # Timestamps
    creation_date = models.DateTimeField()
    update_date = models.DateTimeField()
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'sonarcloud_issues'
        verbose_name = 'Code Issue'
        verbose_name_plural = 'Code Issues'
        ordering = ['-creation_date']
    
    def __str__(self):
        return f"{self.sonarcloud_key} - {self.message[:50]}"
    
    @property
    def severity_color(self):
        """Get color for severity level"""
        colors = {
            'BLOCKER': '#d04437',    # Red
            'CRITICAL': '#ff5722',   # Orange-red
            'MAJOR': '#ff9800',      # Orange
            'MINOR': '#ffeb3b',      # Yellow
            'INFO': '#2196f3'        # Blue
        }
        return colors.get(self.severity, '#666666')


# Cross-system integration models
class SentrySonarLink(models.Model):
    """Links Sentry projects to SonarCloud projects for quality analysis"""
    sentry_project = models.ForeignKey("sentry.SentryProject", on_delete=models.CASCADE)
    sonarcloud_project = models.ForeignKey(SonarCloudProject, on_delete=models.CASCADE)
    
    # Link metadata
    link_type = models.CharField(
        max_length=20,
        choices=[
            ('manual', 'Manually Created'),
            ('auto', 'Automatically Detected'),
            ('imported', 'Imported/Discovered'),
        ],
        default='manual'
    )
    
    # Quality settings
    block_releases_on_quality_gate = models.BooleanField(
        default=False,
        help_text="Block Sentry releases when SonarCloud quality gate fails"
    )
    minimum_coverage_threshold = models.FloatField(
        null=True, blank=True,
        help_text="Minimum test coverage required for releases (percentage)"
    )
    maximum_debt_threshold = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Maximum technical debt allowed for releases (minutes)"
    )
    
    # Link management
    created_by_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    creation_notes = models.TextField(blank=True, help_text="Notes about why this link was created")
    
    # Quality sync tracking
    last_quality_sync = models.DateTimeField(null=True, blank=True)
    quality_sync_errors = models.JSONField(default=list, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'sentry_sonar_links'
        verbose_name = 'Sentry-SonarCloud Link'
        verbose_name_plural = 'Sentry-SonarCloud Links'
        unique_together = ['sentry_project', 'sonarcloud_project']
    
    def __str__(self):
        return f"{self.sentry_project} ↔ {self.sonarcloud_project}"
    
    @property
    def current_quality_status(self):
        """Get current quality status for release gating"""
        if not self.sonarcloud_project:
            return {'status': 'unknown', 'message': 'No SonarCloud project linked'}
        
        project = self.sonarcloud_project
        issues = []
        
        # Check quality gate
        if self.block_releases_on_quality_gate and project.quality_gate_status == 'ERROR':
            issues.append('Quality gate failed')
        
        # Check coverage threshold
        if (self.minimum_coverage_threshold and 
            project.coverage is not None and 
            project.coverage < self.minimum_coverage_threshold):
            issues.append(f'Coverage {project.coverage:.1f}% below threshold {self.minimum_coverage_threshold}%')
        
        # Check debt threshold
        if (self.maximum_debt_threshold and 
            project.technical_debt > self.maximum_debt_threshold):
            debt_hours = project.technical_debt / 60
            threshold_hours = self.maximum_debt_threshold / 60
            issues.append(f'Technical debt {debt_hours:.1f}h exceeds threshold {threshold_hours:.1f}h')
        
        if issues:
            return {'status': 'blocked', 'issues': issues}
        else:
            return {'status': 'ok', 'message': 'All quality checks passed'}


class JiraSonarLink(models.Model):
    """Links JIRA projects to SonarCloud projects for quality-based issue creation"""
    jira_project = models.ForeignKey("jira.JiraProject", on_delete=models.CASCADE)
    sonarcloud_project = models.ForeignKey(SonarCloudProject, on_delete=models.CASCADE)
    
    # Link metadata
    link_type = models.CharField(
        max_length=20,
        choices=[
            ('manual', 'Manually Created'),
            ('auto', 'Automatically Detected'),
            ('imported', 'Imported/Discovered'),
        ],
        default='manual'
    )
    
    # Automation settings
    auto_create_security_tickets = models.BooleanField(
        default=False,
        help_text="Automatically create JIRA tickets for security vulnerabilities"
    )
    auto_create_debt_tickets = models.BooleanField(
        default=False,
        help_text="Automatically create JIRA tickets for technical debt above threshold"
    )
    auto_create_coverage_tickets = models.BooleanField(
        default=False,
        help_text="Automatically create JIRA tickets when coverage drops significantly"
    )
    
    # Thresholds for automation
    security_severity_threshold = models.CharField(
        max_length=20,
        choices=CodeIssue.Severity.choices,
        default=CodeIssue.Severity.MAJOR,
        help_text="Minimum severity for auto-creating security tickets"
    )
    debt_threshold_hours = models.PositiveIntegerField(
        default=8,
        help_text="Create tickets for debt above this threshold (hours)"
    )
    coverage_drop_threshold = models.FloatField(
        default=5.0,
        help_text="Create tickets when coverage drops by this percentage"
    )
    
    # JIRA ticket settings
    default_issue_type = models.CharField(max_length=50, default='Task')
    default_priority = models.CharField(max_length=50, default='Medium')
    security_issue_type = models.CharField(max_length=50, default='Bug')
    security_priority = models.CharField(max_length=50, default='High')
    
    # Link management
    created_by_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    creation_notes = models.TextField(blank=True)
    
    # Sync tracking
    last_ticket_creation_sync = models.DateTimeField(null=True, blank=True)
    tickets_created_count = models.PositiveIntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'jira_sonar_links'
        verbose_name = 'JIRA-SonarCloud Link'
        verbose_name_plural = 'JIRA-SonarCloud Links'
        unique_together = ['jira_project', 'sonarcloud_project']
    
    def __str__(self):
        return f"{self.jira_project} ↔ {self.sonarcloud_project}"


class QualityIssueTicket(models.Model):
    """Tracks JIRA tickets created from SonarCloud quality issues"""
    sonarcloud_issue = models.ForeignKey(CodeIssue, on_delete=models.CASCADE, related_name='jira_tickets')
    jira_issue = models.ForeignKey("jira.JiraIssue", on_delete=models.CASCADE, related_name='quality_issues')
    jira_sonar_link = models.ForeignKey(JiraSonarLink, on_delete=models.CASCADE)
    
    # Creation context
    creation_reason = models.CharField(
        max_length=50,
        choices=[
            ('security', 'Security Vulnerability'),
            ('debt', 'Technical Debt'),
            ('coverage', 'Coverage Drop'),
            ('manual', 'Manual Creation'),
        ]
    )
    
    # Status tracking
    auto_created = models.BooleanField(default=False)
    sync_enabled = models.BooleanField(default=True, help_text="Keep ticket in sync with SonarCloud issue")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'quality_issue_tickets'
        verbose_name = 'Quality Issue Ticket'
        verbose_name_plural = 'Quality Issue Tickets'
        unique_together = ['sonarcloud_issue', 'jira_issue']
    
    def __str__(self):
        return f"{self.jira_issue.jira_key} ← {self.sonarcloud_issue.sonarcloud_key}"


class SonarSyncLog(models.Model):
    """Log of sync operations with SonarCloud"""
    
    class Status(models.TextChoices):
        STARTED = 'started', 'Started'
        SUCCESS = 'success', 'Success'
        FAILED = 'failed', 'Failed'
        PARTIAL = 'partial', 'Partial Success'
    
    class SyncType(models.TextChoices):
        FULL_SYNC = 'full', 'Full Sync'
        PROJECTS_ONLY = 'projects', 'Projects Only'
        MEASURES_ONLY = 'measures', 'Measures Only'
        ISSUES_ONLY = 'issues', 'Issues Only'
    
    sonarcloud_organization = models.ForeignKey(
        SonarCloudOrganization, 
        on_delete=models.CASCADE, 
        related_name='sync_logs'
    )
    sync_type = models.CharField(max_length=20, choices=SyncType.choices, default=SyncType.FULL_SYNC)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.STARTED)
    
    # Sync results
    projects_synced = models.PositiveIntegerField(default=0)
    measures_synced = models.PositiveIntegerField(default=0)
    issues_synced = models.PositiveIntegerField(default=0)
    
    # Error tracking
    error_message = models.TextField(blank=True, null=True)
    error_details = models.JSONField(default=dict, blank=True)
    
    # Timing
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.FloatField(null=True, blank=True)
    
    class Meta:
        db_table = 'sonarcloud_sync_logs'
        verbose_name = 'SonarCloud Sync Log'
        verbose_name_plural = 'SonarCloud Sync Logs'
        ordering = ['-started_at']
    
    def __str__(self):
        return f"SonarCloud Sync {self.started_at.strftime('%Y-%m-%d %H:%M')} - {self.status}"