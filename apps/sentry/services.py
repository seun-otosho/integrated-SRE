import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from django.utils import timezone as django_timezone
from django.db import transaction

from .models import (
    SentryOrganization, SentryProject, SentryIssue, 
    SentryEvent, SentrySyncLog
)
from .client import SentryAPIClient, parse_datetime

logger = logging.getLogger(__name__)


class SentrySyncService:
    """Service for syncing data from Sentry API"""
    
    def __init__(self, organization: SentryOrganization):
        self.organization = organization
        self.client = SentryAPIClient(
            api_token=organization.api_token,
            api_url=organization.api_url
        )
        self.sync_log = None
    
    def sync_all(self) -> SentrySyncLog:
        """Sync all data for the organization"""
        # Create sync log
        self.sync_log = SentrySyncLog.objects.create(
            organization=self.organization,
            status=SentrySyncLog.Status.STARTED
        )
        
        try:
            with transaction.atomic():
                # Sync organization details
                self._sync_organization()
                
                # Sync projects
                projects_count = self._sync_projects()
                
                # Sync issues and events for each project
                issues_count = 0
                events_count = 0
                
                for project in self.organization.projects.all():
                    project_issues, project_events = self._sync_project_data(project)
                    issues_count += project_issues
                    events_count += project_events
                
                # Update sync log
                self.sync_log.projects_synced = projects_count
                self.sync_log.issues_synced = issues_count
                self.sync_log.events_synced = events_count
                self.sync_log.status = SentrySyncLog.Status.SUCCESS
                
                # Update organization last sync
                self.organization.last_sync = django_timezone.now()
                self.organization.save()
                
        except Exception as e:
            logger.error(f"Sync failed for organization {self.organization.slug}: {str(e)}")
            self.sync_log.status = SentrySyncLog.Status.FAILED
            self.sync_log.error_message = str(e)
        
        finally:
            self.sync_log.completed_at = django_timezone.now()
            if self.sync_log.started_at:
                duration = (self.sync_log.completed_at - self.sync_log.started_at).total_seconds()
                self.sync_log.duration_seconds = duration
            self.sync_log.save()
        
        return self.sync_log
    
    def _sync_organization(self):
        """Sync organization details"""
        success, org_data = self.client.get_organization(self.organization.slug)
        if success:
            self.organization.name = org_data.get('name', self.organization.name)
            self.organization.sentry_id = org_data.get('id', self.organization.sentry_id)
            self.organization.avatar_url = org_data.get('avatar', {}).get('avatarUrl')
            if org_data.get('dateCreated'):
                self.organization.date_created = parse_datetime(org_data['dateCreated'])
            self.organization.save()
    
    def _sync_projects(self) -> int:
        """Sync projects for the organization"""
        success, projects_data = self.client.get_projects(self.organization.slug)
        if not success:
            logger.warning(f"Failed to fetch projects for {self.organization.slug}")
            return 0
        
        synced_count = 0
        for project_data in projects_data:
            try:
                project, created = SentryProject.objects.update_or_create(
                    organization=self.organization,
                    sentry_id=project_data['id'],
                    defaults={
                        'slug': project_data['slug'],
                        'name': project_data['name'],
                        'platform': project_data.get('platform'),
                        'status': project_data.get('status', 'active'),
                        'date_created': parse_datetime(project_data['dateCreated']),
                        'first_event': parse_datetime(project_data['firstEvent']) if project_data.get('firstEvent') else None,
                        'has_access': project_data.get('hasAccess', True),
                        'is_public': project_data.get('isPublic', False),
                        'is_bookmarked': project_data.get('isBookmarked', False),
                    }
                )
                synced_count += 1
                
                if created:
                    logger.info(f"Created new project: {project}")
                
            except Exception as e:
                logger.error(f"Failed to sync project {project_data.get('slug')}: {str(e)}")
        
        return synced_count
    
    def _sync_project_data(self, project: SentryProject) -> tuple[int, int]:
        """Sync issues and events for a project"""
        issues_count = 0
        events_count = 0
        
        # Sync issues
        success, issues_data = self.client.get_issues(
            self.organization.slug, 
            project.slug,
            limit=500  # Adjust as needed
        )
        
        if success:
            for issue_data in issues_data:
                try:
                    issue, created = SentryIssue.objects.update_or_create(
                        project=project,
                        sentry_id=issue_data['id'],
                        defaults={
                            'title': issue_data.get('title', ''),
                            'culprit': issue_data.get('culprit'),
                            'permalink': issue_data.get('permalink', ''),
                            'status': issue_data.get('status', 'unresolved'),
                            'level': issue_data.get('level', 'error'),
                            'type': issue_data.get('type'),
                            'metadata': issue_data.get('metadata', {}),
                            'count': issue_data.get('count', 0),
                            'user_count': issue_data.get('userCount', 0),
                            'first_seen': parse_datetime(issue_data['firstSeen']),
                            'last_seen': parse_datetime(issue_data['lastSeen']),
                        }
                    )
                    issues_count += 1
                    
                    # Sync recent events for this issue (limit to avoid overwhelming)
                    if created or issue.events.count() < 10:
                        issue_events = self._sync_issue_events(issue, limit=10)
                        events_count += issue_events
                    
                except Exception as e:
                    logger.error(f"Failed to sync issue {issue_data.get('id')}: {str(e)}")
        
        # Update project statistics
        project.total_issues = project.issues.count()
        project.resolved_issues = project.issues.filter(status='resolved').count()
        project.unresolved_issues = project.issues.filter(status='unresolved').count()
        project.save()
        
        return issues_count, events_count
    
    def _sync_issue_events(self, issue: SentryIssue, limit: int = 10) -> int:
        """Sync events for an issue"""
        success, events_data = self.client.get_issue_events(issue.sentry_id, limit=limit)
        if not success:
            return 0
        
        events_count = 0
        for event_data in events_data:
            try:
                event, created = SentryEvent.objects.update_or_create(
                    issue=issue,
                    sentry_id=event_data['id'],
                    defaults={
                        'event_id': event_data.get('eventID', ''),
                        'message': event_data.get('message', ''),
                        'platform': event_data.get('platform'),
                        'environment': event_data.get('environment'),
                        'release': event_data.get('release', {}).get('version') if event_data.get('release') else None,
                        'user_id': event_data.get('user', {}).get('id') if event_data.get('user') else None,
                        'user_email': event_data.get('user', {}).get('email') if event_data.get('user') else None,
                        'user_ip': event_data.get('user', {}).get('ip_address') if event_data.get('user') else None,
                        'context': event_data.get('context', {}),
                        'tags': {tag['key']: tag['value'] for tag in event_data.get('tags', [])},
                        'extra': event_data.get('extra', {}),
                        'date_created': parse_datetime(event_data['dateCreated']),
                    }
                )
                events_count += 1
                
            except Exception as e:
                logger.error(f"Failed to sync event {event_data.get('id')}: {str(e)}")
        
        return events_count


def sync_organization(organization_id: int) -> SentrySyncLog:
    """Sync a specific organization"""
    try:
        organization = SentryOrganization.objects.get(id=organization_id, sync_enabled=True)
        service = SentrySyncService(organization)
        return service.sync_all()
    except SentryOrganization.DoesNotExist:
        logger.error(f"Organization with ID {organization_id} not found or sync disabled")
        return None


def sync_all_organizations() -> List[SentrySyncLog]:
    """Sync all enabled organizations"""
    sync_logs = []
    organizations = SentryOrganization.objects.filter(sync_enabled=True)
    
    for org in organizations:
        try:
            service = SentrySyncService(org)
            sync_log = service.sync_all()
            sync_logs.append(sync_log)
        except Exception as e:
            logger.error(f"Failed to sync organization {org.slug}: {str(e)}")
    
    return sync_logs