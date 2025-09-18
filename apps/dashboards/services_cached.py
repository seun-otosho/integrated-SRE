import logging
from datetime import datetime
from typing import Dict, Optional, Tuple
from django.utils import timezone

from .models_cache import DashboardSnapshot, DashboardRefreshLog
from .services import DashboardDataService

logger = logging.getLogger(__name__)


class CachedDashboardService:
    """Service for serving pre-computed dashboard data with instant loading"""
    
    def __init__(self):
        self.data_service = DashboardDataService()
        self.default_ttl = 30  # 30 minutes default cache
    
    def get_executive_overview(self, product_filter=None, environment_filter=None) -> Tuple[Dict, bool]:
        """Get executive dashboard data from cache or generate if needed"""
        filter_key = self._build_filter_key('executive', product_filter, environment_filter)
        
        def generator():
            return self.data_service.get_executive_overview(product_filter, environment_filter)
        
        snapshot, was_generated = DashboardSnapshot.get_or_generate(
            dashboard_type=DashboardSnapshot.DashboardType.EXECUTIVE,
            filter_key=filter_key,
            generator_func=generator,
            ttl_minutes=self.default_ttl
        )
        
        if not snapshot.is_valid:
            logger.error(f"Dashboard snapshot invalid: {snapshot.error_message}")
            # Fallback to real-time generation
            return self.data_service.get_executive_overview(product_filter, environment_filter), True
        
        # Add cache metadata to response
        data = snapshot.data.copy()
        data['_cache_info'] = {
            'cached': True,
            'generated_at': snapshot.generated_at.isoformat(),
            'age_minutes': round(snapshot.age_minutes, 1),
            'expires_in_minutes': round(snapshot.time_until_expiry, 1),
            'generation_time': f"{snapshot.generation_time:.3f}s",
            'was_generated': was_generated,
            'data_size_kb': round(snapshot.data_size / 1024, 1),
            'source_records': snapshot.source_record_count
        }
        
        return data, was_generated
    
    def get_product_health_dashboard(self, product_id=None, environment_filter=None) -> Tuple[Dict, bool]:
        """Get product dashboard data from cache or generate if needed"""
        filter_key = self._build_filter_key('product', product_id, environment_filter)
        
        def generator():
            return self.data_service.get_product_health_dashboard(product_id, environment_filter)
        
        snapshot, was_generated = DashboardSnapshot.get_or_generate(
            dashboard_type=DashboardSnapshot.DashboardType.PRODUCT,
            filter_key=filter_key,
            generator_func=generator,
            ttl_minutes=self.default_ttl
        )
        
        if not snapshot.is_valid:
            return self.data_service.get_product_health_dashboard(product_id, environment_filter), True
        
        data = snapshot.data.copy()
        data['_cache_info'] = {
            'cached': True,
            'generated_at': snapshot.generated_at.isoformat(),
            'age_minutes': round(snapshot.age_minutes, 1),
            'expires_in_minutes': round(snapshot.time_until_expiry, 1),
            'generation_time': f"{snapshot.generation_time:.3f}s",
            'was_generated': was_generated
        }
        
        return data, was_generated
    
    def get_environment_dashboard(self, environment=None, product_filter=None) -> Tuple[Dict, bool]:
        """Get environment dashboard data from cache or generate if needed"""
        filter_key = self._build_filter_key('environment', environment, product_filter)
        
        def generator():
            return self.data_service.get_environment_dashboard(environment, product_filter)
        
        snapshot, was_generated = DashboardSnapshot.get_or_generate(
            dashboard_type=DashboardSnapshot.DashboardType.ENVIRONMENT,
            filter_key=filter_key,
            generator_func=generator,
            ttl_minutes=self.default_ttl
        )
        
        if not snapshot.is_valid:
            return self.data_service.get_environment_dashboard(environment, product_filter), True
        
        data = snapshot.data.copy()
        data['_cache_info'] = {
            'cached': True,
            'generated_at': snapshot.generated_at.isoformat(),
            'age_minutes': round(snapshot.age_minutes, 1),
            'expires_in_minutes': round(snapshot.time_until_expiry, 1),
            'generation_time': f"{snapshot.generation_time:.3f}s",
            'was_generated': was_generated
        }
        
        return data, was_generated
    
    def _build_filter_key(self, dashboard_type: str, param1=None, param2=None) -> str:
        """Build a unique filter key for caching"""
        parts = [dashboard_type]
        
        if param1 is not None:
            parts.append(f"p1_{param1}")
        if param2 is not None:
            parts.append(f"p2_{param2}")
        
        return "_".join(parts)
    
    def refresh_dashboard_cache(self, dashboard_type: str = None, force: bool = False) -> Dict:
        """Refresh dashboard cache for specified type or all types"""
        log = DashboardRefreshLog.objects.create(
            refresh_type=DashboardRefreshLog.RefreshType.FORCE_ALL if force else DashboardRefreshLog.RefreshType.ON_DEMAND,
            dashboard_types=[]
        )
        
        results = {
            'snapshots_refreshed': 0,
            'snapshots_failed': 0,
            'errors': [],
            'details': []
        }
        
        try:
            # Determine which dashboard types to refresh
            if dashboard_type:
                dashboard_types = [dashboard_type]
            else:
                dashboard_types = ['executive', 'product', 'environment']
            
            log.dashboard_types = dashboard_types
            log.save()
            
            for dash_type in dashboard_types:
                type_results = self._refresh_dashboard_type(dash_type, force)
                results['snapshots_refreshed'] += type_results['refreshed']
                results['snapshots_failed'] += type_results['failed']
                results['errors'].extend(type_results['errors'])
                results['details'].append({
                    'dashboard_type': dash_type,
                    'refreshed': type_results['refreshed'],
                    'failed': type_results['failed'],
                    'combinations': type_results['combinations']
                })
            
            # Update log
            log.snapshots_refreshed = results['snapshots_refreshed']
            log.snapshots_failed = results['snapshots_failed']
            log.errors = results['errors']
            log.completed_at = timezone.now()
            log.save()
            
        except Exception as e:
            log.errors = [str(e)]
            log.completed_at = timezone.now()
            log.save()
            results['errors'].append(str(e))
        
        return results
    
    def _refresh_dashboard_type(self, dashboard_type: str, force: bool = False) -> Dict:
        """Refresh all combinations for a specific dashboard type"""
        results = {
            'refreshed': 0,
            'failed': 0,
            'errors': [],
            'combinations': []
        }
        
        # Get all existing snapshots for this type
        snapshots = DashboardSnapshot.objects.filter(dashboard_type=dashboard_type)
        
        if not force:
            # Only refresh expired snapshots
            snapshots = snapshots.filter(expires_at__lte=timezone.now())
        
        for snapshot in snapshots:
            try:
                # Parse filter key to reconstruct parameters
                filter_parts = snapshot.filter_key.split('_')
                
                if dashboard_type == 'executive':
                    product_filter = self._extract_param(filter_parts, 'p1')
                    environment_filter = self._extract_param(filter_parts, 'p2')
                    
                    def generator():
                        return self.data_service.get_executive_overview(product_filter, environment_filter)
                    
                elif dashboard_type == 'product':
                    product_id = self._extract_param(filter_parts, 'p1')
                    environment_filter = self._extract_param(filter_parts, 'p2')
                    
                    def generator():
                        return self.data_service.get_product_health_dashboard(product_id, environment_filter)
                    
                elif dashboard_type == 'environment':
                    environment = self._extract_param(filter_parts, 'p1')
                    product_filter = self._extract_param(filter_parts, 'p2')
                    
                    def generator():
                        return self.data_service.get_environment_dashboard(environment, product_filter)
                
                # Refresh the snapshot
                success = snapshot.refresh(generator, ttl_minutes=self.default_ttl)
                
                if success:
                    results['refreshed'] += 1
                    results['combinations'].append(snapshot.filter_key)
                else:
                    results['failed'] += 1
                    results['errors'].append(f"{snapshot.filter_key}: {snapshot.error_message}")
                
            except Exception as e:
                results['failed'] += 1
                results['errors'].append(f"{snapshot.filter_key}: {str(e)}")
        
        return results
    
    def _extract_param(self, filter_parts: list, param_prefix: str) -> Optional[str]:
        """Extract parameter from filter key parts"""
        for part in filter_parts:
            if part.startswith(f"{param_prefix}_"):
                value = part[len(f"{param_prefix}_"):]
                return value if value != 'None' else None
        return None
    
    def get_cache_statistics(self) -> Dict:
        """Get statistics about dashboard cache performance"""
        from django.db.models import Count, Avg, Max, Min
        
        from django.db.models import Q
        
        stats = DashboardSnapshot.objects.aggregate(
            total_snapshots=Count('id'),
            valid_snapshots=Count('id', filter=Q(is_valid=True)),
            avg_generation_time=Avg('generation_time'),
            max_generation_time=Max('generation_time'),
            min_generation_time=Min('generation_time'),
            avg_data_size=Avg('data_size')
        )
        
        # Count by dashboard type
        by_type = {}
        for dash_type in DashboardSnapshot.DashboardType.choices:
            count = DashboardSnapshot.objects.filter(dashboard_type=dash_type[0]).count()
            by_type[dash_type[1]] = count
        
        # Recent refresh logs
        recent_refreshes = DashboardRefreshLog.objects.filter(
            completed_at__isnull=False
        ).order_by('-started_at')[:5]
        
        return {
            'total_snapshots': stats['total_snapshots'] or 0,
            'valid_snapshots': stats['valid_snapshots'] or 0,
            'invalid_snapshots': (stats['total_snapshots'] or 0) - (stats['valid_snapshots'] or 0),
            'avg_generation_time': round(stats['avg_generation_time'] or 0, 3),
            'max_generation_time': round(stats['max_generation_time'] or 0, 3),
            'min_generation_time': round(stats['min_generation_time'] or 0, 3),
            'avg_data_size_kb': round((stats['avg_data_size'] or 0) / 1024, 1),
            'by_dashboard_type': by_type,
            'recent_refreshes': [
                {
                    'type': refresh.get_refresh_type_display(),
                    'started_at': refresh.started_at.isoformat(),
                    'duration': refresh.duration_seconds,
                    'success_rate': refresh.success_rate,
                    'snapshots_refreshed': refresh.snapshots_refreshed
                }
                for refresh in recent_refreshes
            ]
        }