import requests
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from django.conf import settings

logger = logging.getLogger(__name__)


class SentryAPIClient:
    """Client for interacting with Sentry API"""
    
    def __init__(self, api_token: str, api_url: str = "https://sentry.io/api/0/"):
        self.api_token = api_token
        self.api_url = api_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {api_token}',
            'Content-Type': 'application/json'
        })
    
    def _make_request(self, endpoint: str, method: str = 'GET', params: dict = None, data: dict = None) -> Tuple[bool, dict]:
        """Make a request to Sentry API"""
        url = f"{self.api_url}/{endpoint.lstrip('/')}"
        
        try:
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=data,
                timeout=30
            )
            
            if response.status_code == 200:
                return True, response.json()
            else:
                logger.error(f"Sentry API error {response.status_code}: {response.text}")
                return False, {'error': f"HTTP {response.status_code}: {response.text}"}
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Sentry API request failed: {str(e)}")
            return False, {'error': str(e)}
    
    def get_organizations(self) -> Tuple[bool, List[Dict]]:
        """Get list of organizations"""
        success, data = self._make_request('organizations/')
        if success:
            return True, data
        return False, []
    
    def get_organization(self, org_slug: str) -> Tuple[bool, Dict]:
        """Get organization details"""
        return self._make_request(f'organizations/{org_slug}/')
    
    def get_projects(self, org_slug: str) -> Tuple[bool, List[Dict]]:
        """Get projects for an organization"""
        success, data = self._make_request(f'organizations/{org_slug}/projects/')
        if success:
            return True, data
        return False, []
    
    def get_project(self, org_slug: str, project_slug: str) -> Tuple[bool, Dict]:
        """Get project details"""
        return self._make_request(f'projects/{org_slug}/{project_slug}/')
    
    def get_issues(self, org_slug: str, project_slug: str, limit: int = 100, status: str = None) -> Tuple[bool, List[Dict]]:
        """Get issues for a project"""
        params = {'limit': limit}
        if status:
            params['query'] = f'is:{status}'
        
        success, data = self._make_request(f'projects/{org_slug}/{project_slug}/issues/', params=params)
        if success:
            return True, data
        return False, []
    
    def get_issue_events(self, issue_id: str, limit: int = 50) -> Tuple[bool, List[Dict]]:
        """Get events for an issue"""
        params = {'limit': limit}
        success, data = self._make_request(f'issues/{issue_id}/events/', params=params)
        if success:
            return True, data
        return False, []
    
    def get_project_stats(self, org_slug: str, project_slug: str, stat: str = '24h') -> Tuple[bool, List[Dict]]:
        """Get project statistics"""
        params = {'stat': stat}
        return self._make_request(f'projects/{org_slug}/{project_slug}/stats/', params=params)
    
    def test_connection(self) -> Tuple[bool, str]:
        """Test API connection"""
        success, data = self.get_organizations()
        if success:
            return True, f"Connected successfully. Found {len(data)} organizations."
        else:
            return False, f"Connection failed: {data.get('error', 'Unknown error')}"


def parse_datetime(date_string: str) -> datetime:
    """Parse datetime string from Sentry API"""
    try:
        # Handle different datetime formats from Sentry
        if date_string.endswith('Z'):
            date_string = date_string[:-1] + '+00:00'
        return datetime.fromisoformat(date_string)
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)