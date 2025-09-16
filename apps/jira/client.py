import requests
import base64
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from django.conf import settings

logger = logging.getLogger(__name__)


class JiraAPIClient:
    """Client for interacting with JIRA Cloud REST API"""
    
    def __init__(self, base_url: str, username: str, api_token: str):
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.api_token = api_token
        self.api_base = f"{self.base_url}/rest/api/3"
        
        # Create session with authentication
        self.session = requests.Session()
        auth_string = f"{username}:{api_token}"
        auth_bytes = auth_string.encode('ascii')
        auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
        
        self.session.headers.update({
            'Authorization': f'Basic {auth_b64}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
    
    def _make_request(self, endpoint: str, method: str = 'GET', params: dict = None, data: dict = None) -> Tuple[bool, dict]:
        """Make a request to JIRA API"""
        url = f"{self.api_base}/{endpoint.lstrip('/')}"
        
        try:
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=data,
                timeout=30
            )
            
            if response.status_code in [200, 201]:
                try:
                    return True, response.json()
                except json.JSONDecodeError:
                    return True, {}
            else:
                logger.error(f"JIRA API error {response.status_code}: {response.text}")
                return False, {
                    'error': f"HTTP {response.status_code}",
                    'message': response.text,
                    'status_code': response.status_code
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"JIRA API request failed: {str(e)}")
            return False, {'error': 'Request failed', 'message': str(e)}
    
    def test_connection(self) -> Tuple[bool, str]:
        """Test the JIRA API connection"""
        success, data = self._make_request('myself')
        if success:
            user_name = data.get('displayName', 'Unknown')
            return True, f"Connected successfully as {user_name}"
        else:
            error_msg = data.get('message', 'Unknown error')
            return False, f"Connection failed: {error_msg}"
    
    def get_projects(self, expand: str = "lead,description") -> Tuple[bool, List[Dict]]:
        """Get list of JIRA projects"""
        params = {'expand': expand}
        success, data = self._make_request('project', params=params)
        if success:
            return True, data if isinstance(data, list) else []
        return False, []
    
    def get_project(self, project_key: str, expand: str = "lead,description") -> Tuple[bool, Dict]:
        """Get specific project details"""
        params = {'expand': expand}
        return self._make_request(f'project/{project_key}', params=params)
    
    def get_project_issues(self, project_key: str, max_results: int = 100, start_at: int = 0, 
                          jql_filter: str = None) -> Tuple[bool, Dict]:
        """Get issues for a project"""
        # Build JQL query
        base_jql = f'project = {project_key}'
        if jql_filter:
            jql = f'{base_jql} AND ({jql_filter})'
        else:
            jql = base_jql
        
        params = {
            'jql': jql,
            'maxResults': max_results,
            'startAt': start_at,
            'expand': 'names,schema',
            'fields': [
                'summary', 'description', 'issuetype', 'status', 'priority',
                'assignee', 'reporter', 'created', 'updated', 'resolutiondate',
                'labels', 'components', 'fixVersions'
            ]
        }
        
        return self._make_request('search', params=params)
    
    def get_issue(self, issue_key: str) -> Tuple[bool, Dict]:
        """Get specific issue details"""
        fields = [
            'summary', 'description', 'issuetype', 'status', 'priority',
            'assignee', 'reporter', 'created', 'updated', 'resolutiondate',
            'labels', 'components', 'fixVersions'
        ]
        params = {'fields': ','.join(fields)}
        return self._make_request(f'issue/{issue_key}', params=params)
    
    def create_issue(self, project_key: str, issue_type: str, summary: str, 
                    description: str = "", priority: str = "Medium", 
                    assignee_account_id: str = None, labels: List[str] = None) -> Tuple[bool, Dict]:
        """Create a new JIRA issue"""
        issue_data = {
            "fields": {
                "project": {"key": project_key},
                "issuetype": {"name": issue_type},
                "summary": summary,
                "priority": {"name": priority}
            }
        }
        
        if description:
            # JIRA Cloud uses Atlassian Document Format (ADF) for rich text
            # For simplicity, we'll use plain text format
            issue_data["fields"]["description"] = {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": description
                            }
                        ]
                    }
                ]
            }
        
        if assignee_account_id:
            issue_data["fields"]["assignee"] = {"accountId": assignee_account_id}
        
        if labels:
            issue_data["fields"]["labels"] = labels
        
        return self._make_request('issue', method='POST', data=issue_data)
    
    def update_issue(self, issue_key: str, fields: Dict) -> Tuple[bool, Dict]:
        """Update an existing JIRA issue"""
        update_data = {"fields": fields}
        return self._make_request(f'issue/{issue_key}', method='PUT', data=update_data)
    
    def get_issue_transitions(self, issue_key: str) -> Tuple[bool, List[Dict]]:
        """Get available transitions for an issue"""
        success, data = self._make_request(f'issue/{issue_key}/transitions')
        if success:
            return True, data.get('transitions', [])
        return False, []
    
    def transition_issue(self, issue_key: str, transition_id: str, comment: str = None) -> Tuple[bool, Dict]:
        """Transition an issue to a new status"""
        transition_data = {
            "transition": {"id": transition_id}
        }
        
        if comment:
            transition_data["update"] = {
                "comment": [
                    {
                        "add": {
                            "body": {
                                "type": "doc",
                                "version": 1,
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [
                                            {
                                                "type": "text",
                                                "text": comment
                                            }
                                        ]
                                    }
                                ]
                            }
                        }
                    }
                ]
            }
        
        return self._make_request(f'issue/{issue_key}/transitions', method='POST', data=transition_data)
    
    def add_comment(self, issue_key: str, comment: str) -> Tuple[bool, Dict]:
        """Add a comment to an issue"""
        comment_data = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": comment
                            }
                        ]
                    }
                ]
            }
        }
        
        return self._make_request(f'issue/{issue_key}/comment', method='POST', data=comment_data)
    
    def get_users(self, project_key: str = None) -> Tuple[bool, List[Dict]]:
        """Get users who can be assigned to issues"""
        if project_key:
            params = {'project': project_key}
            return self._make_request('user/assignable/search', params=params)
        else:
            return self._make_request('users/search', params={'maxResults': 1000})


def parse_jira_datetime(date_string: str) -> datetime:
    """Parse datetime string from JIRA API"""
    try:
        # JIRA uses ISO format: 2023-12-25T10:30:00.000+0000
        if date_string.endswith('+0000'):
            date_string = date_string[:-5] + 'Z'
        return datetime.fromisoformat(date_string.replace('Z', '+00:00'))
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


def extract_plain_text_from_adf(adf_content: dict) -> str:
    """Extract plain text from Atlassian Document Format (ADF)"""
    if not isinstance(adf_content, dict):
        return str(adf_content) if adf_content else ""
    
    def extract_text(node):
        if isinstance(node, dict):
            if node.get('type') == 'text':
                return node.get('text', '')
            elif 'content' in node:
                return ''.join(extract_text(child) for child in node['content'])
        elif isinstance(node, list):
            return ''.join(extract_text(item) for item in node)
        return ''
    
    return extract_text(adf_content)