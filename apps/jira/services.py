import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from django.utils import timezone as django_timezone
from django.db import transaction

from .models import (
    JiraOrganization, JiraProject, JiraIssue, 
    SentryJiraLink, JiraSyncLog
)
from .client import JiraAPIClient, parse_jira_datetime, extract_plain_text_from_adf

logger = logging.getLogger(__name__)


class JiraSyncService:
    """Service for syncing data from JIRA API"""
    
    def __init__(self, jira_organization: JiraOrganization):
        self.organization = jira_organization
        self.client = JiraAPIClient(
            base_url=jira_organization.base_url,
            username=jira_organization.username,
            api_token=jira_organization.api_token
        )
        self.sync_log = None
    
    def sync_all(self) -> JiraSyncLog:
        """Sync all data for the JIRA organization"""
        # Create sync log
        self.sync_log = JiraSyncLog.objects.create(
            jira_organization=self.organization,
            sync_type=JiraSyncLog.SyncType.FULL_SYNC,
            status=JiraSyncLog.Status.STARTED
        )
        
        try:
            with transaction.atomic():
                # Test connection first
                self._test_connection()
                
                # Sync projects
                projects_count = self._sync_projects()
                
                # Sync issues for each enabled project
                issues_count = 0
                for project in self.organization.projects.filter(sync_enabled=True, sync_issues=True):
                    project_issues = self._sync_project_issues(project)
                    issues_count += project_issues
                
                # Update sync log
                self.sync_log.projects_synced = projects_count
                self.sync_log.issues_synced = issues_count
                self.sync_log.status = JiraSyncLog.Status.SUCCESS
                
                # Update organization last sync
                self.organization.last_sync = django_timezone.now()
                self.organization.connection_status = 'connected'
                self.organization.save()
                
        except Exception as e:
            logger.error(f"JIRA sync failed for organization {self.organization.name}: {str(e)}")
            self.sync_log.status = JiraSyncLog.Status.FAILED
            self.sync_log.error_message = str(e)
            
            # Update connection status
            self.organization.connection_status = 'failed'
            self.organization.connection_error = str(e)
            self.organization.save()
        
        finally:
            self.sync_log.completed_at = django_timezone.now()
            if self.sync_log.started_at:
                duration = (self.sync_log.completed_at - self.sync_log.started_at).total_seconds()
                self.sync_log.duration_seconds = duration
            self.sync_log.save()
        
        return self.sync_log
    
    def _test_connection(self):
        """Test JIRA API connection"""
        success, message = self.client.test_connection()
        self.organization.last_connection_test = django_timezone.now()
        
        if success:
            self.organization.connection_status = 'connected'
            self.organization.connection_error = ''
        else:
            self.organization.connection_status = 'failed'
            self.organization.connection_error = message
            raise Exception(f"JIRA connection failed: {message}")
        
        self.organization.save()
    
    def _sync_projects(self) -> int:
        """Sync projects for the organization"""
        success, projects_data = self.client.get_projects()
        if not success:
            logger.warning(f"Failed to fetch projects for {self.organization.name}")
            return 0
        
        synced_count = 0
        for project_data in projects_data:
            try:
                # Extract project information
                project_key = project_data.get('key', '')
                project_id = project_data.get('id', '')
                name = project_data.get('name', '')
                
                if not project_key or not project_id:
                    logger.warning(f"Skipping project with missing key or ID: {project_data}")
                    continue
                
                # Extract lead information
                lead = project_data.get('lead', {})
                lead_account_id = lead.get('accountId', '') if lead else ''
                lead_display_name = lead.get('displayName', '') if lead else ''
                
                # Extract URLs
                self_url = project_data.get('self', '')
                avatar_urls = project_data.get('avatarUrls', {})
                avatar_url = avatar_urls.get('48x48', '') if avatar_urls else ''
                
                project, created = JiraProject.objects.update_or_create(
                    jira_organization=self.organization,
                    jira_key=project_key,
                    defaults={
                        'jira_id': project_id,
                        'name': name,
                        'description': project_data.get('description', ''),
                        'project_type': project_data.get('projectTypeKey', ''),
                        'lead_account_id': lead_account_id,
                        'lead_display_name': lead_display_name,
                        'category_name': project_data.get('projectCategory', {}).get('name', '') if project_data.get('projectCategory') else '',
                        'self_url': self_url,
                        'avatar_url': avatar_url,
                    }
                )
                synced_count += 1
                
                if created:
                    logger.info(f"Created new JIRA project: {project}")
                
            except Exception as e:
                logger.error(f"Failed to sync JIRA project {project_data.get('key')}: {str(e)}")
        
        return synced_count
    
    def _sync_project_issues(self, project: JiraProject) -> int:
        """Sync issues for a specific project"""
        synced_count = 0
        start_at = 0
        max_results = 100
        
        try:
            while True:
                # Get batch of issues
                success, issues_data = self.client.get_project_issues(
                    project.jira_key,
                    max_results=max_results,
                    start_at=start_at
                )
                
                if not success:
                    logger.warning(f"Failed to fetch issues for project {project.jira_key}")
                    break
                
                issues = issues_data.get('issues', [])
                if not issues:
                    break
                
                # Process each issue
                for issue_data in issues:
                    try:
                        if self._sync_single_issue(project, issue_data):
                            synced_count += 1
                    except Exception as e:
                        logger.error(f"Failed to sync issue {issue_data.get('key')}: {str(e)}")
                
                # Check if we've reached the limit or end
                total = issues_data.get('total', 0)
                if start_at + max_results >= total or synced_count >= project.max_issues_to_sync:
                    break
                
                start_at += max_results
            
            # Update project statistics
            self._update_project_statistics(project)
            project.last_issue_sync = django_timezone.now()
            project.save()
            
        except Exception as e:
            logger.error(f"Error syncing issues for project {project.jira_key}: {str(e)}")
        
        return synced_count
    
    def _sync_single_issue(self, project: JiraProject, issue_data: Dict) -> bool:
        """Sync a single JIRA issue"""
        try:
            # Extract basic issue information
            jira_key = issue_data.get('key', '')
            jira_id = issue_data.get('id', '')
            fields = issue_data.get('fields', {})
            
            if not jira_key or not jira_id:
                return False
            
            # Extract issue details
            summary = fields.get('summary', '')
            description_adf = fields.get('description')
            description = extract_plain_text_from_adf(description_adf) if description_adf else ''
            
            # Extract issue type and status
            issue_type_data = fields.get('issuetype', {})
            issue_type = issue_type_data.get('name', 'Task')
            
            status_data = fields.get('status', {})
            status = status_data.get('name', 'Open')
            status_category_data = status_data.get('statusCategory', {})
            status_category = status_category_data.get('key', 'new')
            
            # Extract priority
            priority_data = fields.get('priority', {})
            priority = priority_data.get('name', 'Medium')
            
            # Extract people
            assignee = fields.get('assignee', {})
            assignee_account_id = assignee.get('accountId', '') if assignee else ''
            assignee_display_name = assignee.get('displayName', '') if assignee else ''
            assignee_email = assignee.get('emailAddress', '') if assignee else ''
            
            reporter = fields.get('reporter', {})
            reporter_account_id = reporter.get('accountId', '') if reporter else ''
            reporter_display_name = reporter.get('displayName', '') if reporter else ''
            reporter_email = reporter.get('emailAddress', '') if reporter else ''
            
            # Extract timestamps
            jira_created = parse_jira_datetime(fields.get('created', ''))
            jira_updated = parse_jira_datetime(fields.get('updated', ''))
            resolution_date = None
            if fields.get('resolutiondate'):
                resolution_date = parse_jira_datetime(fields['resolutiondate'])
            
            # Extract labels and components
            labels = [label for label in fields.get('labels', [])]
            components = [comp.get('name', '') for comp in fields.get('components', [])]
            fix_versions = [version.get('name', '') for version in fields.get('fixVersions', [])]
            
            # Create or update the issue
            issue, created = JiraIssue.objects.update_or_create(
                jira_project=project,
                jira_key=jira_key,
                defaults={
                    'jira_id': jira_id,
                    'summary': summary,
                    'description': description,
                    'issue_type': issue_type,
                    'status': status,
                    'status_category': status_category,
                    'priority': priority,
                    'assignee_account_id': assignee_account_id,
                    'assignee_display_name': assignee_display_name,
                    'assignee_email': assignee_email,
                    'reporter_account_id': reporter_account_id,
                    'reporter_display_name': reporter_display_name,
                    'reporter_email': reporter_email,
                    'jira_created': jira_created,
                    'jira_updated': jira_updated,
                    'resolution_date': resolution_date,
                    'self_url': issue_data.get('self', ''),
                    'labels': labels,
                    'components': components,
                    'fix_versions': fix_versions,
                }
            )
            
            if created:
                logger.debug(f"Created new JIRA issue: {issue}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error processing JIRA issue data: {str(e)}")
            return False
    
    def _update_project_statistics(self, project: JiraProject):
        """Update project issue statistics"""
        project.total_issues = project.issues.count()
        project.open_issues = project.issues.filter(status_category='new').count()
        project.in_progress_issues = project.issues.filter(status_category='indeterminate').count()
        project.done_issues = project.issues.filter(status_category='done').count()


class SentryJiraLinkService:
    """Service for managing Sentry-JIRA links and bidirectional sync"""
    
    def __init__(self, jira_organization: JiraOrganization = None):
        self.organization = jira_organization
        if jira_organization:
            self.client = JiraAPIClient(
                base_url=jira_organization.base_url,
                username=jira_organization.username,
                api_token=jira_organization.api_token
            )
    
    def create_jira_issue_from_sentry(self, sentry_issue, jira_project: JiraProject, 
                                    issue_type: str = "Bug", priority: str = "Medium",
                                    assignee_account_id: str = None, user=None) -> Tuple[bool, JiraIssue, str]:
        """Create a JIRA issue from a Sentry issue"""
        try:
            # Initialize client if not already done
            if not hasattr(self, 'client'):
                self.client = JiraAPIClient(
                    base_url=jira_project.jira_organization.base_url,
                    username=jira_project.jira_organization.username,
                    api_token=jira_project.jira_organization.api_token
                )
            
            # Build issue summary and description
            summary = f"[Sentry] {sentry_issue.title}"
            
            description_parts = [
                f"Sentry Issue: {sentry_issue.title}",
                f"Level: {sentry_issue.level.upper()}",
                f"Status: {sentry_issue.status}",
                f"First Seen: {sentry_issue.first_seen.strftime('%Y-%m-%d %H:%M')}",
                f"Last Seen: {sentry_issue.last_seen.strftime('%Y-%m-%d %H:%M')}",
                f"Event Count: {sentry_issue.count}",
                f"User Count: {sentry_issue.user_count}",
                "",
                f"Sentry Link: {sentry_issue.permalink}",
            ]
            
            if sentry_issue.culprit:
                description_parts.insert(-2, f"Culprit: {sentry_issue.culprit}")
            
            description = "\n".join(description_parts)
            
            # Create labels
            labels = ["sentry", f"level-{sentry_issue.level}"]
            if sentry_issue.project.product:
                labels.append(f"product-{sentry_issue.project.product.name.lower().replace(' ', '-')}")
            
            # Create JIRA issue
            success, jira_response = self.client.create_issue(
                project_key=jira_project.jira_key,
                issue_type=issue_type,
                summary=summary,
                description=description,
                priority=priority,
                assignee_account_id=assignee_account_id,
                labels=labels
            )
            
            if not success:
                error_msg = jira_response.get('message', 'Unknown error creating JIRA issue')
                return False, None, error_msg
            
            # Get the created issue details
            jira_key = jira_response.get('key')
            if not jira_key:
                return False, None, "No issue key returned from JIRA"
            
            # Fetch the full issue details to create our local record
            success, issue_data = self.client.get_issue(jira_key)
            if not success:
                return False, None, "Failed to fetch created issue details"
            
            # Create local JIRA issue record
            sync_service = JiraSyncService(jira_project.jira_organization)
            sync_service._sync_single_issue(jira_project, issue_data)
            
            # Get the created JiraIssue object
            jira_issue = JiraIssue.objects.get(jira_project=jira_project, jira_key=jira_key)
            jira_issue.created_from_sentry = True
            jira_issue.save()
            
            # Create the link
            link = SentryJiraLink.objects.create(
                sentry_issue=sentry_issue,
                jira_issue=jira_issue,
                link_type='manual',
                created_by_user=user,
                creation_notes=f"Created from Sentry issue: {sentry_issue.title}",
                sync_sentry_to_jira=True,
                sync_jira_to_sentry=True
            )
            
            return True, jira_issue, f"Successfully created JIRA issue {jira_key}"
            
        except Exception as e:
            logger.error(f"Error creating JIRA issue from Sentry: {str(e)}")
            return False, None, str(e)
    
    def sync_jira_to_sentry(self, link: SentryJiraLink) -> Tuple[bool, str]:
        """Sync JIRA issue status to Sentry issue"""
        try:
            if not link.sync_jira_to_sentry:
                return True, "Sync disabled for this link"
            
            jira_issue = link.jira_issue
            sentry_issue = link.sentry_issue
            
            # Map JIRA status to Sentry status
            if jira_issue.is_resolved:
                if sentry_issue.status != 'resolved':
                    sentry_issue.status = 'resolved'
                    sentry_issue.save()
                    link.last_sync_jira_to_sentry = django_timezone.now()
                    link.save()
                    return True, f"Marked Sentry issue as resolved (JIRA: {jira_issue.status})"
            
            return True, "No sync needed"
            
        except Exception as e:
            error_msg = f"Error syncing JIRA to Sentry: {str(e)}"
            logger.error(error_msg)
            
            # Log the error in the link
            link.sync_errors.append({
                'timestamp': django_timezone.now().isoformat(),
                'direction': 'jira_to_sentry',
                'error': error_msg
            })
            link.save()
            
            return False, error_msg
    
    def sync_all_links(self) -> Dict[str, int]:
        """Sync all active Sentry-JIRA links"""
        results = {'success': 0, 'failed': 0, 'skipped': 0}
        
        # Get all links that have sync enabled
        active_links = SentryJiraLink.objects.filter(
            sync_jira_to_sentry=True
        ).select_related('sentry_issue', 'jira_issue', 'jira_issue__jira_project__jira_organization')
        
        for link in active_links:
            success, message = self.sync_jira_to_sentry(link)
            if success:
                results['success'] += 1
            else:
                results['failed'] += 1
        
        return results


# Convenience functions
def sync_jira_organization(organization_id: int) -> JiraSyncLog:
    """Sync a specific JIRA organization"""
    try:
        organization = JiraOrganization.objects.get(id=organization_id, sync_enabled=True)
        service = JiraSyncService(organization)
        return service.sync_all()
    except JiraOrganization.DoesNotExist:
        logger.error(f"JIRA organization with ID {organization_id} not found or sync disabled")
        return None


def sync_all_jira_organizations() -> List[JiraSyncLog]:
    """Sync all enabled JIRA organizations"""
    sync_logs = []
    organizations = JiraOrganization.objects.filter(sync_enabled=True)
    
    for org in organizations:
        try:
            service = JiraSyncService(org)
            sync_log = service.sync_all()
            sync_logs.append(sync_log)
        except Exception as e:
            logger.error(f"Failed to sync JIRA organization {org.name}: {str(e)}")
    
    return sync_logs