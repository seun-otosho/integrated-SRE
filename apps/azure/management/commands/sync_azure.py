"""
Management command to sync Azure Application Insights and Log Analytics data
"""

import time
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.azure.models import AzureConfiguration
from apps.azure.services import AzureDataService
from apps.azure.client import AzureClient, AzureAuthenticationError, AzureAPIError


class Command(BaseCommand):
    help = 'Sync data from Azure Application Insights and Log Analytics'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--config',
            type=str,
            help='Specific configuration name to sync (if not provided, syncs all active configurations)'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force sync even if last sync was recent'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be synced without actually syncing'
        )
        parser.add_argument(
            '--test-connection',
            action='store_true',
            help='Test connection to Azure APIs without syncing data'
        )
        parser.add_argument(
            '--metrics-only',
            action='store_true',
            help='Sync only metrics data'
        )
        parser.add_argument(
            '--logs-only',
            action='store_true',
            help='Sync only log data'
        )
        parser.add_argument(
            '--resources-only',
            action='store_true',
            help='Sync only resource discovery'
        )
    
    def handle(self, *args, **options):
        self.verbosity = options['verbosity']
        self.dry_run = options['dry_run']
        
        try:
            if options['test_connection']:
                self._test_connections(options)
            else:
                self._sync_data(options)
                
        except (AzureAuthenticationError, AzureAPIError) as e:
            raise CommandError(f"Azure API Error: {e}")
        except Exception as e:
            raise CommandError(f"Sync failed: {e}")
    
    def _test_connections(self, options):
        """Test connections to Azure APIs"""
        self.stdout.write(self.style.HTTP_INFO("🔍 Testing Azure API connections..."))
        
        configs = self._get_configurations(options)
        
        if not configs:
            self.stdout.write(self.style.WARNING("No Azure configurations found"))
            return
        
        total_configs = len(configs)
        successful_tests = 0
        
        for config in configs:
            self.stdout.write(f"\n📋 Testing: {config.name}")
            
            try:
                client = AzureClient(config)
                result = client.test_connection()
                
                if result['success']:
                    self.stdout.write(self.style.SUCCESS(f"  ✅ Connection successful"))
                    self.stdout.write(f"  📊 Subscription: {result['subscription']['display_name']}")
                    self.stdout.write(f"  🔗 APIs tested: {', '.join(result['apis_tested'])}")
                    successful_tests += 1
                else:
                    self.stdout.write(self.style.ERROR(f"  ❌ Connection failed: {result['error']}"))
                
                client.close()
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ❌ Test failed: {e}"))
        
        # Summary
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(self.style.HTTP_INFO("CONNECTION TEST SUMMARY"))
        self.stdout.write(f"Total configurations: {total_configs}")
        self.stdout.write(f"Successful tests: {successful_tests}")
        self.stdout.write(f"Failed tests: {total_configs - successful_tests}")
        
        if successful_tests == total_configs:
            self.stdout.write(self.style.SUCCESS("🎉 All connections successful!"))
        else:
            self.stdout.write(self.style.WARNING(f"⚠️  {total_configs - successful_tests} connection(s) failed"))
    
    def _sync_data(self, options):
        """Sync Azure data"""
        if self.dry_run:
            self.stdout.write(self.style.HTTP_INFO("🧪 DRY RUN MODE - No actual syncing will occur"))
        
        self.stdout.write(self.style.HTTP_INFO("🔄 Starting Azure data sync..."))
        
        configs = self._get_configurations(options)
        
        if not configs:
            self.stdout.write(self.style.WARNING("No Azure configurations found"))
            return
        
        if self.dry_run:
            self._show_dry_run_info(configs, options)
            return
        
        # Initialize service
        service = AzureDataService()
        start_time = time.time()
        
        # Sync all configurations
        if len(configs) > 1:
            # Batch sync
            result = service.sync_all_configurations(force=options['force'])
            self._show_batch_results(result, time.time() - start_time)
        else:
            # Single configuration sync
            config = configs[0]
            self.stdout.write(f"📋 Syncing: {config.name}")
            
            try:
                result = service.sync_configuration(config)
                self._show_single_result(config, result, time.time() - start_time)
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ Sync failed for {config.name}: {e}"))
                raise
    
    def _get_configurations(self, options):
        """Get configurations to sync based on options"""
        if options['config']:
            try:
                config = AzureConfiguration.objects.get(name=options['config'], is_active=True)
                return [config]
            except AzureConfiguration.DoesNotExist:
                raise CommandError(f"Configuration '{options['config']}' not found or inactive")
        else:
            configs = AzureConfiguration.objects.filter(is_active=True)
            
            if not options['force']:
                # Only get configs that need syncing
                configs = [config for config in configs if config.needs_sync]
            
            return list(configs)
    
    def _show_dry_run_info(self, configs, options):
        """Show what would be synced in dry run mode"""
        self.stdout.write(f"Would sync {len(configs)} configuration(s):")
        
        for config in configs:
            self.stdout.write(f"\n📋 {config.name} ({config.get_config_type_display()})")
            self.stdout.write(f"  🔗 Subscription: {config.subscription_id}")
            
            if config.resource_group:
                self.stdout.write(f"  📁 Resource Group: {config.resource_group}")
            
            self.stdout.write(f"  🌍 Environment: {config.environment_filter}")
            
            if config.workspace_id:
                self.stdout.write(f"  📊 Log Analytics: {config.workspace_id}")
            
            if config.application_id:
                self.stdout.write(f"  📱 App Insights: {config.application_id}")
            
            # Show sync type
            sync_types = []
            if not options['metrics_only'] and not options['logs_only']:
                sync_types.append('resources')
            if not options['logs_only'] and not options['resources_only']:
                sync_types.append('metrics')
            if config.workspace_id and not options['metrics_only'] and not options['resources_only']:
                sync_types.append('logs')
            
            self.stdout.write(f"  🔄 Sync types: {', '.join(sync_types)}")
            
            last_sync = config.last_sync.strftime('%Y-%m-%d %H:%M') if config.last_sync else 'Never'
            self.stdout.write(f"  ⏰ Last sync: {last_sync}")
    
    def _show_single_result(self, config, result, duration):
        """Show results for single configuration sync"""
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(self.style.HTTP_INFO("SYNC RESULTS"))
        self.stdout.write(f"Configuration: {config.name}")
        self.stdout.write(f"Duration: {duration:.1f} seconds")
        
        if result['success']:
            self.stdout.write(self.style.SUCCESS("Status: ✅ Success"))
            self.stdout.write(f"Resources processed: {result['resources_processed']}")
            self.stdout.write(f"Metrics collected: {result['metrics_collected']}")
            self.stdout.write(f"Logs collected: {result['logs_collected']}")
        else:
            self.stdout.write(self.style.ERROR("Status: ❌ Failed"))
    
    def _show_batch_results(self, result, duration):
        """Show results for batch sync"""
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(self.style.HTTP_INFO("BATCH SYNC RESULTS"))
        self.stdout.write(f"Duration: {duration:.1f} seconds")
        self.stdout.write(f"Configurations processed: {result['configurations_processed']}")
        self.stdout.write(f"Configurations failed: {result['configurations_failed']}")
        self.stdout.write(f"Total resources: {result['total_resources']}")
        self.stdout.write(f"Total metrics: {result['total_metrics']}")
        self.stdout.write(f"Total logs: {result['total_logs']}")
        
        if result['configurations_failed'] == 0:
            self.stdout.write(self.style.SUCCESS("🎉 All configurations synced successfully!"))
        else:
            self.stdout.write(self.style.WARNING(f"⚠️  {result['configurations_failed']} configuration(s) failed"))
        
        # Show details if verbose
        if self.verbosity >= 2 and result['details']:
            self.stdout.write(f"\nDETAILS BY CONFIGURATION:")
            for detail in result['details']:
                config_name = detail['configuration']
                config_result = detail['result']
                status = "✅" if config_result['success'] else "❌"
                self.stdout.write(f"  {status} {config_name}: "
                                f"R:{config_result['resources_processed']}, "
                                f"M:{config_result['metrics_collected']}, "
                                f"L:{config_result['logs_collected']}")
        
        # Show errors if any
        if result['errors']:
            self.stdout.write(self.style.ERROR(f"\nERRORS:"))
            for error in result['errors']:
                self.stdout.write(self.style.ERROR(f"  • {error}"))
    
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