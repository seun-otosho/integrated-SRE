import logging
import re
from typing import Dict, List, Optional, Tuple
from django.utils import timezone as django_timezone
from django.db import transaction

logger = logging.getLogger(__name__)


class SentryJiraLinkingService:
    """Service for automatically linking Sentry issues to JIRA tickets based on annotations"""
    
    def __init__(self):
        pass
    
    def extract_jira_tickets_from_annotations(self, annotations: List[Dict]) -> List[Dict]:
        """Extract JIRA ticket information from Sentry annotations"""
        jira_tickets = []
        
        for annotation in annotations:
            if not isinstance(annotation, dict):
                continue
                
            url = annotation.get('url', '')
            display_name = annotation.get('displayName', '')
            
            # Check if this looks like a JIRA ticket
            jira_info = self._parse_jira_annotation(url, display_name)
            if jira_info:
                jira_tickets.append(jira_info)
        
        return jira_tickets
    
    def _parse_jira_annotation(self, url: str, display_name: str) -> Optional[Dict]:
        """Parse a single annotation to extract JIRA ticket information"""
        if not url:
            return None
        
        # Common JIRA URL patterns
        patterns = [
            # Standard Atlassian Cloud: https://company.atlassian.net/browse/PROJ-123
            r'https?://([^.]+)\.atlassian\.net/browse/([A-Z][A-Z0-9]+-\d+)',
            # On-premise JIRA: https://jira.company.com/browse/PROJ-123  
            r'https?://[^/]*jira[^/]*/browse/([A-Z][A-Z0-9]+-\d+)',
            # Direct ticket pattern in display name
            r'^([A-Z][A-Z0-9]+-\d+)$'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                if len(match.groups()) == 2:
                    # Pattern with domain and ticket
                    domain = match.group(1)
                    ticket_key = match.group(2)
                    base_url = f"https://{domain}.atlassian.net"
                else:
                    # Pattern with just ticket
                    ticket_key = match.group(1)
                    # Try to extract base URL from the full URL
                    base_match = re.search(r'(https?://[^/]+)', url)
                    base_url = base_match.group(1) if base_match else None
                
                return {
                    'ticket_key': ticket_key,
                    'base_url': base_url,
                    'full_url': url,
                    'display_name': display_name or ticket_key
                }
        
        # Check display name for ticket pattern if URL didn't match
        if display_name:
            match = re.search(r'^([A-Z][A-Z0-9]+-\d+)$', display_name)
            if match:
                return {
                    'ticket_key': match.group(1),
                    'base_url': None,
                    'full_url': url,
                    'display_name': display_name
                }
        
        return None
    
    def link_sentry_issue_to_jira_tickets(self, sentry_issue, force_update: bool = False) -> Dict:
        """Link a Sentry issue to JIRA tickets based on its annotations"""
        from apps.sentry.client import SentryAPIClient
        from apps.jira.models import JiraIssue, JiraOrganization
        from apps.jira.services import SentryJiraLinkService
        
        results = {
            'success': False,
            'links_created': 0,
            'links_found': 0,
            'errors': [],
            'jira_tickets': []
        }
        
        try:
            # Get fresh data from Sentry API to get annotations
            org = sentry_issue.project.organization
            client = SentryAPIClient(org.api_token)
            
            success, issue_data = client._make_request(f'issues/{sentry_issue.sentry_id}/')
            if not success:
                results['errors'].append(f"Failed to fetch issue from Sentry API: {issue_data}")
                return results
            
            # Extract JIRA tickets from annotations
            annotations = issue_data.get('annotations', [])
            jira_tickets = self.extract_jira_tickets_from_annotations(annotations)
            
            if not jira_tickets:
                results['errors'].append("No JIRA tickets found in Sentry annotations")
                return results
            
            results['jira_tickets'] = jira_tickets
            results['links_found'] = len(jira_tickets)
            
            # Try to find and link each JIRA ticket
            for jira_ticket_info in jira_tickets:
                ticket_key = jira_ticket_info['ticket_key']
                
                try:
                    # Find the JIRA issue in our database
                    jira_issue = JiraIssue.objects.filter(jira_key=ticket_key).first()
                    
                    if not jira_issue:
                        # Try to fetch and create the missing JIRA ticket
                        fetch_result = self._fetch_and_create_missing_jira_ticket(
                            ticket_key, jira_ticket_info, sentry_issue
                        )
                        
                        if fetch_result['success']:
                            jira_issue = fetch_result['jira_issue']
                            results['errors'].append(f"✅ Auto-fetched missing JIRA ticket {ticket_key}")
                        else:
                            results['errors'].append(f"❌ JIRA ticket {ticket_key} not found and could not be fetched: {fetch_result['error']}")
                            continue
                    
                    # Check if link already exists
                    from apps.jira.models import SentryJiraLink
                    existing_link = SentryJiraLink.objects.filter(
                        sentry_issue=sentry_issue,
                        jira_issue=jira_issue
                    ).first()
                    
                    if existing_link and not force_update:
                        results['errors'].append(f"Link to {ticket_key} already exists")
                        continue
                    
                    # Create the link
                    if not existing_link:
                        link = SentryJiraLink.objects.create(
                            sentry_issue=sentry_issue,
                            jira_issue=jira_issue,
                            link_type='auto',  # Automatically created from annotations
                            creation_notes=f"Automatically linked from Sentry annotation: {jira_ticket_info['full_url']}",
                            sync_sentry_to_jira=True,
                            sync_jira_to_sentry=True
                        )
                        results['links_created'] += 1
                        logger.info(f"Created automatic link: {sentry_issue} -> {jira_issue}")
                    
                except Exception as e:
                    results['errors'].append(f"Error linking to {ticket_key}: {str(e)}")
            
            results['success'] = results['links_created'] > 0 or len(results['errors']) == 0
            
        except Exception as e:
            results['errors'].append(f"Unexpected error: {str(e)}")
            logger.error(f"Error in automatic JIRA linking for {sentry_issue}: {str(e)}")
        
        return results
    
    def scan_and_link_all_sentry_issues(self, organization=None, limit: int = None, 
                                       skip_linked: bool = False, offset: int = 0) -> Dict:
        """Scan all Sentry issues and automatically link them to JIRA tickets"""
        from apps.sentry.models import SentryIssue
        
        summary = {
            'issues_processed': 0,
            'issues_skipped': 0,
            'issues_with_jira_links': 0,
            'total_links_created': 0,
            'errors': [],
            'details': []
        }
        
        # Get issues to process
        queryset = SentryIssue.objects.select_related('project', 'project__organization')
        
        if organization:
            queryset = queryset.filter(project__organization=organization)
        
        # Filter out issues that already have JIRA links if requested
        if skip_linked:
            from apps.jira.models import SentryJiraLink
            linked_issue_ids = SentryJiraLink.objects.values_list('sentry_issue_id', flat=True)
            queryset = queryset.exclude(id__in=linked_issue_ids)
        
        # Apply offset
        if offset > 0:
            queryset = queryset[offset:]
        
        # Apply limit after offset
        if limit:
            queryset = queryset[:limit]
        
        for issue in queryset:
            try:
                # Double-check for existing links if skip_linked is enabled
                if skip_linked:
                    from apps.jira.models import SentryJiraLink
                    if SentryJiraLink.objects.filter(sentry_issue=issue).exists():
                        summary['issues_skipped'] += 1
                        continue
                
                summary['issues_processed'] += 1
                
                # Try to link this issue
                result = self.link_sentry_issue_to_jira_tickets(issue)
                
                if result['links_found'] > 0:
                    summary['issues_with_jira_links'] += 1
                    summary['total_links_created'] += result['links_created']
                    
                    summary['details'].append({
                        'issue': str(issue),
                        'jira_tickets': [t['ticket_key'] for t in result['jira_tickets']],
                        'links_created': result['links_created'],
                        'errors': result['errors']
                    })
                
                # Collect errors
                if result['errors']:
                    for error in result['errors']:
                        summary['errors'].append(f"{issue.title[:50]}: {error}")
                # print(f"Processed \n\t{issue}: \n\t\t{result}\n","_"*88)
            except Exception as e:
                summary['errors'].append(f"Failed to process {issue}: {str(e)}")
        
        return summary
    
    def get_linkable_issues_preview(self, organization=None, limit: int = 10, 
                                   skip_linked: bool = False, offset: int = 0) -> List[Dict]:
        """Preview which issues have JIRA annotations and could be linked"""
        from apps.sentry.models import SentryIssue
        from apps.sentry.client import SentryAPIClient
        
        linkable_issues = []
        
        # Get issues to check
        queryset = SentryIssue.objects.select_related('project', 'project__organization')
        
        if organization:
            queryset = queryset.filter(project__organization=organization)
        
        # Filter out issues that already have JIRA links if requested
        if skip_linked:
            from apps.jira.models import SentryJiraLink
            linked_issue_ids = SentryJiraLink.objects.values_list('sentry_issue_id', flat=True)
            queryset = queryset.exclude(id__in=linked_issue_ids)
        
        # Apply offset
        if offset > 0:
            queryset = queryset[offset:]
        
        # Apply limit after offset
        for issue in queryset[:limit]:
            try:
                # Get annotations from Sentry API
                org = issue.project.organization
                client = SentryAPIClient(org.api_token)
                
                success, issue_data = client._make_request(f'issues/{issue.sentry_id}/')
                if success:
                    annotations = issue_data.get('annotations', [])
                    jira_tickets = self.extract_jira_tickets_from_annotations(annotations)
                    
                    if jira_tickets:
                        linkable_issues.append({
                            'sentry_issue': issue,
                            'jira_tickets': jira_tickets,
                            'annotations': annotations
                        })
                
            except Exception as e:
                logger.error(f"Error checking {issue}: {str(e)}")
        
        return linkable_issues
    
    def _fetch_and_create_missing_jira_ticket(self, ticket_key: str, jira_ticket_info: Dict, 
                                            sentry_issue) -> Dict:
        """Fetch and create a missing JIRA ticket from the JIRA API"""
        from apps.jira.models import JiraOrganization, JiraProject, JiraIssue
        from apps.jira.services import JiraSyncService
        from apps.jira.client import JiraAPIClient
        
        result = {
            'success': False,
            'jira_issue': None,
            'error': None,
            'created_project': False
        }
        
        try:
            # Extract project key from ticket key (e.g., 'CAIMS2-4389' -> 'CAIMS2')
            project_key = ticket_key.split('-')[0]
            
            # Try to find the JIRA organization that might have this ticket
            base_url = jira_ticket_info.get('base_url')
            jira_org = None
            
            if base_url:
                # Try to find organization by base URL
                jira_org = JiraOrganization.objects.filter(
                    base_url__icontains=base_url.replace('https://', '').replace('http://', '')
                ).first()
            
            if not jira_org:
                # Try to find any organization that might have this project
                existing_project = JiraProject.objects.filter(jira_key=project_key).first()
                if existing_project:
                    jira_org = existing_project.jira_organization
            
            if not jira_org:
                # Use the first available JIRA organization as fallback
                jira_org = JiraOrganization.objects.filter(sync_enabled=True).first()
            
            if not jira_org:
                result['error'] = "No JIRA organization configured"
                return result
            
            # Create JIRA client
            client = JiraAPIClient(jira_org.base_url, jira_org.username, jira_org.api_token)
            
            # Test connection first
            success, message = client.test_connection()
            if not success:
                result['error'] = f"JIRA connection failed: {message}"
                return result
            
            # Try to fetch the specific issue
            success, issue_data = client.get_issue(ticket_key)
            if not success:
                result['error'] = f"Could not fetch JIRA issue {ticket_key}: {issue_data.get('message', 'Unknown error')}"
                return result
            
            # Check if we need to create the project first
            jira_project = JiraProject.objects.filter(
                jira_organization=jira_org,
                jira_key=project_key
            ).first()
            
            if not jira_project:
                # Fetch project details and create it
                project_result = self._fetch_and_create_jira_project(client, jira_org, project_key)
                if project_result['success']:
                    jira_project = project_result['jira_project']
                    result['created_project'] = True
                else:
                    result['error'] = f"Could not create JIRA project {project_key}: {project_result['error']}"
                    return result
            
            # Create the JIRA issue using the sync service
            sync_service = JiraSyncService(jira_org)
            created_issue = sync_service._sync_single_issue(jira_project, issue_data)
            
            if created_issue:
                # Get the created issue
                jira_issue = JiraIssue.objects.filter(
                    jira_project=jira_project,
                    jira_key=ticket_key
                ).first()
                
                if jira_issue:
                    result['success'] = True
                    result['jira_issue'] = jira_issue
                    logger.info(f"Successfully fetched and created JIRA issue {ticket_key}")
                else:
                    result['error'] = "Issue created but not found in database"
            else:
                result['error'] = "Failed to create JIRA issue in database"
            
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"Error fetching JIRA ticket {ticket_key}: {str(e)}")
        
        return result
    
    def _fetch_and_create_jira_project(self, client: 'JiraAPIClient', jira_org, project_key: str) -> Dict:
        """Fetch and create a missing JIRA project"""
        from apps.jira.models import JiraProject
        
        result = {
            'success': False,
            'jira_project': None,
            'error': None
        }
        
        try:
            # Try to get project details
            success, project_data = client.get_project(project_key)
            if not success:
                result['error'] = f"Could not fetch project details: {project_data.get('message', 'Unknown error')}"
                return result
            
            # Create the project
            jira_project = JiraProject.objects.create(
                jira_organization=jira_org,
                jira_key=project_data.get('key', project_key),
                name=project_data.get('name', project_key),
                description=project_data.get('description', ''),
                project_type=project_data.get('projectTypeKey', 'software'),
                lead_account_id=project_data.get('lead', {}).get('accountId', ''),
                lead_display_name=project_data.get('lead', {}).get('displayName', ''),
                # Set sync enabled for this auto-discovered project
                sync_enabled=True,
                sync_issues=True
            )
            
            result['success'] = True
            result['jira_project'] = jira_project
            logger.info(f"Successfully created JIRA project {project_key}")
            
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"Error creating JIRA project {project_key}: {str(e)}")
        
        return result