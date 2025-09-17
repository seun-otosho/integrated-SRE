from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from apps.sentry.models import SentryOrganization
from apps.sentry.services_jira_linking import SentryJiraLinkingService


class Command(BaseCommand):
    help = 'Automatically link Sentry issues to JIRA tickets based on annotations'

    def add_arguments(self, parser):
        parser.add_argument(
            '--org',
            type=str,
            help='Organization slug to process (if not provided, processes all)',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=100,
            help='Maximum number of issues to process (default: 100)',
        )
        parser.add_argument(
            '--preview',
            action='store_true',
            help='Show preview of linkable issues without creating links',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Update existing links',
        )

    def handle(self, *args, **options):
        org_slug = options.get('org')
        limit = options.get('limit', 100)
        preview = options.get('preview', False)
        force = options.get('force', False)

        service = SentryJiraLinkingService()

        # Get organization if specified
        organization = None
        if org_slug:
            try:
                organization = SentryOrganization.objects.get(slug=org_slug)
                self.stdout.write(f'Processing organization: {organization.name}')
            except SentryOrganization.DoesNotExist:
                raise CommandError(f'Organization "{org_slug}" does not exist')

        if preview:
            self._show_preview(service, organization, limit)
        else:
            self._process_links(service, organization, limit, force)

    def _show_preview(self, service, organization, limit):
        """Show preview of issues that can be linked"""
        self.stdout.write(self.style.WARNING('PREVIEW MODE - No links will be created'))
        self.stdout.write(f'Checking up to {limit} issues for JIRA annotations...\n')

        linkable_issues = service.get_linkable_issues_preview(organization, limit)

        if not linkable_issues:
            self.stdout.write(self.style.WARNING('No issues with JIRA annotations found.'))
            return

        self.stdout.write(f'Found {len(linkable_issues)} issues with JIRA annotations:\n')

        for item in linkable_issues:
            issue = item['sentry_issue']
            jira_tickets = item['jira_tickets']
            
            self.stdout.write(f'📍 {issue.title[:60]}')
            self.stdout.write(f'   Sentry ID: {issue.sentry_id}')
            self.stdout.write(f'   Project: {issue.project}')
            
            for ticket in jira_tickets:
                self.stdout.write(f'   🎫 JIRA: {ticket["ticket_key"]} ({ticket["full_url"]})')
            
            self.stdout.write('')

        self.stdout.write(self.style.SUCCESS(
            f'\nPreview complete. Run without --preview to create {len(linkable_issues)} potential links.'
        ))

    def _process_links(self, service, organization, limit, force):
        """Process and create links"""
        self.stdout.write(f'Processing up to {limit} Sentry issues...')
        
        if force:
            self.stdout.write(self.style.WARNING('FORCE MODE - Will update existing links'))

        summary = service.scan_and_link_all_sentry_issues(organization, limit)

        # Display results
        self.stdout.write('\n' + '='*60)
        self.stdout.write('PROCESSING SUMMARY:')
        self.stdout.write('='*60)
        
        self.stdout.write(f'Issues processed: {summary["issues_processed"]}')
        self.stdout.write(f'Issues with JIRA annotations: {summary["issues_with_jira_links"]}')
        self.stdout.write(f'Total links created: {summary["total_links_created"]}')
        
        if summary['details']:
            self.stdout.write('\nSUCCESSFUL LINKS:')
            for detail in summary['details']:
                if detail['links_created'] > 0:
                    tickets = ', '.join(detail['jira_tickets'])
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'✅ {detail["issue"][:50]} -> {tickets}'
                        )
                    )

        if summary['errors']:
            self.stdout.write('\nERRORS:')
            for error in summary['errors'][:10]:  # Show first 10 errors
                self.stdout.write(self.style.ERROR(f'❌ {error}'))
            
            if len(summary['errors']) > 10:
                self.stdout.write(
                    self.style.WARNING(f'... and {len(summary["errors"]) - 10} more errors')
                )

        # Final status
        if summary['total_links_created'] > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n🎉 Successfully created {summary["total_links_created"]} automatic JIRA links!'
                )
            )
        elif summary['issues_with_jira_links'] > 0:
            self.stdout.write(
                self.style.WARNING(
                    '\n⚠️ Found issues with JIRA annotations but no new links were created. '
                    'This might mean the JIRA tickets are not synced yet or links already exist.'
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    '\n📝 No issues with JIRA annotations found. '
                    'Make sure your Sentry issues have JIRA ticket links in the UI.'
                )
            )