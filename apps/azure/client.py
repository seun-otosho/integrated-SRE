"""
Azure Application Insights and Log Analytics Client
Handles authentication and API interactions with Azure services
"""

import logging
import requests
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import quote

from django.conf import settings
from django.utils import timezone

from .models import AzureConfiguration

logger = logging.getLogger(__name__)


class AzureAuthenticationError(Exception):
    """Raised when Azure authentication fails"""
    pass


class AzureAPIError(Exception):
    """Raised when Azure API calls fail"""
    pass


class AzureClient:
    """Client for Azure Application Insights and Log Analytics APIs"""
    
    # Azure API endpoints
    AZURE_LOGIN_URL = "https://login.microsoftonline.com"
    AZURE_MANAGEMENT_URL = "https://management.azure.com"
    AZURE_MONITOR_URL = "https://api.applicationinsights.io"
    AZURE_LOG_ANALYTICS_URL = "https://api.loganalytics.io"
    
    def __init__(self, configuration: AzureConfiguration):
        self.configuration = configuration
        self.access_token = None
        self.token_expires_at = None
        self.session = requests.Session()
        
        # Set default headers
        self.session.headers.update({
            'User-Agent': 'SRE-Dashboard/1.0',
            'Accept': 'application/json'
        })
    
    def authenticate(self) -> str:
        """
        Authenticate with Azure using service principal credentials
        Returns access token
        """
        if self.access_token and self.token_expires_at:
            if timezone.now() < self.token_expires_at - timedelta(minutes=5):
                return self.access_token
        
        logger.info(f"Authenticating with Azure for {self.configuration.name}")
        
        auth_url = f"{self.AZURE_LOGIN_URL}/{self.configuration.tenant_id}/oauth2/v2.0/token"
        
        data = {
            'grant_type': 'client_credentials',
            'client_id': self.configuration.client_id,
            'client_secret': self.configuration.client_secret,
            'scope': 'https://management.azure.com/.default'
        }
        
        try:
            # OAuth2 requires application/x-www-form-urlencoded
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}
            response = self.session.post(auth_url, data=data, headers=headers)
            
            # Enhanced error reporting
            if response.status_code != 200:
                error_details = response.text
                try:
                    error_json = response.json()
                    error_description = error_json.get('error_description', 'Unknown error')
                    error_code = error_json.get('error', 'unknown_error')
                    logger.error(f"Azure auth failed - Code: {error_code}, Description: {error_description}")
                    raise AzureAuthenticationError(f"Azure authentication failed: {error_code} - {error_description}")
                except:
                    logger.error(f"Azure auth failed with status {response.status_code}: {error_details}")
                    raise AzureAuthenticationError(f"Azure authentication failed (HTTP {response.status_code}): {error_details}")
            
            token_data = response.json()
            self.access_token = token_data['access_token']
            
            # Calculate token expiration (with buffer)
            expires_in = token_data.get('expires_in', 3600)
            self.token_expires_at = timezone.now() + timedelta(seconds=expires_in)
            
            # Update session headers
            self.session.headers['Authorization'] = f'Bearer {self.access_token}'
            
            logger.info("Azure authentication successful")
            return self.access_token
            
        except AzureAuthenticationError:
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Azure authentication network error: {e}")
            raise AzureAuthenticationError(f"Network error during Azure authentication: {e}")
    
    def test_connection(self) -> Dict[str, Any]:
        """
        Test connection to Azure APIs
        Returns connection status and basic info
        """
        try:
            self.authenticate()
            
            # Test management API
            mgmt_url = f"{self.AZURE_MANAGEMENT_URL}/subscriptions/{self.configuration.subscription_id}"
            mgmt_params = {'api-version': '2020-01-01'}
            
            mgmt_response = self.session.get(mgmt_url, params=mgmt_params)
            mgmt_response.raise_for_status()
            
            subscription_info = mgmt_response.json()
            
            result = {
                'success': True,
                'subscription': {
                    'id': subscription_info.get('subscriptionId'),
                    'display_name': subscription_info.get('displayName'),
                    'state': subscription_info.get('state')
                },
                'authentication': 'success',
                'apis_tested': ['management']
            }
            
            # Test Application Insights if configured
            if self.configuration.application_id:
                try:
                    app_insights_url = f"{self.AZURE_MONITOR_URL}/v1/apps/{self.configuration.application_id}/metadata"
                    ai_response = self.session.get(app_insights_url)
                    ai_response.raise_for_status()
                    result['apis_tested'].append('application_insights')
                except Exception as e:
                    logger.warning(f"Application Insights test failed: {e}")
            
            # Test Log Analytics if configured
            if self.configuration.workspace_id:
                try:
                    # Simple query to test access
                    query_result = self.execute_kql_query("print 'connection_test'", limit=1)
                    if query_result:
                        result['apis_tested'].append('log_analytics')
                except Exception as e:
                    logger.warning(f"Log Analytics test failed: {e}")
            
            return result
            
        except Exception as e:
            logger.error(f"Azure connection test failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'authentication': 'failed'
            }
    
    def get_resources(self, resource_group: Optional[str] = None) -> List[Dict]:
        """
        Get Azure resources from the subscription/resource group
        """
        self.authenticate()
        
        if resource_group:
            url = f"{self.AZURE_MANAGEMENT_URL}/subscriptions/{self.configuration.subscription_id}/resourceGroups/{resource_group}/resources"
        else:
            url = f"{self.AZURE_MANAGEMENT_URL}/subscriptions/{self.configuration.subscription_id}/resources"
        
        params = {'api-version': '2021-04-01'}
        
        # Add resource tag filters if configured
        if self.configuration.resource_tags:
            tag_filters = []
            for key, value in self.configuration.resource_tags.items():
                tag_filters.append(f"tagName eq '{key}' and tagValue eq '{value}'")
            if tag_filters:
                params['$filter'] = ' and '.join(tag_filters)
        
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            resources = data.get('value', [])
            
            logger.info(f"Retrieved {len(resources)} resources from Azure")
            
            # Add resource group name to each resource if not present
            for resource in resources:
                if 'resourceGroup' not in resource and 'id' in resource:
                    # Extract resource group from resource ID
                    try:
                        resource_id = resource['id']
                        rg_name = resource_id.split('/resourceGroups/')[1].split('/')[0]
                        resource['resourceGroup'] = rg_name
                    except (IndexError, KeyError):
                        logger.warning(f"Could not extract resource group from {resource.get('id', 'unknown')}")
                        resource['resourceGroup'] = resource_group or 'unknown'
            
            return resources
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get Azure resources: {e}")
            raise AzureAPIError(f"Failed to get resources: {e}")
    
    def get_resource_metrics(self, resource_id: str, metrics: List[str], 
                           start_time: datetime, end_time: datetime,
                           time_grain: str = 'PT1M') -> Dict:
        """
        Get metrics for a specific Azure resource
        """
        self.authenticate()
        
        # Build metrics list
        metric_names = ','.join(metrics)
        
        url = f"{self.AZURE_MANAGEMENT_URL}{resource_id}/providers/Microsoft.Insights/metrics"
        # Format timestamps for Azure API (needs timezone)
        start_time_str = start_time.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        end_time_str = end_time.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        
        params = {
            'api-version': '2018-01-01',
            'metricnames': metric_names,
            'timespan': f"{start_time_str}/{end_time_str}",
            'interval': time_grain,
            'aggregation': 'Average,Maximum,Minimum'
        }
        
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get metrics for {resource_id}: {e}")
            raise AzureAPIError(f"Failed to get metrics: {e}")
    
    def execute_kql_query(self, query: str, start_time: Optional[datetime] = None,
                         end_time: Optional[datetime] = None, limit: int = 1000) -> Dict:
        """
        Execute KQL query against Log Analytics workspace
        """
        if not self.configuration.workspace_id:
            raise AzureAPIError("Log Analytics workspace not configured")
        
        self.authenticate()
        
        url = f"{self.AZURE_LOG_ANALYTICS_URL}/v1/workspaces/{self.configuration.workspace_id}/query"
        
        # Build query with time range if provided
        full_query = query
        if start_time and end_time:
            time_filter = f"| where TimeGenerated between (datetime({start_time.isoformat()}) .. datetime({end_time.isoformat()}))"
            full_query = f"{query} {time_filter}"
        
        if limit:
            full_query = f"{full_query} | limit {limit}"
        
        data = {'query': full_query}
        
        try:
            response = self.session.post(url, json=data)
            response.raise_for_status()
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"KQL query failed: {e}")
            raise AzureAPIError(f"KQL query failed: {e}")
    
    def get_application_insights_events(self, event_type: str, 
                                      start_time: datetime, end_time: datetime,
                                      filters: Optional[Dict] = None) -> Dict:
        """
        Get events from Application Insights
        """
        if not self.configuration.application_id:
            raise AzureAPIError("Application Insights not configured")
        
        self.authenticate()
        
        url = f"{self.AZURE_MONITOR_URL}/v1/apps/{self.configuration.application_id}/events/{event_type}"
        
        params = {
            'timespan': f"{start_time.isoformat()}/{end_time.isoformat()}",
            '$top': 1000
        }
        
        if filters:
            filter_conditions = []
            for key, value in filters.items():
                filter_conditions.append(f"{key} eq '{value}'")
            if filter_conditions:
                params['$filter'] = ' and '.join(filter_conditions)
        
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get Application Insights events: {e}")
            raise AzureAPIError(f"Failed to get Application Insights events: {e}")
    
    def get_database_metrics(self, database_resource_id: str, 
                           start_time: datetime, end_time: datetime) -> Dict:
        """
        Get database-specific metrics (SQL Database, Cosmos DB)
        """
        # Common database metrics
        db_metrics = [
            'cpu_percent',
            'memory_percent', 
            'dtu_consumption_percent',
            'storage_percent',
            'connection_successful',
            'connection_failed',
            'blocked_by_firewall'
        ]
        
        return self.get_resource_metrics(
            database_resource_id, 
            db_metrics, 
            start_time, 
            end_time
        )
    
    def get_performance_summary(self, start_time: datetime, end_time: datetime) -> Dict:
        """
        Get performance summary across all configured resources
        """
        summary = {
            'period': {
                'start': start_time.isoformat(),
                'end': end_time.isoformat()
            },
            'resources': [],
            'overall_health': 'unknown',
            'alerts': 0,
            'errors': 0
        }
        
        try:
            # Get all resources
            resources = self.get_resources()
            
            for resource in resources:
                resource_id = resource['id']
                resource_summary = {
                    'id': resource_id,
                    'name': resource['name'],
                    'type': resource['type'],
                    'location': resource['location'],
                    'health': 'unknown',
                    'metrics': {}
                }
                
                try:
                    # Get basic metrics for this resource type
                    if 'Microsoft.Web' in resource['type']:
                        # Web App metrics
                        metrics = self.get_resource_metrics(
                            resource_id,
                            ['CpuPercentage', 'MemoryPercentage', 'HttpResponseTime'],
                            start_time,
                            end_time
                        )
                        resource_summary['metrics'] = metrics
                        
                    elif 'Microsoft.Sql' in resource['type']:
                        # SQL Database metrics
                        metrics = self.get_database_metrics(resource_id, start_time, end_time)
                        resource_summary['metrics'] = metrics
                        
                except Exception as e:
                    logger.warning(f"Failed to get metrics for {resource['name']}: {e}")
                    resource_summary['error'] = str(e)
                
                summary['resources'].append(resource_summary)
            
            # Calculate overall health
            healthy_resources = sum(1 for r in summary['resources'] if r.get('health') != 'critical')
            total_resources = len(summary['resources'])
            
            if total_resources == 0:
                summary['overall_health'] = 'unknown'
            elif healthy_resources / total_resources >= 0.9:
                summary['overall_health'] = 'healthy'
            elif healthy_resources / total_resources >= 0.7:
                summary['overall_health'] = 'warning'
            else:
                summary['overall_health'] = 'critical'
            
            return summary
            
        except Exception as e:
            logger.error(f"Failed to get performance summary: {e}")
            summary['error'] = str(e)
            return summary
    
    def close(self):
        """Close the session"""
        if self.session:
            self.session.close()


class AzureQueryBuilder:
    """Helper class for building KQL queries"""
    
    @staticmethod
    def performance_overview(hours: int = 24) -> str:
        """Build query for performance overview"""
        return f"""
        let timeRange = {hours}h;
        union 
        (requests 
         | where timestamp > ago(timeRange)
         | summarize 
             RequestCount = count(),
             AvgDuration = avg(duration),
             FailureRate = countif(success == false) * 100.0 / count()
         | extend Type = "Requests"),
        (dependencies 
         | where timestamp > ago(timeRange)
         | summarize 
             DependencyCount = count(),
             AvgDuration = avg(duration),
             FailureRate = countif(success == false) * 100.0 / count()
         | extend Type = "Dependencies"),
        (exceptions 
         | where timestamp > ago(timeRange)
         | summarize ExceptionCount = count()
         | extend Type = "Exceptions")
        """
    
    @staticmethod
    def database_performance(hours: int = 24) -> str:
        """Build query for database performance"""
        return f"""
        let timeRange = {hours}h;
        dependencies
        | where timestamp > ago(timeRange)
        | where type == "SQL" or type == "Azure DocumentDB"
        | summarize 
            QueryCount = count(),
            AvgDuration = avg(duration),
            MaxDuration = max(duration),
            FailureCount = countif(success == false),
            FailureRate = countif(success == false) * 100.0 / count()
            by target, type
        | order by QueryCount desc
        """
    
    @staticmethod
    def error_analysis(hours: int = 24) -> str:
        """Build query for error analysis"""
        return f"""
        let timeRange = {hours}h;
        union 
        (exceptions 
         | where timestamp > ago(timeRange)
         | summarize ErrorCount = count() by type, outerMessage
         | extend Source = "Exceptions"),
        (traces 
         | where timestamp > ago(timeRange) and severityLevel >= 3
         | summarize ErrorCount = count() by message
         | extend Source = "Traces")
        | order by ErrorCount desc
        | limit 50
        """
    
    @staticmethod
    def infrastructure_health(hours: int = 1) -> str:
        """Build query for infrastructure health check"""
        return f"""
        let timeRange = {hours}h;
        union
        (performanceCounters
         | where timestamp > ago(timeRange)
         | where counter == "% Processor Time" or counter == "Available MBytes"
         | summarize 
             AvgValue = avg(value),
             MaxValue = max(value)
             by counter, instance
         | extend Type = "Performance"),
        (heartbeat
         | where timestamp > ago(timeRange)
         | summarize LastHeartbeat = max(timestamp) by Computer
         | extend Type = "Heartbeat")
        """