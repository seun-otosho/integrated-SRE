from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from datetime import timedelta

from apps.dashboards.services_cached import CachedDashboardService
from apps.dashboards.models_cache import DashboardSnapshot


class Command(BaseCommand):
    help = 'Refresh dashboard cache for instant loading'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dashboard',
            type=str,
            choices=['executive', 'product', 'environment'],
            help='Specific dashboard type to refresh (if not provided, refreshes all)',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force refresh all snapshots, even if not expired',
        )
        parser.add_argument(
            '--expired-only',
            action='store_true',
            help='Only refresh expired snapshots',
        )
        parser.add_argument(
            '--preload-common',
            action='store_true',
            help='Preload common dashboard combinations',
        )
        parser.add_argument(
            '--stats',
            action='store_true',
            help='Show cache statistics',
        )
        parser.add_argument(
            '--cleanup',
            action='store_true',
            help='Clean up old snapshots and logs',
        )

    def handle(self, *args, **options):
        dashboard_type = options.get('dashboard')
        force = options.get('force', False)
        expired_only = options.get('expired_only', False)
        preload_common = options.get('preload_common', False)
        show_stats = options.get('stats', False)
        cleanup = options.get('cleanup', False)

        service = CachedDashboardService()

        if show_stats:
            self._show_statistics(service)
            return

        if cleanup:
            self._cleanup_old_data()
            return

        if preload_common:
            self._preload_common_combinations(service)
            return

        # Main refresh operation
        self.stdout.write(f'🔄 Starting dashboard cache refresh...')
        
        if force:
            self.stdout.write(self.style.WARNING('FORCE MODE - Refreshing all snapshots'))
        elif expired_only:
            self.stdout.write('EXPIRED-ONLY MODE - Refreshing only expired snapshots')
        
        if dashboard_type:
            self.stdout.write(f'Target: {dashboard_type} dashboard only')
        else:
            self.stdout.write('Target: All dashboard types')

        # Perform refresh
        start_time = timezone.now()
        results = service.refresh_dashboard_cache(dashboard_type, force)
        end_time = timezone.now()
        
        duration = (end_time - start_time).total_seconds()

        # Display results
        self.stdout.write('\n' + '='*60)
        self.stdout.write('REFRESH RESULTS')
        self.stdout.write('='*60)
        
        self.stdout.write(f'Duration: {duration:.2f} seconds')
        self.stdout.write(f'Snapshots refreshed: {results["snapshots_refreshed"]}')
        self.stdout.write(f'Snapshots failed: {results["snapshots_failed"]}')
        
        if results['details']:
            self.stdout.write('\nDETAILS BY DASHBOARD TYPE:')
            for detail in results['details']:
                dashboard = detail['dashboard_type']
                refreshed = detail['refreshed']
                failed = detail['failed']
                combinations = detail['combinations']
                
                self.stdout.write(f'  {dashboard.title()}: {refreshed} refreshed, {failed} failed')
                if combinations:
                    for combo in combinations:
                        self.stdout.write(f'    ✅ {combo}')

        if results['errors']:
            self.stdout.write('\nERRORS:')
            for error in results['errors'][:10]:  # Show first 10 errors
                self.stdout.write(self.style.ERROR(f'  ❌ {error}'))
            
            if len(results['errors']) > 10:
                self.stdout.write(f'  ... and {len(results["errors"]) - 10} more errors')

        # Final status
        if results['snapshots_refreshed'] > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n🎉 Successfully refreshed {results["snapshots_refreshed"]} dashboard snapshots!'
                )
            )
            self.stdout.write('Dashboard pages will now load instantly! ⚡')
        elif results['snapshots_failed'] > 0:
            self.stdout.write(
                self.style.ERROR(
                    f'\n❌ All {results["snapshots_failed"]} refresh attempts failed.'
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    '\n📝 No snapshots needed refreshing. All cache is up to date.'
                )
            )

    def _show_statistics(self, service):
        """Display cache statistics"""
        stats = service.get_cache_statistics()
        
        self.stdout.write('📊 DASHBOARD CACHE STATISTICS')
        self.stdout.write('='*50)
        
        self.stdout.write(f'Total snapshots: {stats["total_snapshots"]}')
        self.stdout.write(f'Valid snapshots: {stats["valid_snapshots"]}')
        self.stdout.write(f'Invalid snapshots: {stats["invalid_snapshots"]}')
        
        self.stdout.write(f'\nPerformance:')
        self.stdout.write(f'  Average generation time: {stats["avg_generation_time"]}s')
        self.stdout.write(f'  Max generation time: {stats["max_generation_time"]}s')
        self.stdout.write(f'  Min generation time: {stats["min_generation_time"]}s')
        self.stdout.write(f'  Average data size: {stats["avg_data_size_kb"]} KB')
        
        if stats['by_dashboard_type']:
            self.stdout.write(f'\nBy Dashboard Type:')
            for dashboard_type, count in stats['by_dashboard_type'].items():
                self.stdout.write(f'  {dashboard_type}: {count} snapshots')
        
        if stats['recent_refreshes']:
            self.stdout.write(f'\nRecent Refreshes:')
            for refresh in stats['recent_refreshes']:
                duration = f"{refresh['duration']:.1f}s" if refresh['duration'] else 'N/A'
                self.stdout.write(
                    f"  {refresh['type']}: {refresh['snapshots_refreshed']} snapshots "
                    f"({refresh['success_rate']:.1f}% success) in {duration}"
                )

    def _preload_common_combinations(self, service):
        """Preload common dashboard combinations"""
        self.stdout.write('🚀 Preloading common dashboard combinations...')
        
        # Get available products and environments
        from apps.products.models import Product
        from apps.sentry.models import SentryIssue
        
        products = Product.objects.all()[:5]  # Top 5 products
        environments = SentryIssue.objects.exclude(
            environment__isnull=True
        ).exclude(
            environment__exact=''
        ).values_list('environment', flat=True).distinct()[:3]  # Top 3 environments
        
        combinations = [
            # Executive dashboard combinations
            ('executive', None, None),  # All products, all environments
            ('executive', None, 'production'),  # All products, production only
        ]
        
        # Add product-specific combinations
        for product in products:
            combinations.extend([
                ('product', product.id, None),  # Product overview
                ('product', product.id, 'production'),  # Product in production
            ])
        
        # Add environment combinations
        for env in environments:
            combinations.append(('environment', env, None))
        
        self.stdout.write(f'Will preload {len(combinations)} combinations...')
        
        success_count = 0
        for dashboard_type, param1, param2 in combinations:
            try:
                if dashboard_type == 'executive':
                    data, was_generated = service.get_executive_overview(param1, param2)
                elif dashboard_type == 'product':
                    data, was_generated = service.get_product_health_dashboard(param1, param2)
                elif dashboard_type == 'environment':
                    data, was_generated = service.get_environment_dashboard(param1, param2)
                
                status = 'GENERATED' if was_generated else 'CACHED'
                key = service._build_filter_key(dashboard_type, param1, param2)
                self.stdout.write(f'  ✅ {key}: {status}')
                success_count += 1
                
            except Exception as e:
                key = service._build_filter_key(dashboard_type, param1, param2)
                self.stdout.write(self.style.ERROR(f'  ❌ {key}: {str(e)}'))
        
        self.stdout.write(
            self.style.SUCCESS(
                f'\n🎉 Preloaded {success_count}/{len(combinations)} dashboard combinations!'
            )
        )

    def _cleanup_old_data(self):
        """Clean up old snapshots and logs"""
        self.stdout.write('🧹 Cleaning up old dashboard data...')
        
        # Remove snapshots older than 7 days
        from django.utils import timezone
        cutoff_date = timezone.now() - timedelta(days=7)
        
        old_snapshots = DashboardSnapshot.objects.filter(generated_at__lt=cutoff_date)
        snapshot_count = old_snapshots.count()
        old_snapshots.delete()
        
        # Remove logs older than 30 days
        from apps.dashboards.models_cache import DashboardRefreshLog
        log_cutoff = timezone.now() - timedelta(days=30)
        old_logs = DashboardRefreshLog.objects.filter(started_at__lt=log_cutoff)
        log_count = old_logs.count()
        old_logs.delete()
        
        self.stdout.write(f'Removed {snapshot_count} old snapshots')
        self.stdout.write(f'Removed {log_count} old refresh logs')
        
        self.stdout.write(self.style.SUCCESS('🎉 Cleanup completed!'))