from django.db import models
from django.utils import timezone
from datetime import timedelta
import json


class DashboardSnapshot(models.Model):
    """Pre-computed dashboard data for instant loading"""
    
    class DashboardType(models.TextChoices):
        EXECUTIVE = 'executive', 'Executive Overview'
        PRODUCT = 'product', 'Product Health'
        ENVIRONMENT = 'environment', 'Environment Status'
        
    dashboard_type = models.CharField(max_length=20, choices=DashboardType.choices)
    filter_key = models.CharField(
        max_length=200, 
        help_text="Unique key for filter combination (e.g., 'product_5_env_production')"
    )
    
    # Pre-computed data
    data = models.JSONField(help_text="Complete dashboard data ready for display")
    
    # Metadata
    generated_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(help_text="When this snapshot should be refreshed")
    generation_time = models.FloatField(help_text="Time taken to generate this snapshot (seconds)")
    
    # Statistics
    data_size = models.PositiveIntegerField(default=0, help_text="Size of JSON data in bytes")
    source_record_count = models.PositiveIntegerField(default=0, help_text="Number of source records processed")
    
    # Status
    is_valid = models.BooleanField(default=True, help_text="Whether this snapshot is still valid")
    error_message = models.TextField(blank=True, help_text="Error message if generation failed")
    
    class Meta:
        db_table = 'dashboard_snapshots'
        verbose_name = 'Dashboard Snapshot'
        verbose_name_plural = 'Dashboard Snapshots'
        unique_together = ['dashboard_type', 'filter_key']
        indexes = [
            models.Index(fields=['dashboard_type', 'filter_key']),
            models.Index(fields=['expires_at']),
            models.Index(fields=['generated_at']),
        ]
        ordering = ['-generated_at']
    
    def __str__(self):
        return f"{self.get_dashboard_type_display()} - {self.filter_key} ({self.generated_at})"
    
    @property
    def is_expired(self):
        """Check if this snapshot has expired"""
        return timezone.now() > self.expires_at
    
    @property
    def age_minutes(self):
        """Get age of snapshot in minutes"""
        return (timezone.now() - self.generated_at).total_seconds() / 60
    
    @property
    def time_until_expiry(self):
        """Get time until expiry in minutes"""
        if self.is_expired:
            return 0
        return (self.expires_at - timezone.now()).total_seconds() / 60
    
    @classmethod
    def get_or_generate(cls, dashboard_type, filter_key, generator_func, ttl_minutes=30):
        """Get existing snapshot or generate new one"""
        try:
            snapshot = cls.objects.get(
                dashboard_type=dashboard_type,
                filter_key=filter_key,
                is_valid=True
            )
            
            if not snapshot.is_expired:
                return snapshot, False  # Found valid cache
            
        except cls.DoesNotExist:
            snapshot = None
        
        # Generate new snapshot
        import time
        start_time = time.time()
        
        try:
            data = generator_func()
            end_time = time.time()
            generation_time = end_time - start_time
            
            # Create or update snapshot
            snapshot, created = cls.objects.update_or_create(
                dashboard_type=dashboard_type,
                filter_key=filter_key,
                defaults={
                    'data': data,
                    'expires_at': timezone.now() + timedelta(minutes=ttl_minutes),
                    'generation_time': generation_time,
                    'data_size': len(json.dumps(data)),
                    'source_record_count': cls._count_source_records(data),
                    'is_valid': True,
                    'error_message': ''
                }
            )
            
            return snapshot, True  # Generated new cache
            
        except Exception as e:
            # Store error information
            cls.objects.update_or_create(
                dashboard_type=dashboard_type,
                filter_key=filter_key,
                defaults={
                    'data': {},
                    'expires_at': timezone.now() + timedelta(minutes=5),  # Retry sooner on error
                    'generation_time': time.time() - start_time,
                    'data_size': 0,
                    'source_record_count': 0,
                    'is_valid': False,
                    'error_message': str(e)
                }
            )
            raise
    
    @staticmethod
    def _count_source_records(data):
        """Count the number of source records in the data"""
        count = 0
        
        # Count items in various data structures
        for key, value in data.items():
            if isinstance(value, list):
                count += len(value)
            elif isinstance(value, dict) and 'total' in value:
                count += value.get('total', 0)
        
        return count
    
    def refresh(self, generator_func, ttl_minutes=30):
        """Refresh this snapshot with new data"""
        import time
        start_time = time.time()
        
        try:
            data = generator_func()
            end_time = time.time()
            
            self.data = data
            self.expires_at = timezone.now() + timedelta(minutes=ttl_minutes)
            self.generation_time = end_time - start_time
            self.data_size = len(json.dumps(data))
            self.source_record_count = self._count_source_records(data)
            self.is_valid = True
            self.error_message = ''
            self.save()
            
            return True
            
        except Exception as e:
            self.is_valid = False
            self.error_message = str(e)
            self.expires_at = timezone.now() + timedelta(minutes=5)
            self.save()
            return False


class DashboardRefreshLog(models.Model):
    """Log of dashboard refresh operations"""
    
    class RefreshType(models.TextChoices):
        SCHEDULED = 'scheduled', 'Scheduled Refresh'
        ON_DEMAND = 'on_demand', 'On-Demand Refresh'
        EXPIRED_ONLY = 'expired_only', 'Expired Only Refresh'
        FORCE_ALL = 'force_all', 'Force Refresh All'
    
    refresh_type = models.CharField(max_length=20, choices=RefreshType.choices)
    dashboard_types = models.JSONField(default=list, help_text="List of dashboard types refreshed")
    
    # Results
    snapshots_refreshed = models.PositiveIntegerField(default=0)
    snapshots_failed = models.PositiveIntegerField(default=0)
    total_generation_time = models.FloatField(default=0)
    
    # Timing
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Error tracking
    errors = models.JSONField(default=list, blank=True)
    
    class Meta:
        db_table = 'dashboard_refresh_logs'
        verbose_name = 'Dashboard Refresh Log'
        verbose_name_plural = 'Dashboard Refresh Logs'
        ordering = ['-started_at']
    
    def __str__(self):
        return f"{self.get_refresh_type_display()} - {self.started_at}"
    
    @property
    def duration_seconds(self):
        """Get duration of refresh operation"""
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
    
    @property
    def success_rate(self):
        """Get success rate percentage"""
        total = self.snapshots_refreshed + self.snapshots_failed
        if total > 0:
            return (self.snapshots_refreshed / total) * 100
        return 0