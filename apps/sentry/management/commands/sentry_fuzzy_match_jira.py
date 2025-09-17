from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from apps.sentry.models import SentryOrganization
from apps.sentry.services_jira_fuzzy_matching import SentryJiraFuzzyMatchingService


class Command(BaseCommand):
    help = 'Find JIRA tickets that might match Sentry issues using fuzzy title matching'

    def add_arguments(self, parser):
        parser.add_argument(
            '--org',
            type=str,
            help='Organization slug to process (if not provided, processes all)',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=50,
            help='Maximum number of Sentry issues to scan (default: 50)',
        )
        parser.add_argument(
            '--similarity',
            type=float,
            default=0.7,
            help='Minimum similarity threshold (0.0-1.0, default: 0.7)',
        )
        parser.add_argument(
            '--preview',
            action='store_true',
            help='Show potential matches without creating links',
        )
        parser.add_argument(
            '--auto-create',
            action='store_true',
            help='Automatically create links for high-confidence matches',
        )
        parser.add_argument(
            '--min-confidence',
            type=float,
            default=0.85,
            help='Minimum confidence for auto-creation (default: 0.85)',
        )

    def handle(self, *args, **options):
        org_slug = options.get('org')
        limit = options.get('limit', 50)
        similarity = options.get('similarity', 0.7)
        preview = options.get('preview', False)
        auto_create = options.get('auto_create', False)
        min_confidence = options.get('min_confidence', 0.85)

        # Validate similarity threshold
        if not 0.0 <= similarity <= 1.0:
            raise CommandError('Similarity threshold must be between 0.0 and 1.0')

        # Get organization if specified
        organization = None
        if org_slug:
            try:
                organization = SentryOrganization.objects.get(slug=org_slug)
                self.stdout.write(f'Processing organization: {organization.name}')
            except SentryOrganization.DoesNotExist:
                raise CommandError(f'Organization "{org_slug}" does not exist')

        # Initialize service
        service = SentryJiraFuzzyMatchingService()
        
        if preview:
            self._show_preview(service, organization, limit, similarity)
        else:
            self._process_matches(service, organization, limit, similarity, auto_create, min_confidence)

    def _show_preview(self, service, organization, limit, similarity):
        """Show preview of potential matches"""
        self.stdout.write(self.style.WARNING('PREVIEW MODE - No links will be created'))
        self.stdout.write(f'Scanning up to {limit} Sentry issues for fuzzy JIRA matches...')
        self.stdout.write(f'Similarity threshold: {similarity:.1%}\n')

        results = service.scan_and_suggest_matches(organization, limit, similarity)

        # Display summary
        summary = results['summary']
        self.stdout.write('='*60)
        self.stdout.write('FUZZY MATCHING SUMMARY')
        self.stdout.write('='*60)
        self.stdout.write(f'Issues scanned: {results["issues_scanned"]}')
        self.stdout.write(f'Potential matches found: {results["potential_matches_found"]}')
        self.stdout.write(f'High confidence matches: {results["high_confidence_matches"]}')
        self.stdout.write(f'Match rate: {summary["match_rate_percent"]}%')
        if results["potential_matches_found"] > 0:
            self.stdout.write(f'High confidence rate: {summary["high_confidence_rate"]}%')

        # Show individual suggestions
        if results['suggestions']:
            self.stdout.write('\nTOP SUGGESTIONS:')
            for i, suggestion in enumerate(results['suggestions'][:10], 1):
                sentry_issue = suggestion['sentry_issue']
                best_match = suggestion['best_match']
                
                self.stdout.write(f'\n{i}. {suggestion["confidence"].upper()} CONFIDENCE MATCH')
                self.stdout.write(f'   Sentry: {sentry_issue.title[:80]}')
                self.stdout.write(f'   JIRA:   {best_match["jira_summary"][:80]}')
                self.stdout.write(f'   Ticket: {best_match["jira_issue"].jira_key}')
                self.stdout.write(f'   Similarity: {best_match["similarity_score"]:.1%}')
                self.stdout.write(f'   Match type: {best_match["match_type"]}')
        
        if results['potential_matches_found'] > 0:
            self.stdout.write(f'\n💡 Run without --preview to create links')
            if results['high_confidence_matches'] > 0:
                self.stdout.write(f'   Use --auto-create to automatically link {results["high_confidence_matches"]} high-confidence matches')

    def _process_matches(self, service, organization, limit, similarity, auto_create, min_confidence):
        """Process and create matches"""
        self.stdout.write(f'Scanning {limit} Sentry issues for fuzzy JIRA matches...')
        self.stdout.write(f'Similarity threshold: {similarity:.1%}')
        
        if auto_create:
            self.stdout.write(self.style.SUCCESS(f'AUTO-CREATE MODE - Will create links for matches ≥{min_confidence:.1%}'))

        # Scan for suggestions
        results = service.scan_and_suggest_matches(organization, limit, similarity)
        
        if not results['suggestions']:
            self.stdout.write(self.style.WARNING('No potential matches found.'))
            return

        # Create links from suggestions
        link_results = service.create_links_from_suggestions(
            results['suggestions'],
            auto_create_high_confidence=auto_create,
            min_confidence_score=min_confidence
        )

        # Display results
        self.stdout.write('\n' + '='*60)
        self.stdout.write('PROCESSING RESULTS')
        self.stdout.write('='*60)
        
        self.stdout.write(f'Issues scanned: {results["issues_scanned"]}')
        self.stdout.write(f'Potential matches found: {results["potential_matches_found"]}')
        self.stdout.write(f'Links created: {link_results["links_created"]}')
        
        if auto_create:
            self.stdout.write(f'High-confidence auto-created: {link_results["high_confidence_created"]}')
            self.stdout.write(f'Manual review needed: {link_results["manual_review_needed"]}')
        else:
            self.stdout.write(f'Manual review needed: {len(results["suggestions"])}')

        # Show successful links
        if link_results['links_created'] > 0:
            self.stdout.write('\nSUCCESSFUL LINKS:')
            # Get the high-confidence suggestions that were auto-created
            high_conf_suggestions = [
                s for s in results['suggestions'] 
                if s['best_match']['similarity_score'] >= min_confidence
            ]
            
            for suggestion in high_conf_suggestions[:5]:
                best_match = suggestion['best_match']
                sentry_title = suggestion['sentry_issue'].title[:50]
                jira_key = best_match['jira_issue'].jira_key
                similarity = best_match['similarity_score']
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'✅ {jira_key}: {sentry_title} (similarity: {similarity:.1%})'
                    )
                )

        # Show manual review suggestions
        if not auto_create and results['suggestions']:
            self.stdout.write('\nMANUAL REVIEW SUGGESTIONS:')
            for suggestion in results['suggestions'][:5]:
                best_match = suggestion['best_match']
                sentry_title = suggestion['sentry_issue'].title[:50]
                jira_key = best_match['jira_issue'].jira_key
                similarity = best_match['similarity_score']
                
                self.stdout.write(f'📋 {jira_key}: {sentry_title} (similarity: {similarity:.1%})')

        # Show errors
        if link_results['errors']:
            self.stdout.write('\nERRORS:')
            for error in link_results['errors'][:5]:
                self.stdout.write(self.style.ERROR(f'❌ {error}'))

        # Final summary
        if link_results['links_created'] > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n🎉 Successfully created {link_results["links_created"]} fuzzy-matched JIRA links!'
                )
            )
        elif results['potential_matches_found'] > 0:
            self.stdout.write(
                self.style.WARNING(
                    f'\n📝 Found {results["potential_matches_found"]} potential matches. '
                    f'Use --auto-create for high-confidence linking or review manually.'
                )
            )