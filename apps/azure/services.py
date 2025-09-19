"""
Azure Services - Data processing and integration logic
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from django.utils import timezone
from django.db import transaction

from .models import (
    AzureConfiguration, AzureResource, AzureMetric, 
    AzureLog, AzureAlert, AzureSyncLog
)
from .client import AzureClient, AzureQueryBuilder, AzureAPIError
from apps.products.models import Product

logger = logging.getLogger(__name__)


class AzureDataService:
    """Service for managing Azure data collection and processing"""
    
    def __init__(self):
        self.query_builder = AzureQueryBuilder()
    
    def sync_all_configurations(self, force: bool = False) -> Dict[str, Any]:
        """
        Sync data for all active Azure configurations
        """
        results = {
            'configurations_processed': 0,
            'configurations_failed': 0,
            'total_resources': 0,
            'total_metrics': 0,
            'total_logs': 0,
            'errors': [],
            'details': []
        }
        
        configs = AzureConfiguration.objects.filter(is_active=True)
        
        if not force:
            configs = configs.filter(
                models.Q(last_sync__isnull=True) |
                models.Q(last_sync__lt=timezone.now() - timedelta(minutes=models.F('sync_interval_minutes')))
            )
        
        for config in configs:
            try:
                sync_result = self.sync_configuration(config)
                results['configurations_processed'] += 1
                results['total_resources'] += sync_result.get('resources_processed', 0)
                results['total_metrics'] += sync_result.get('metrics_collected', 0)
                results['total_logs'] += sync_result.get('logs_collected', 0)
                results['details'].append({
                    'configuration': config.name,
                    'result': sync_result
                })
                
            except Exception as e:
                logger.error(f"Failed to sync configuration {config.name}: {e}")
                results['configurations_failed'] += 1
                results['errors'].append(f"{config.name}: {str(e)}")
        
        return results
    
    def sync_configuration(self, config: AzureConfiguration) -> Dict[str, Any]:
        """
        Sync data for a specific Azure configuration
        """
        sync_log = AzureSyncLog.objects.create(
            configuration=config,
            sync_type=AzureSyncLog.SyncType.FULL
        )
        
        client = None
        try:
            client = AzureClient(config)
            
            # Test connection first
            connection_test = client.test_connection()
            if not connection_test['success']:
                raise AzureAPIError(f"Connection test failed: {connection_test.get('error')}")
            
            # Sync resources
            resources_result = self._sync_resources(client, config)
            sync_log.resources_processed = resources_result['count']
            
            # Sync metrics for resources
            metrics_result = self._sync_metrics(client, config)
            sync_log.metrics_collected = metrics_result['count']
            
            # Sync logs if Log Analytics is configured
            logs_result = {'count': 0}
            if config.workspace_id:
                logs_result = self._sync_logs(client, config)
                sync_log.logs_collected = logs_result['count']
            
            # Update configuration
            config.last_sync = timezone.now()
            config.save()
            
            # Mark sync as successful
            sync_log.success = True
            sync_log.completed_at = timezone.now()
            sync_log.save()
            
            return {
                'success': True,
                'resources_processed': resources_result['count'],
                'metrics_collected': metrics_result['count'],
                'logs_collected': logs_result['count'],
                'duration': sync_log.duration_seconds
            }
            
        except Exception as e:
            logger.error(f"Sync failed for {config.name}: {e}")
            sync_log.errors = [str(e)]
            sync_log.completed_at = timezone.now()
            sync_log.save()
            raise
            
        finally:
            if client:
                client.close()
    
    def _sync_resources(self, client: AzureClient, config: AzureConfiguration) -> Dict[str, Any]:
        """Sync Azure resources"""
        logger.info(f"Syncing resources for {config.name}")
        
        resources_data = client.get_resources(config.resource_group)
        processed_count = 0
        
        for resource_data in resources_data:
            try:
                resource, created = AzureResource.objects.update_or_create(
                    resource_id=resource_data['id'],
                    defaults={
                        'configuration': config,
                        'name': resource_data['name'],
                        'resource_type': self._map_resource_type(resource_data['type']),
                        'location': resource_data['location'],
                        'resource_group': resource_data.get('resourceGroup', config.resource_group),
                        'subscription_id': config.subscription_id,
                        'tags': resource_data.get('tags', {}),
                        'last_seen': timezone.now()
                    }
                )
                
                # Associate with product if possible
                if not resource.product:
                    product = self._find_product_for_resource(resource)
                    if product:
                        resource.product = product
                        resource.save()
                
                processed_count += 1
                if created:
                    logger.info(f"Created new resource: {resource.name}")
                
            except Exception as e:
                logger.error(f"Failed to process resource {resource_data['name']}: {e}")
        
        return {'count': processed_count}
    
    def _sync_metrics(self, client: AzureClient, config: AzureConfiguration) -> Dict[str, Any]:
        """Sync metrics for all resources"""
        logger.info(f"Syncing metrics for {config.name}")
        
        # Get time range (last hour by default)
        end_time = timezone.now()
        start_time = end_time - timedelta(hours=1)
        
        resources = AzureResource.objects.filter(
            configuration=config,
            is_monitored=True
        )
        
        metrics_collected = 0
        
        for resource in resources:
            try:
                metrics = self._get_metrics_for_resource_type(resource.resource_type)
                
                if metrics:
                    metrics_data = client.get_resource_metrics(
                        resource.resource_id,
                        metrics,
                        start_time,
                        end_time
                    )
                    
                    metrics_count = self._process_metrics_data(resource, metrics_data)
                    metrics_collected += metrics_count
                    
            except Exception as e:
                logger.error(f"Failed to sync metrics for {resource.name}: {e}")
        
        return {'count': metrics_collected}
    
    def _sync_logs(self, client: AzureClient, config: AzureConfiguration) -> Dict[str, Any]:
        """Sync logs from Log Analytics"""
        logger.info(f"Syncing logs for {config.name}")
        
        # Get recent logs (last hour)
        end_time = timezone.now()
        start_time = end_time - timedelta(hours=1)
        
        queries = [
            ("Application Logs", self.query_builder.error_analysis(1)),
            ("Performance", self.query_builder.infrastructure_health(1))
        ]
        
        logs_collected = 0
        
        for log_type, query in queries:
            try:
                result = client.execute_kql_query(query, start_time, end_time)
                logs_count = self._process_log_data(config, log_type, result)
                logs_collected += logs_count
                
            except Exception as e:
                logger.error(f"Failed to sync {log_type} logs: {e}")
        
        return {'count': logs_collected}
    
    def _process_metrics_data(self, resource: AzureResource, metrics_data: Dict) -> int:
        """Process and store metrics data"""
        metrics_count = 0
        
        for metric in metrics_data.get('value', []):
            metric_name = metric['name']['value']
            namespace = metric.get('type', 'Unknown')
            unit = metric['unit']
            
            for timeseries in metric.get('timeseries', []):
                for data_point in timeseries.get('data', []):
                    if 'average' in data_point and data_point['average'] is not None:
                        AzureMetric.objects.update_or_create(
                            resource=resource,
                            metric_name=metric_name,
                            timestamp=datetime.fromisoformat(data_point['timeStamp'].replace('Z', '+00:00')),
                            defaults={
                                'metric_type': self._categorize_metric(metric_name),
                                'namespace': namespace,
                                'value': data_point['average'],
                                'unit': unit,
                                'aggregation_type': 'Average',
                                'dimensions': timeseries.get('metadatavalues', {}),
                                'severity': self._assess_metric_severity(metric_name, data_point['average'])
                            }
                        )
                        metrics_count += 1
        
        return metrics_count
    
    def _process_log_data(self, config: AzureConfiguration, log_type: str, log_data: Dict) -> int:
        """Process and store log data"""
        logs_count = 0
        
        # This is a simplified implementation - in practice, you'd need to 
        # parse the specific structure of different log types
        for table in log_data.get('tables', []):
            columns = table.get('columns', [])
            rows = table.get('rows', [])
            
            for row in rows:
                # Create a simple log entry - you'd customize this based on actual log structure
                log_entry = {
                    'log_type': log_type,
                    'source': 'LogAnalytics',
                    'timestamp': timezone.now(),  # You'd parse actual timestamp from logs
                    'level': AzureLog.LogLevel.INFO,
                    'message': str(row),  # You'd extract actual message
                    'properties': dict(zip([col['name'] for col in columns], row))
                }
                
                # You'd need to find the appropriate resource for this log
                # For now, we'll skip resource association
                logs_count += 1
        
        return logs_count
    
    def _map_resource_type(self, azure_type: str) -> str:
        """Map Azure resource type to our enum"""
        type_mapping = {
            'Microsoft.Web/sites': AzureResource.ResourceType.WEB_APP,
            'Microsoft.Web/sites/functions': AzureResource.ResourceType.FUNCTION_APP,
            'Microsoft.Sql/servers/databases': AzureResource.ResourceType.SQL_DATABASE,
            'Microsoft.DocumentDB/databaseAccounts': AzureResource.ResourceType.COSMOS_DB,
            'Microsoft.Storage/storageAccounts': AzureResource.ResourceType.STORAGE_ACCOUNT,
            'Microsoft.KeyVault/vaults': AzureResource.ResourceType.KEY_VAULT,
            'Microsoft.Network/applicationGateways': AzureResource.ResourceType.APPLICATION_GATEWAY,
            'Microsoft.Network/loadBalancers': AzureResource.ResourceType.LOAD_BALANCER,
            'Microsoft.Compute/virtualMachines': AzureResource.ResourceType.VIRTUAL_MACHINE,
            'Microsoft.ContainerInstance/containerGroups': AzureResource.ResourceType.CONTAINER_INSTANCE,
        }
        
        return type_mapping.get(azure_type, AzureResource.ResourceType.OTHER)
    
    def _get_metrics_for_resource_type(self, resource_type: str) -> List[str]:
        """Get relevant metrics for a resource type"""
        metric_mapping = {
            AzureResource.ResourceType.WEB_APP: [
                'CpuPercentage', 'MemoryPercentage', 'HttpResponseTime', 
                'Http5xx', 'Http4xx', 'Requests'
            ],
            AzureResource.ResourceType.SQL_DATABASE: [
                'cpu_percent', 'memory_percent', 'dtu_consumption_percent',
                'storage_percent', 'connection_successful', 'connection_failed'
            ],
            AzureResource.ResourceType.COSMOS_DB: [
                'TotalRequestUnits', 'ProvisionedThroughput', 'AvailableStorage',
                'ServerSideLatency', 'UserErrors', 'ThrottledRequests'
            ],
            AzureResource.ResourceType.STORAGE_ACCOUNT: [
                'UsedCapacity', 'Transactions', 'Ingress', 'Egress', 'SuccessE2ELatency'
            ]
        }
        
        return metric_mapping.get(resource_type, [])
    
    def _categorize_metric(self, metric_name: str) -> str:
        """Categorize metric by type"""
        performance_metrics = ['cpu', 'memory', 'response', 'latency', 'duration']
        availability_metrics = ['http', 'error', 'success', 'failure', 'uptime']
        usage_metrics = ['storage', 'capacity', 'requests', 'transactions', 'throughput']
        
        metric_lower = metric_name.lower()
        
        if any(term in metric_lower for term in performance_metrics):
            return AzureMetric.MetricType.PERFORMANCE
        elif any(term in metric_lower for term in availability_metrics):
            return AzureMetric.MetricType.AVAILABILITY
        elif any(term in metric_lower for term in usage_metrics):
            return AzureMetric.MetricType.USAGE
        else:
            return AzureMetric.MetricType.CUSTOM
    
    def _assess_metric_severity(self, metric_name: str, value: float) -> str:
        """Assess metric severity based on value and thresholds"""
        # Simplified severity assessment - you'd customize these thresholds
        metric_lower = metric_name.lower()
        
        if 'cpu' in metric_lower or 'memory' in metric_lower:
            if value > 90:
                return AzureMetric.Severity.CRITICAL
            elif value > 80:
                return AzureMetric.Severity.WARNING
            else:
                return AzureMetric.Severity.INFO
        
        elif 'error' in metric_lower or '5xx' in metric_lower:
            if value > 10:
                return AzureMetric.Severity.ERROR
            elif value > 1:
                return AzureMetric.Severity.WARNING
            else:
                return AzureMetric.Severity.INFO
        
        return AzureMetric.Severity.INFO
    
    def _find_product_for_resource(self, resource: AzureResource) -> Optional[Product]:
        """Try to associate resource with a product based on naming or tags"""
        # Try to match by tags first
        if resource.tags:
            product_tag = resource.tags.get('Product') or resource.tags.get('product')
            if product_tag:
                try:
                    return Product.objects.get(name__icontains=product_tag)
                except Product.DoesNotExist:
                    pass
        
        # Try to match by resource name
        for product in Product.objects.all():
            if product.name.lower() in resource.name.lower():
                return product
        
        return None
    
    def get_infrastructure_dashboard_data(self, product_id: Optional[int] = None, 
                                        environment: Optional[str] = None) -> Dict[str, Any]:
        """
        Get dashboard data for Azure infrastructure monitoring
        """
        # Filter configurations and resources
        configs = AzureConfiguration.objects.filter(is_active=True)
        
        if environment:
            configs = configs.filter(environment_filter=environment)
        
        resources = AzureResource.objects.filter(
            configuration__in=configs,
            is_monitored=True
        )
        
        if product_id:
            resources = resources.filter(product_id=product_id)
        
        # Get recent metrics (last 24 hours)
        end_time = timezone.now()
        start_time = end_time - timedelta(hours=24)
        
        recent_metrics = AzureMetric.objects.filter(
            resource__in=resources,
            timestamp__gte=start_time
        )
        
        # Calculate summary statistics
        dashboard_data = {
            'summary': {
                'total_resources': resources.count(),
                'monitored_resources': resources.filter(is_monitored=True).count(),
                'active_alerts': AzureAlert.objects.filter(
                    resource__in=resources,
                    status=AzureAlert.AlertStatus.ACTIVE
                ).count(),
                'configurations': configs.count()
            },
            'resource_health': self._calculate_resource_health(resources, recent_metrics),
            'performance_trends': self._get_performance_trends(resources, start_time, end_time),
            'top_alerts': self._get_top_alerts(resources),
            'cost_overview': self._get_cost_overview(resources),
            'environment_breakdown': self._get_environment_breakdown(configs),
            'last_updated': timezone.now().isoformat()
        }
        
        return dashboard_data
    
    def _calculate_resource_health(self, resources, metrics) -> Dict:
        """Calculate overall resource health"""
        # Simplified health calculation
        total_resources = resources.count()
        if total_resources == 0:
            return {'status': 'unknown', 'healthy_count': 0, 'total_count': 0}
        
        # Count resources with recent critical metrics
        critical_resources = metrics.filter(
            severity=AzureMetric.Severity.CRITICAL,
            timestamp__gte=timezone.now() - timedelta(hours=1)
        ).values('resource').distinct().count()
        
        healthy_count = total_resources - critical_resources
        health_percentage = (healthy_count / total_resources) * 100
        
        if health_percentage >= 95:
            status = 'healthy'
        elif health_percentage >= 80:
            status = 'warning'
        else:
            status = 'critical'
        
        return {
            'status': status,
            'healthy_count': healthy_count,
            'total_count': total_resources,
            'health_percentage': round(health_percentage, 1)
        }
    
    def _get_performance_trends(self, resources, start_time, end_time) -> Dict:
        """Get performance trends for the time period"""
        # This would generate trend data for key metrics
        # Simplified implementation
        return {
            'cpu_trend': [],
            'memory_trend': [],
            'response_time_trend': [],
            'error_rate_trend': []
        }
    
    def _get_top_alerts(self, resources) -> List[Dict]:
        """Get top active alerts"""
        alerts = AzureAlert.objects.filter(
            resource__in=resources,
            status=AzureAlert.AlertStatus.ACTIVE
        ).order_by('-fired_at')[:10]
        
        return [
            {
                'name': alert.name,
                'severity': alert.get_severity_display(),
                'resource': alert.resource.name if alert.resource else 'N/A',
                'fired_at': alert.fired_at.isoformat(),
                'duration': str(alert.duration)
            }
            for alert in alerts
        ]
    
    def _get_cost_overview(self, resources) -> Dict:
        """Get cost overview for resources"""
        # This would integrate with Azure Cost Management API
        # Simplified implementation
        return {
            'current_month': 0,
            'last_month': 0,
            'trend': 'stable',
            'top_resources': []
        }
    
    def _get_environment_breakdown(self, configs) -> List[Dict]:
        """Get breakdown by environment"""
        breakdown = []
        
        for config in configs:
            env_data = {
                'environment': config.environment_filter,
                'configuration': config.name,
                'resources': config.resources.count(),
                'last_sync': config.last_sync.isoformat() if config.last_sync else None,
                'status': 'healthy'  # You'd calculate actual status
            }
            breakdown.append(env_data)
        
        return breakdown