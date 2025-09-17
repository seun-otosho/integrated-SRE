import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from django.utils import timezone as django_timezone
from django.db import transaction

from .models import (
    SonarCloudOrganization, SonarCloudProject, QualityMeasurement,
    CodeIssue, SonarSyncLog
)
from .client import (
    SonarCloudAPIClient, parse_sonar_datetime, convert_rating_to_letter,
    convert_technical_debt
)

logger = logging.getLogger(__name__)


class SonarCloudSyncService:
    """Service for syncing data from SonarCloud API"""
    
    def __init__(self, sonarcloud_organization: SonarCloudOrganization):
        self.organization = sonarcloud_organization
        self.client = SonarCloudAPIClient(api_token=sonarcloud_organization.api_token)
        self.sync_log = None
    
    def sync_all(self) -> SonarSyncLog:
        """Sync all data for the SonarCloud organization"""
        # Create sync log
        self.sync_log = SonarSyncLog.objects.create(
            sonarcloud_organization=self.organization,
            sync_type=SonarSyncLog.SyncType.FULL_SYNC,
            status=SonarSyncLog.Status.STARTED
        )
        
        try:
            with transaction.atomic():
                # Test connection first
                self._test_connection()
                
                # Sync projects
                projects_count = self._sync_projects()
                
                # Sync measures for each enabled project
                measures_count = 0
                issues_count = 0
                
                for project in self.organization.projects.filter(sync_enabled=True):
                    if project.sync_measures:
                        if self._sync_project_measures(project):
                            measures_count += 1
                    
                    if project.sync_issues:
                        project_issues = self._sync_project_issues(project)
                        issues_count += project_issues
                
                # Update sync log
                self.sync_log.projects_synced = projects_count
                self.sync_log.measures_synced = measures_count
                self.sync_log.issues_synced = issues_count
                self.sync_log.status = SonarSyncLog.Status.SUCCESS
                
                # Update organization last sync
                self.organization.last_sync = django_timezone.now()
                self.organization.connection_status = 'connected'
                self.organization.save()
                
        except Exception as e:
            logger.error(f"SonarCloud sync failed for organization {self.organization.name}: {str(e)}")
            self.sync_log.status = SonarSyncLog.Status.FAILED
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
        """Test SonarCloud API connection"""
        success, message = self.client.test_connection()
        self.organization.last_connection_test = django_timezone.now()
        
        if success:
            self.organization.connection_status = 'connected'
            self.organization.connection_error = ''
        else:
            self.organization.connection_status = 'failed'
            self.organization.connection_error = message
            raise Exception(f"SonarCloud connection failed: {message}")
        
        self.organization.save()
    
    def _sync_projects(self) -> int:
        """Sync projects for the organization"""
        success, projects_data = self.client.get_projects(self.organization.organization_key)
        if not success:
            logger.warning(f"Failed to fetch projects for {self.organization.name}")
            return 0
        
        synced_count = 0
        for project_data in projects_data:
            try:
                # Extract project information
                project_key = project_data.get('key', '')
                name = project_data.get('name', '')
                
                if not project_key or not name:
                    logger.warning(f"Skipping project with missing key or name: {project_data}")
                    continue
                
                # Get additional project details if available
                qualifier = project_data.get('qualifier', '')
                if qualifier != 'TRK':  # TRK = project, skip others like modules
                    continue
                
                project, created = SonarCloudProject.objects.update_or_create(
                    sonarcloud_organization=self.organization,
                    project_key=project_key,
                    defaults={
                        'name': name,
                        'description': project_data.get('description', ''),
                        'visibility': project_data.get('visibility', 'public'),
                        'language': project_data.get('language', ''),
                    }
                )
                synced_count += 1
                
                if created:
                    logger.info(f"Created new SonarCloud project: {project}")
                
            except Exception as e:
                logger.error(f"Failed to sync SonarCloud project {project_data.get('key')}: {str(e)}")
        
        return synced_count
    
    def _sync_project_measures(self, project: SonarCloudProject) -> bool:
        """Sync quality measures for a specific project"""
        try:
            success, measures_data = self.client.get_project_measures(project.project_key)
            if not success:
                logger.warning(f"Failed to fetch measures for project {project.project_key}")
                return False
            
            measures = measures_data.get('measures', {})
            component = measures_data.get('component', {})
            
            # Update project with latest measures
            project.quality_gate_status = measures.get('alert_status', 'NONE')
            
            # Convert ratings
            project.reliability_rating = convert_rating_to_letter(measures.get('reliability_rating', ''))
            project.security_rating = convert_rating_to_letter(measures.get('security_rating', ''))
            project.maintainability_rating = convert_rating_to_letter(measures.get('sqale_rating', ''))
            
            # Numeric measures
            project.lines_of_code = int(float(measures.get('ncloc', 0)))
            project.coverage = float(measures.get('coverage', 0)) if measures.get('coverage') else None
            project.duplication = float(measures.get('duplicated_lines_density', 0)) if measures.get('duplicated_lines_density') else None
            project.technical_debt = convert_technical_debt(measures.get('sqale_index', '0'))
            
            # Issue counts
            project.bugs = int(float(measures.get('bugs', 0)))
            project.vulnerabilities = int(float(measures.get('vulnerabilities', 0)))
            project.security_hotspots = int(float(measures.get('security_hotspots', 0)))
            project.code_smells = int(float(measures.get('code_smells', 0)))
            
            # Get last analysis date if available
            last_analysis = component.get('analysisDate')
            if last_analysis:
                project.last_analysis = parse_sonar_datetime(last_analysis)
            
            project.last_measure_sync = django_timezone.now()
            project.save()
            
            # Create historical measurement record
            QualityMeasurement.objects.create(
                project=project,
                analysis_date=project.last_analysis or django_timezone.now(),
                quality_gate_status=project.quality_gate_status,
                reliability_rating=project.reliability_rating,
                security_rating=project.security_rating,
                maintainability_rating=project.maintainability_rating,
                lines_of_code=project.lines_of_code,
                coverage=project.coverage,
                duplication=project.duplication,
                technical_debt=project.technical_debt,
                bugs=project.bugs,
                vulnerabilities=project.vulnerabilities,
                security_hotspots=project.security_hotspots,
                code_smells=project.code_smells,
                complexity=int(float(measures.get('complexity', 0))),
                cognitive_complexity=int(float(measures.get('cognitive_complexity', 0))),
                classes=int(float(measures.get('classes', 0))),
                functions=int(float(measures.get('functions', 0))),
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error syncing measures for project {project.project_key}: {str(e)}")
            return False
    
    def _sync_project_issues(self, project: SonarCloudProject) -> int:
        """Sync issues for a specific project"""
        synced_count = 0
        
        try:
            # Get regular issues (bugs, vulnerabilities, code smells)
            success, issues_data = self.client.get_project_issues(project.project_key)
            if success:
                for issue_data in issues_data:
                    try:
                        if self._sync_single_issue(project, issue_data):
                            synced_count += 1
                    except Exception as e:
                        logger.error(f"Failed to sync issue {issue_data.get('key')}: {str(e)}")
            
            # Get security hotspots
            success, hotspots_data = self.client.get_security_hotspots(project.project_key)
            if success:
                for hotspot_data in hotspots_data:
                    try:
                        if self._sync_single_hotspot(project, hotspot_data):
                            synced_count += 1
                    except Exception as e:
                        logger.error(f"Failed to sync hotspot {hotspot_data.get('key')}: {str(e)}")
            
        except Exception as e:
            logger.error(f"Error syncing issues for project {project.project_key}: {str(e)}")
        
        return synced_count
    
    def _sync_single_issue(self, project: SonarCloudProject, issue_data: Dict) -> bool:
        """Sync a single code issue"""
        try:
            sonarcloud_key = issue_data.get('key', '')
            if not sonarcloud_key:
                return False
            
            # Extract issue details
            rule = issue_data.get('rule', '')
            severity = issue_data.get('severity', 'INFO')
            issue_type = issue_data.get('type', 'CODE_SMELL')
            message = issue_data.get('message', '')
            component = issue_data.get('component', '')
            
            # Get line number from text range
            text_range = issue_data.get('textRange', {})
            line = text_range.get('startLine') if text_range else None
            
            # Status and resolution
            status = issue_data.get('status', 'OPEN')
            resolution = issue_data.get('resolution', '')
            
            # Effort and debt
            effort = issue_data.get('effort', '')
            debt = convert_technical_debt(effort)
            
            # Timestamps
            creation_date = parse_sonar_datetime(issue_data.get('creationDate', ''))
            update_date = parse_sonar_datetime(issue_data.get('updateDate', ''))
            
            # Create or update the issue
            issue, created = CodeIssue.objects.update_or_create(
                sonarcloud_key=sonarcloud_key,
                defaults={
                    'project': project,
                    'rule': rule,
                    'severity': severity,
                    'type': issue_type,
                    'message': message,
                    'component': component,
                    'line': line,
                    'status': status,
                    'resolution': resolution,
                    'effort': effort,
                    'debt': debt,
                    'creation_date': creation_date,
                    'update_date': update_date,
                }
            )
            
            if created:
                logger.debug(f"Created new code issue: {issue}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error processing issue data: {str(e)}")
            return False
    
    def _sync_single_hotspot(self, project: SonarCloudProject, hotspot_data: Dict) -> bool:
        """Sync a single security hotspot"""
        try:
            sonarcloud_key = hotspot_data.get('key', '')
            if not sonarcloud_key:
                return False
            
            # Treat hotspots as security issues
            rule = hotspot_data.get('rule', '')
            severity = hotspot_data.get('vulnerabilityProbability', 'INFO').upper()
            message = hotspot_data.get('message', '')
            component = hotspot_data.get('component', '')
            
            # Get line number
            text_range = hotspot_data.get('textRange', {})
            line = text_range.get('startLine') if text_range else None
            
            # Status
            status = hotspot_data.get('status', 'TO_REVIEW')
            
            # Timestamps
            creation_date = parse_sonar_datetime(hotspot_data.get('creationDate', ''))
            update_date = parse_sonar_datetime(hotspot_data.get('updateDate', ''))
            
            # Create or update the hotspot as an issue
            issue, created = CodeIssue.objects.update_or_create(
                sonarcloud_key=sonarcloud_key,
                defaults={
                    'project': project,
                    'rule': rule,
                    'severity': severity,
                    'type': CodeIssue.IssueType.SECURITY_HOTSPOT,
                    'message': message,
                    'component': component,
                    'line': line,
                    'status': status,
                    'resolution': '',
                    'effort': '',
                    'debt': 0,
                    'creation_date': creation_date,
                    'update_date': update_date,
                }
            )
            
            if created:
                logger.debug(f"Created new security hotspot: {issue}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error processing hotspot data: {str(e)}")
            return False


# Convenience functions
def sync_sonarcloud_organization(organization_id: int) -> SonarSyncLog:
    """Sync a specific SonarCloud organization"""
    try:
        organization = SonarCloudOrganization.objects.get(id=organization_id, sync_enabled=True)
        service = SonarCloudSyncService(organization)
        return service.sync_all()
    except SonarCloudOrganization.DoesNotExist:
        logger.error(f"SonarCloud organization with ID {organization_id} not found or sync disabled")
        return None


def sync_all_sonarcloud_organizations() -> List[SonarSyncLog]:
    """Sync all enabled SonarCloud organizations"""
    sync_logs = []
    organizations = SonarCloudOrganization.objects.filter(sync_enabled=True)
    
    for org in organizations:
        try:
            service = SonarCloudSyncService(org)
            sync_log = service.sync_all()
            sync_logs.append(sync_log)
        except Exception as e:
            logger.error(f"Failed to sync SonarCloud organization {org.name}: {str(e)}")
    
    return sync_logs