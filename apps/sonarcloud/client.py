import requests
import base64
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from django.conf import settings

logger = logging.getLogger(__name__)


class SonarCloudAPIClient:
    """Client for interacting with SonarCloud Web API"""
    
    def __init__(self, api_token: str):
        self.api_token = api_token
        self.api_base = "https://sonarcloud.io/api"
        
        # Create session with authentication
        self.session = requests.Session()
        # SonarCloud uses token-based auth (token as username, empty password)
        auth_string = f"{api_token}:"
        auth_bytes = auth_string.encode('ascii')
        auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
        
        self.session.headers.update({
            'Authorization': f'Basic {auth_b64}',
            'Accept': 'application/json'
        })
    
    def _make_request(self, endpoint: str, method: str = 'GET', params: dict = None, data: dict = None) -> Tuple[bool, dict]:
        """Make a request to SonarCloud API"""
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
                except ValueError:
                    return True, {}
            else:
                error_text = response.text
                try:
                    error_json = response.json()
                    if 'errors' in error_json:
                        error_text = '; '.join([err.get('msg', str(err)) for err in error_json['errors']])
                    elif 'message' in error_json:
                        error_text = error_json['message']
                except:
                    pass
                
                logger.error(f"SonarCloud API error {response.status_code} for {url}: {error_text}")
                return False, {
                    'error': f"HTTP {response.status_code}",
                    'message': error_text,
                    'status_code': response.status_code,
                    'url': url
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"SonarCloud API request failed: {str(e)}")
            return False, {'error': 'Request failed', 'message': str(e)}
    
    def test_connection(self) -> Tuple[bool, str]:
        """Test the SonarCloud API connection"""
        success, data = self._make_request('authentication/validate')
        if success:
            valid = data.get('valid', False)
            if valid:
                return True, "Connection successful - API token is valid"
            else:
                return False, "API token is invalid"
        else:
            error_msg = data.get('message', 'Unknown error')
            return False, f"Connection failed: {error_msg}"
    
    def get_organizations(self) -> Tuple[bool, List[Dict]]:
        """Get list of organizations accessible to the user"""
        success, data = self._make_request('organizations/search')
        if success:
            return True, data.get('organizations', [])
        return False, []
    
    def get_organization(self, organization_key: str) -> Tuple[bool, Dict]:
        """Get specific organization details"""
        params = {'organization': organization_key}
        success, data = self._make_request('organizations/search', params=params)
        if success:
            organizations = data.get('organizations', [])
            if organizations:
                return True, organizations[0]
            else:
                return False, {'message': 'Organization not found'}
        return False, data
    
    def get_projects(self, organization_key: str, page_size: int = 500) -> Tuple[bool, List[Dict]]:
        """Get list of projects in an organization"""
        params = {
            'organization': organization_key,
            'ps': page_size  # page size
        }
        
        all_projects = []
        page = 1
        
        while True:
            params['p'] = page
            success, data = self._make_request('projects/search', params=params)
            
            if not success:
                return False, []
            
            projects = data.get('components', [])
            all_projects.extend(projects)
            
            # Check if we have more pages
            paging = data.get('paging', {})
            total = paging.get('total', 0)
            page_size_actual = paging.get('pageSize', page_size)
            
            if len(all_projects) >= total:
                break
            
            page += 1
        
        return True, all_projects
    
    def get_project_measures(self, project_key: str, metrics: List[str] = None) -> Tuple[bool, Dict]:
        """Get quality measures for a project"""
        if metrics is None:
            # Default set of important metrics
            metrics = [
                'alert_status',  # Quality Gate status
                'reliability_rating', 'security_rating', 'sqale_rating',  # Ratings
                'coverage', 'line_coverage', 'branch_coverage',  # Coverage
                'duplicated_lines_density',  # Duplication
                'ncloc',  # Lines of code
                'sqale_index',  # Technical debt
                'bugs', 'vulnerabilities', 'security_hotspots', 'code_smells',  # Issues
                'complexity', 'cognitive_complexity',  # Complexity
                'classes', 'functions', 'files'  # Size metrics
            ]
        
        params = {
            'component': project_key,
            'metricKeys': ','.join(metrics)
        }
        
        success, data = self._make_request('measures/component', params=params)
        if success:
            component = data.get('component', {})
            measures = component.get('measures', [])
            
            # Convert to dict for easier access
            measures_dict = {}
            for measure in measures:
                metric = measure.get('metric')
                value = measure.get('value')
                measures_dict[metric] = value
            
            return True, {
                'component': component,
                'measures': measures_dict
            }
        
        return False, data
    
    def get_project_issues(self, project_key: str, types: List[str] = None, 
                          page_size: int = 500) -> Tuple[bool, List[Dict]]:
        """Get issues for a project"""
        if types is None:
            types = ['BUG', 'VULNERABILITY', 'CODE_SMELL']
        
        params = {
            'componentKeys': project_key,
            'types': ','.join(types),
            'ps': page_size,
            'resolved': 'false'  # Only get unresolved issues
        }
        
        all_issues = []
        page = 1
        
        while True:
            params['p'] = page
            success, data = self._make_request('issues/search', params=params)
            
            if not success:
                return False, []
            
            issues = data.get('issues', [])
            all_issues.extend(issues)
            
            # Check pagination
            paging = data.get('paging', {})
            total = paging.get('total', 0)
            
            if len(all_issues) >= total:
                break
            
            page += 1
            
            # Safety limit to prevent infinite loops
            if page > 100:
                logger.warning(f"Hit page limit while fetching issues for {project_key}")
                break
        
        return True, all_issues
    
    def get_security_hotspots(self, project_key: str, page_size: int = 500) -> Tuple[bool, List[Dict]]:
        """Get security hotspots for a project"""
        params = {
            'projectKey': project_key,
            'ps': page_size,
            'status': 'TO_REVIEW'  # Only get hotspots that need review
        }
        
        all_hotspots = []
        page = 1
        
        while True:
            params['p'] = page
            success, data = self._make_request('hotspots/search', params=params)
            
            if not success:
                return False, []
            
            hotspots = data.get('hotspots', [])
            all_hotspots.extend(hotspots)
            
            # Check pagination
            paging = data.get('paging', {})
            total = paging.get('total', 0)
            
            if len(all_hotspots) >= total:
                break
            
            page += 1
            
            # Safety limit
            if page > 50:
                logger.warning(f"Hit page limit while fetching hotspots for {project_key}")
                break
        
        return True, all_hotspots
    
    def get_quality_gate_status(self, project_key: str, branch: str = None) -> Tuple[bool, Dict]:
        """Get quality gate status for a project"""
        params = {'projectKey': project_key}
        if branch:
            params['branch'] = branch
        
        return self._make_request('qualitygates/project_status', params=params)
    
    def get_project_analyses(self, project_key: str, category: str = 'VERSION') -> Tuple[bool, List[Dict]]:
        """Get project analysis history"""
        params = {
            'project': project_key,
            'category': category,
            'ps': 100  # Get last 100 analyses
        }
        
        success, data = self._make_request('project_analyses/search', params=params)
        if success:
            return True, data.get('analyses', [])
        return False, []
    
    def get_metrics_definitions(self) -> Tuple[bool, List[Dict]]:
        """Get all available metrics definitions"""
        success, data = self._make_request('metrics/search')
        if success:
            return True, data.get('metrics', [])
        return False, []


def parse_sonar_datetime(date_string: str) -> datetime:
    """Parse datetime string from SonarCloud API"""
    try:
        # SonarCloud uses ISO format: 2023-12-25T10:30:00+0000
        if date_string.endswith('+0000'):
            date_string = date_string[:-5] + 'Z'
        return datetime.fromisoformat(date_string.replace('Z', '+00:00'))
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


def convert_rating_to_letter(rating_value: str) -> str:
    """Convert SonarCloud numeric rating to letter (1=A, 2=B, etc.)"""
    rating_map = {'1': 'A', '2': 'B', '3': 'C', '4': 'D', '5': 'E'}
    return rating_map.get(str(rating_value), '')


def convert_technical_debt(debt_string: str) -> int:
    """Convert technical debt string to minutes"""
    if not debt_string:
        return 0
    
    try:
        # Handle formats like "1h 30min", "45min", "2d 3h"
        total_minutes = 0
        
        # Extract days
        if 'd' in debt_string:
            days_part = debt_string.split('d')[0].strip()
            if days_part.isdigit():
                total_minutes += int(days_part) * 24 * 60
        
        # Extract hours
        if 'h' in debt_string:
            h_index = debt_string.find('h')
            # Find the number before 'h'
            h_start = h_index - 1
            while h_start >= 0 and (debt_string[h_start].isdigit() or debt_string[h_start] == ' '):
                h_start -= 1
            h_start += 1
            
            hours_str = debt_string[h_start:h_index].strip()
            if hours_str.isdigit():
                total_minutes += int(hours_str) * 60
        
        # Extract minutes
        if 'min' in debt_string:
            min_index = debt_string.find('min')
            # Find the number before 'min'
            min_start = min_index - 1
            while min_start >= 0 and (debt_string[min_start].isdigit() or debt_string[min_start] == ' '):
                min_start -= 1
            min_start += 1
            
            minutes_str = debt_string[min_start:min_index].strip()
            if minutes_str.isdigit():
                total_minutes += int(minutes_str)
        
        return total_minutes
        
    except (ValueError, AttributeError):
        return 0