from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from datetime import timedelta

from apps.sentry.models import SentryOrganization
from apps.sentry.services import sync_organization, sync_all_organizations


class Command(BaseCommand):
    help = 'Sync data from Sentry API'

    def add_arguments(self, parser):
        parser.add_argument(
            '--org',
            type=str,
            help='Organization slug to sync (if not provided, syncs all enabled organizations)',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force sync even if last sync was recent',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be synced without actually syncing',
        )
        parser.add_argument(
            '--link-jira',
            action='store_true',
            help='Automatically link synced issues to JIRA tickets based on annotations',
        )
        parser.add_argument(
            '--skip-existing-links',
            action='store_true',
            help='Skip JIRA linking for issues that already have links (faster processing)',
        )
        parser.add_argument(
            '--fuzzy-match',
            action='store_true',
            help='Also run fuzzy matching to find implicit JIRA connections',
        )

    def handle(self, *args, **options):
        org_slug = options.get('org')
        force = options.get('force', False)
        dry_run = options.get('dry_run', False)
        link_jira = options.get('link_jira', False)
        skip_existing_links = options.get('skip_existing_links', False)

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No actual syncing will occur'))
        
        if link_jira:
            self.stdout.write(self.style.SUCCESS('JIRA LINKING ENABLED - Will auto-link issues to JIRA tickets'))
            if skip_existing_links:
                self.stdout.write(self.style.SUCCESS('SKIP-EXISTING-LINKS - Will skip issues with existing JIRA links'))
        
        fuzzy_match = options.get('fuzzy_match', False)
        if fuzzy_match:
            self.stdout.write(self.style.SUCCESS('FUZZY MATCHING ENABLED - Will discover implicit JIRA connections'))

        if org_slug:
            # Sync specific organization
            try:
                org = SentryOrganization.objects.get(slug=org_slug)
                if not org.sync_enabled and not force:
                    raise CommandError(f'Organization {org_slug} has sync disabled. Use --force to override.')
                
                if not force and org.last_sync:
                    time_since_sync = timezone.now() - org.last_sync
                    min_interval = timedelta(hours=org.sync_interval_hours)
                    if time_since_sync < min_interval:
                        self.stdout.write(
                            self.style.WARNING(
                                f'Organization {org_slug} was synced {time_since_sync} ago. '
                                f'Minimum interval is {org.sync_interval_hours}h. Use --force to override.'
                            )
                        )
                        return

                if dry_run:
                    self.stdout.write(f'Would sync organization: {org.name} ({org.slug})')
                    return

                self.stdout.write(f'Syncing organization: {org.name} ({org.slug})')
                sync_log = sync_organization(org.id)
                
                if sync_log:
                    if sync_log.status == 'success':
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'Successfully synced {org.slug}: '
                                f'{sync_log.projects_synced} projects, '
                                f'{sync_log.issues_synced} issues, '
                                f'{sync_log.events_synced} events '
                                f'({sync_log.duration_seconds:.1f}s)'
                            )
                        )
                        
                        # Auto-link JIRA tickets if requested
                        if link_jira and not dry_run:
                            self._link_jira_tickets_for_organization(org, skip_existing_links, fuzzy_match)
                    else:
                        self.stdout.write(
                            self.style.ERROR(
                                f'Sync failed for {org.slug}: {sync_log.error_message}'
                            )
                        )
                else:
                    self.stdout.write(self.style.ERROR(f'Failed to create sync log for {org.slug}'))
                    
            except SentryOrganization.DoesNotExist:
                raise CommandError(f'Organization "{org_slug}" does not exist')
        
        else:
            # Sync all enabled organizations
            organizations = SentryOrganization.objects.filter(sync_enabled=True)
            
            if not force:
                # Filter organizations that need syncing
                eligible_orgs = []
                for org in organizations:
                    if not org.last_sync:
                        eligible_orgs.append(org)
                    else:
                        time_since_sync = timezone.now() - org.last_sync
                        min_interval = timedelta(hours=org.sync_interval_hours)
                        if time_since_sync >= min_interval:
                            eligible_orgs.append(org)
                organizations = eligible_orgs

            if not organizations:
                self.stdout.write(self.style.WARNING('No organizations need syncing'))
                return

            if dry_run:
                self.stdout.write(f'Would sync {len(organizations)} organizations:')
                for org in organizations:
                    last_sync = org.last_sync.strftime('%Y-%m-%d %H:%M') if org.last_sync else 'Never'
                    self.stdout.write(f'  - {org.name} ({org.slug}) - Last sync: {last_sync}')
                return

            self.stdout.write(f'Syncing {len(organizations)} organizations...')
            
            sync_logs = sync_all_organizations()
            
            success_count = 0
            failed_count = 0
            
            for sync_log in sync_logs:
                if sync_log.status == 'success':
                    success_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'✓ {sync_log.organization.slug}: '
                            f'{sync_log.projects_synced}p, '
                            f'{sync_log.issues_synced}i, '
                            f'{sync_log.events_synced}e '
                            f'({sync_log.duration_seconds:.1f}s)'
                        )
                    )
                else:
                    failed_count += 1
                    self.stdout.write(
                        self.style.ERROR(
                            f'✗ {sync_log.organization.slug}: {sync_log.error_message}'
                        )
                    )
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'\nSync completed: {success_count} successful, {failed_count} failed'
                )
            )
            
            # Auto-link JIRA tickets for successful syncs if requested
            if link_jira and not dry_run and success_count > 0:
                self.stdout.write('\n' + '='*60)
                self.stdout.write('JIRA AUTO-LINKING PHASE')
                self.stdout.write('='*60)
                
                successful_orgs = [log.organization for log in sync_logs if log.status == 'success']
                for org in successful_orgs:
                    self._link_jira_tickets_for_organization(org, skip_existing_links, fuzzy_match)
    
    def _link_jira_tickets_for_organization(self, organization, skip_existing_links, fuzzy_match=False):
        """Link JIRA tickets for a specific organization after sync"""
        try:
            from apps.sentry.services_jira_linking import SentryJiraLinkingService
            
            self.stdout.write(f'🔗 Linking JIRA tickets for {organization.name}...')
            
            service = SentryJiraLinkingService()
            
            # Link issues for this organization with reasonable limits
            summary = service.scan_and_link_all_sentry_issues(
                organization=organization, 
                limit=100,  # Process up to 100 issues per sync
                skip_linked=skip_existing_links
            )
            
            # Report results
            if summary['total_links_created'] > 0:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'   ✅ Created {summary["total_links_created"]} JIRA links '
                        f'from {summary["issues_with_jira_links"]} issues'
                    )
                )
            elif summary['issues_with_jira_links'] > 0:
                self.stdout.write(
                    self.style.WARNING(
                        f'   ⚠️ Found {summary["issues_with_jira_links"]} issues with annotations '
                        f'but no new links created (may already exist)'
                    )
                )
            else:
                self.stdout.write(f'   📝 No JIRA annotations found in recent issues')
            
            # Report any critical errors (but don't show all the "no annotations" errors)
            critical_errors = [e for e in summary['errors'] if 'No JIRA tickets found' not in e]
            if critical_errors:
                for error in critical_errors[:3]:  # Show first 3 critical errors
                    self.stdout.write(self.style.WARNING(f'   ⚠️ {error}'))
                
                if len(critical_errors) > 3:
                    self.stdout.write(f'   ... and {len(critical_errors) - 3} more issues')
            
            if summary.get('issues_skipped', 0) > 0:
                self.stdout.write(f'   ⏭️ Skipped {summary["issues_skipped"]} already-linked issues')
            
            # Run fuzzy matching if requested
            if fuzzy_match:
                self.stdout.write(f'🔍 Running fuzzy matching for {organization.name}...')
                try:
                    from apps.sentry.services_jira_fuzzy_matching import SentryJiraFuzzyMatchingService
                    
                    fuzzy_service = SentryJiraFuzzyMatchingService()
                    
                    # Run fuzzy matching with conservative settings for sync integration
                    fuzzy_results = fuzzy_service.scan_and_suggest_matches(
                        organization=organization,
                        limit=50,  # Limit for sync integration
                        similarity_threshold=0.8  # Higher threshold for auto-sync
                    )
                    
                    if fuzzy_results['suggestions']:
                        # Auto-create high confidence fuzzy matches
                        link_results = fuzzy_service.create_links_from_suggestions(
                            fuzzy_results['suggestions'],
                            auto_create_high_confidence=True,
                            min_confidence_score=0.85
                        )
                        
                        if link_results['links_created'] > 0:
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f'   🎯 Fuzzy matching created {link_results["links_created"]} additional links'
                                )
                            )
                        else:
                            self.stdout.write(f'   📝 Fuzzy matching found potential matches but no auto-links created')
                    else:
                        self.stdout.write(f'   📝 No fuzzy matches found above threshold')
                        
                except ImportError:
                    self.stdout.write(f'   ⚠️ Fuzzy matching not available (service not found)')
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'   ⚠️ Fuzzy matching failed: {str(e)}'))
                
        except ImportError:
            self.stdout.write(
                self.style.WARNING(
                    f'   ⚠️ JIRA linking not available for {organization.name} '
                    f'(JIRA app not installed or services not available)'
                )
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'   ❌ JIRA linking failed for {organization.name}: {str(e)}')
            )
