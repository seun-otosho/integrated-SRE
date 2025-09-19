"""
Management command to backfill Azure metrics data for historical analysis
"""

import time
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.db import transaction

from apps.azure.models import AzureConfiguration, AzureResource, AzureMetric
from apps.azure.services import AzureDataService
from apps.azure.client import AzureClient, AzureAuthenticationError, AzureAPIError


class Command(BaseCommand):
    help = 'Backfill Azure metrics data for historical analysis'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Number of days to backfill (default: 30, max: 90)'
        )
        parser.add_argument(
            '--config',
            type=str,
            help='Specific configuration name to backfill (if not provided, backfills all active configurations)'
        )
        parser.add_argument(
            '--resource-type',
            type=str,
            help='Specific resource type to backfill (e.g., webapp, keyvault)'
        )
        parser.add_argument(
            '--chunk-days',
            type=int,
            default=7,
            help='Days per chunk to avoid API timeouts (default: 7)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be backfilled without actually doing it'
        )
        parser.add_argument(
            '--skip-existing',
            action='store_true',
            help='Skip time periods that already have data'
        )
        parser.add_argument(
            '--delay',
            type=float,
            default=1.0,
            help='Delay between API calls in seconds (default: 1.0)'
        )
    
    def handle(self, *args, **options):
        self.verbosity = options['verbosity']
        self.dry_run = options['dry_run']
        
        # Validate inputs
        days = options['days']
        if days > 90:
            raise CommandError("Cannot backfill more than 90 days (Azure retention limit)")
        
        chunk_days = options['chunk_days']
        if chunk_days > days:
            chunk_days = days
        
        try:
            if self.dry_run:
                self.stdout.write(self.style.HTTP_INFO("🧪 DRY RUN MODE - No actual backfilling will occur"))
            
            self.stdout.write(self.style.HTTP_INFO(f"🔄 Starting Azure metrics backfill for {days} days..."))
            
            self._backfill_metrics(options)
            
        except (AzureAuthenticationError, AzureAPIError) as e:
            raise CommandError(f"Azure API Error: {e}")
        except Exception as e:
            raise CommandError(f"Backfill failed: {e}")
    
    def _backfill_metrics(self, options):
        """Main backfill logic"""
        days = options['days']
        chunk_days = options['chunk_days']
        delay = options['delay']
        
        # Get configurations
        configs = self._get_configurations(options)
        if not configs:
            self.stdout.write(self.style.WARNING("No Azure configurations found"))
            return
        
        # Calculate time periods
        end_time = timezone.now()
        start_time = end_time - timedelta(days=days)
        
        self.stdout.write(f"📅 Backfill period: {start_time.strftime('%Y-%m-%d')} to {end_time.strftime('%Y-%m-%d')}")
        self.stdout.write(f"📦 Processing {len(configs)} configuration(s)")
        
        total_metrics_collected = 0
        total_api_calls = 0
        
        for config in configs:
            self.stdout.write(f"\n📋 Processing: {config.name}")
            
            # Get resources for this config
            resources = self._get_resources(config, options)
            self.stdout.write(f"   Resources to process: {len(resources)}")
            
            if self.dry_run:
                self._show_dry_run_info(config, resources, start_time, end_time, chunk_days)
                continue
            
            client = None
            try:
                client = AzureClient(config)
                service = AzureDataService()
                
                # Process in chunks to avoid API timeouts
                current_start = start_time
                while current_start < end_time:
                    current_end = min(current_start + timedelta(days=chunk_days), end_time)
                    
                    chunk_metrics, chunk_calls = self._process_time_chunk(
                        client, service, resources, current_start, current_end, options
                    )
                    
                    total_metrics_collected += chunk_metrics
                    total_api_calls += chunk_calls
                    
                    current_start = current_end
                    
                    # Rate limiting
                    if delay > 0:
                        time.sleep(delay)
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ Failed to process {config.name}: {e}"))
            finally:
                if client:
                    client.close()
        
        # Summary
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(self.style.HTTP_INFO("BACKFILL SUMMARY"))
        self.stdout.write(f"Total metrics collected: {total_metrics_collected}")
        self.stdout.write(f"Total API calls made: {total_api_calls}")
        self.stdout.write(f"Average metrics per call: {total_metrics_collected / max(total_api_calls, 1):.1f}")
        
        if total_metrics_collected > 0:
            self.stdout.write(self.style.SUCCESS("🎉 Backfill completed successfully!"))
        else:
            self.stdout.write(self.style.WARNING("⚠️  No metrics were collected"))
    
    def _get_configurations(self, options):
        """Get Azure configurations to process"""
        if options['config']:
            try:
                config = AzureConfiguration.objects.get(name=options['config'], is_active=True)
                return [config]
            except AzureConfiguration.DoesNotExist:
                raise CommandError(f"Configuration '{options['config']}' not found or inactive")
        else:
            return list(AzureConfiguration.objects.filter(is_active=True))
    
    def _get_resources(self, config, options):
        """Get resources to process for a configuration"""
        resources = AzureResource.objects.filter(
            configuration=config,
            is_monitored=True
        )
        
        if options['resource_type']:
            resources = resources.filter(resource_type=options['resource_type'])
        
        # Only get resources that have metrics defined
        service = AzureDataService()
        filtered_resources = []
        
        for resource in resources:
            metrics = service._get_metrics_for_resource_type(resource.resource_type)
            if metrics:
                filtered_resources.append(resource)
        
        return filtered_resources
    
    def _process_time_chunk(self, client, service, resources, start_time, end_time, options):
        """Process a chunk of time for all resources"""
        chunk_start = time.time()
        metrics_collected = 0
        api_calls = 0
        
        self.stdout.write(f"   ⏱️  Processing {start_time.strftime('%Y-%m-%d')} to {end_time.strftime('%Y-%m-%d')}")
        
        for resource in resources:
            if self.verbosity >= 2:
                self.stdout.write(f"      📦 {resource.name} ({resource.get_resource_type_display()})")
            
            try:
                # Check if we should skip existing data
                if options['skip_existing']:
                    existing_count = AzureMetric.objects.filter(
                        resource=resource,
                        timestamp__gte=start_time,
                        timestamp__lt=end_time
                    ).count()
                    
                    if existing_count > 0:
                        if self.verbosity >= 2:
                            self.stdout.write(f"         ⏩ Skipping - {existing_count} existing metrics")
                        continue
                
                # Get metrics for this resource type
                expected_metrics = service._get_metrics_for_resource_type(resource.resource_type)
                if not expected_metrics:
                    continue
                
                # Try to get metrics from Azure
                try:
                    metrics_data = client.get_resource_metrics(
                        resource.resource_id,
                        expected_metrics,
                        start_time,
                        end_time,
                        'PT1H'  # 1 hour intervals
                    )
                    api_calls += 1
                    
                    # Process and store metrics
                    processed_count = self._store_metrics_data(resource, metrics_data, service)
                    metrics_collected += processed_count
                    
                    if self.verbosity >= 2:
                        self.stdout.write(f"         ✅ {processed_count} metrics collected")
                
                except Exception as e:
                    if self.verbosity >= 2:
                        self.stdout.write(f"         ❌ API error: {str(e)[:100]}...")
            
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"      ⚠️  Error processing {resource.name}: {e}"))
        
        chunk_duration = time.time() - chunk_start
        self.stdout.write(f"   📊 Chunk result: {metrics_collected} metrics in {chunk_duration:.1f}s")
        
        return metrics_collected, api_calls
    
    def _store_metrics_data(self, resource, metrics_data, service):
        """Store metrics data in the database"""
        metrics_count = 0
        
        with transaction.atomic():
            for metric in metrics_data.get('value', []):
                metric_name = metric['name']['value']
                namespace = metric.get('type', 'Unknown')
                unit = metric['unit']
                
                for timeseries in metric.get('timeseries', []):
                    for data_point in timeseries.get('data', []):
                        if 'average' in data_point and data_point['average'] is not None:
                            # Parse timestamp
                            timestamp_str = data_point['timeStamp'].replace('Z', '+00:00')
                            timestamp = datetime.fromisoformat(timestamp_str)
                            
                            # Create or update metric
                            metric_obj, created = AzureMetric.objects.get_or_create(
                                resource=resource,
                                metric_name=metric_name,
                                timestamp=timestamp,
                                defaults={
                                    'metric_type': service._categorize_metric(metric_name),
                                    'namespace': namespace,
                                    'value': data_point['average'],
                                    'unit': unit,
                                    'aggregation_type': 'Average',
                                    'dimensions': timeseries.get('metadatavalues', {}),
                                    'severity': service._assess_metric_severity(metric_name, data_point['average'])
                                }
                            )
                            
                            if created:
                                metrics_count += 1
        
        return metrics_count
    
    def _show_dry_run_info(self, config, resources, start_time, end_time, chunk_days):
        """Show what would be processed in dry run mode"""
        self.stdout.write(f"   📋 Configuration: {config.name}")
        self.stdout.write(f"   📅 Time range: {start_time.strftime('%Y-%m-%d')} to {end_time.strftime('%Y-%m-%d')}")
        self.stdout.write(f"   📦 Resources: {len(resources)}")
        self.stdout.write(f"   🔄 Chunk size: {chunk_days} days")
        
        if self.verbosity >= 2:
            service = AzureDataService()
            total_expected_metrics = 0
            
            for resource in resources:
                metrics = service._get_metrics_for_resource_type(resource.resource_type)
                expected_points = len(metrics) * (end_time - start_time).days * 24  # Hourly data
                total_expected_metrics += expected_points
                
                self.stdout.write(f"      📦 {resource.name}: ~{expected_points} metrics expected")
            
            self.stdout.write(f"   📊 Total expected metrics: ~{total_expected_metrics}")
        
        # Calculate chunks
        total_days = (end_time - start_time).days
        chunks = (total_days + chunk_days - 1) // chunk_days
        self.stdout.write(f"   🧩 Will process in {chunks} chunk(s)")
    
    def _format_duration(self, seconds):
        """Format duration in human readable format"""
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            remaining_seconds = seconds % 60
            return f"{minutes}m {remaining_seconds:.0f}s"
        else:
            hours = int(seconds // 3600)
            remaining_minutes = int((seconds % 3600) // 60)
            return f"{hours}h {remaining_minutes}m"