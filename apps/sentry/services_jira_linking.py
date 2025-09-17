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
                        results['errors'].append(f"JIRA ticket {ticket_key} not found in database - may need to sync JIRA first")
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
    
    def scan_and_link_all_sentry_issues(self, organization=None, limit: int = None) -> Dict:
        """Scan all Sentry issues and automatically link them to JIRA tickets"""
        from apps.sentry.models import SentryIssue
        
        summary = {
            'issues_processed': 0,
            'issues_with_jira_links': 0,
            'total_links_created': 0,
            'errors': [],
            'details': []
        }
        
        # Get issues to process
        queryset = SentryIssue.objects.select_related('project', 'project__organization')
        
        if organization:
            queryset = queryset.filter(project__organization=organization)
        
        if limit:
            queryset = queryset[:limit]
        
        for issue in queryset:
            try:
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
                
            except Exception as e:
                summary['errors'].append(f"Failed to process {issue}: {str(e)}")
        
        return summary
    
    def get_linkable_issues_preview(self, organization=None, limit: int = 10) -> List[Dict]:
        """Preview which issues have JIRA annotations and could be linked"""
        from apps.sentry.models import SentryIssue
        from apps.sentry.client import SentryAPIClient
        
        linkable_issues = []
        
        # Get issues to check
        queryset = SentryIssue.objects.select_related('project', 'project__organization')
        
        if organization:
            queryset = queryset.filter(project__organization=organization)
        
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