import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from django.utils import timezone
from django.db.models import Count, Q, Avg
from django.core.cache import cache

logger = logging.getLogger(__name__)


class DashboardDataService:
    """Service for collecting and aggregating dashboard data"""
    
    def __init__(self):
        self.cache_timeout = 300  # 5 minutes default cache
    
    def get_executive_overview(self, product_filter=None, environment_filter=None) -> Dict:
        """Get executive overview dashboard data"""
        cache_key = f"executive_overview_{product_filter}_{environment_filter}"
        cached_data = cache.get(cache_key)
        if cached_data:
            return cached_data
        
        data = {
            'summary_cards': self._get_summary_cards(product_filter, environment_filter),
            'health_trends': self._get_health_trends(product_filter, environment_filter),
            'critical_issues': self._get_critical_issues(product_filter, environment_filter),
            'environment_status': self._get_environment_status(product_filter),
            'product_health': self._get_product_health_overview(product_filter),
            'integration_stats': self._get_integration_stats(),
            'generated_at': timezone.now().isoformat()
        }
        
        cache.set(cache_key, data, self.cache_timeout)
        return data
    
    def get_product_health_dashboard(self, product_id=None, environment_filter=None) -> Dict:
        """Get product-focused health dashboard"""
        cache_key = f"product_health_{product_id}_{environment_filter}"
        cached_data = cache.get(cache_key)
        if cached_data:
            return cached_data
        
        data = {
            'product_overview': self._get_product_overview(product_id),
            'sentry_metrics': self._get_product_sentry_metrics(product_id, environment_filter),
            'jira_metrics': self._get_product_jira_metrics(product_id),
            'sonarcloud_metrics': self._get_product_sonarcloud_metrics(product_id),
            'cross_system_links': self._get_product_cross_system_links(product_id),
            'environment_breakdown': self._get_product_environment_breakdown(product_id),
            'generated_at': timezone.now().isoformat()
        }
        
        cache.set(cache_key, data, self.cache_timeout)
        return data
    
    def get_environment_dashboard(self, environment=None, product_filter=None) -> Dict:
        """Get environment-focused dashboard"""
        cache_key = f"environment_dash_{environment}_{product_filter}"
        cached_data = cache.get(cache_key)
        if cached_data:
            return cached_data
        
        data = {
            'environment_overview': self._get_environment_overview(environment, product_filter),
            'issue_trends': self._get_environment_issue_trends(environment, product_filter),
            'deployment_health': self._get_deployment_health(environment, product_filter),
            'quality_metrics': self._get_environment_quality_metrics(environment, product_filter),
            'top_issues': self._get_environment_top_issues(environment, product_filter),
            'generated_at': timezone.now().isoformat()
        }
        
        cache.set(cache_key, data, self.cache_timeout)
        return data
    
    def _get_summary_cards(self, product_filter=None, environment_filter=None) -> List[Dict]:
        """Get summary metric cards for executive dashboard"""
        from apps.products.models import Product
        from apps.sentry.models import SentryIssue, SentryProject
        from apps.jira.models import JiraIssue, SentryJiraLink
        from apps.sonarcloud.models import SonarCloudProject
        
        # Apply filters
        products_qs = Product.objects.all()
        if product_filter:
            products_qs = products_qs.filter(id=product_filter)
        
        sentry_issues_qs = SentryIssue.objects.all()
        if product_filter:
            sentry_issues_qs = sentry_issues_qs.filter(project__product_id=product_filter)
        if environment_filter:
            sentry_issues_qs = sentry_issues_qs.filter(environment=environment_filter)
        
        # Calculate metrics
        total_products = products_qs.count()
        total_sentry_issues = sentry_issues_qs.count()
        unresolved_issues = sentry_issues_qs.filter(status='unresolved').count()
        total_jira_links = SentryJiraLink.objects.filter(
            sentry_issue__in=sentry_issues_qs
        ).count()
        
        # Calculate link coverage
        link_coverage = (total_jira_links / max(total_sentry_issues, 1)) * 100
        
        # Get quality metrics
        sonarcloud_projects_qs = SonarCloudProject.objects.all()
        if product_filter:
            sonarcloud_projects_qs = sonarcloud_projects_qs.filter(product_id=product_filter)
        
        quality_gate_passed = sonarcloud_projects_qs.filter(quality_gate_status='OK').count()
        total_quality_projects = sonarcloud_projects_qs.exclude(quality_gate_status='NONE').count()
        quality_pass_rate = (quality_gate_passed / max(total_quality_projects, 1)) * 100
        
        cards = [
            {
                'title': 'Products Monitored',
                'value': total_products,
                'type': 'count',
                'color': 'blue',
                'icon': 'products'
            },
            {
                'title': 'Active Issues',
                'value': unresolved_issues,
                'subtitle': f'{total_sentry_issues} total',
                'type': 'count',
                'color': 'orange' if unresolved_issues > 100 else 'green',
                'icon': 'issues'
            },
            {
                'title': 'JIRA Link Coverage',
                'value': f'{link_coverage:.1f}%',
                'subtitle': f'{total_jira_links} linked',
                'type': 'percentage',
                'color': 'green' if link_coverage > 80 else 'orange' if link_coverage > 50 else 'red',
                'icon': 'links'
            },
            {
                'title': 'Quality Gate Pass Rate',
                'value': f'{quality_pass_rate:.1f}%',
                'subtitle': f'{quality_gate_passed}/{total_quality_projects} passed',
                'type': 'percentage',
                'color': 'green' if quality_pass_rate > 80 else 'orange' if quality_pass_rate > 60 else 'red',
                'icon': 'quality'
            }
        ]
        
        return cards
    
    def _get_health_trends(self, product_filter=None, environment_filter=None) -> Dict:
        """Get health trend data for charts"""
        from apps.sentry.models import SentryIssue
        
        # Get last 30 days of data
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=30)
        
        # Query for trend data
        issues_qs = SentryIssue.objects.filter(
            last_seen__gte=start_date,
            last_seen__lte=end_date
        )
        
        if product_filter:
            issues_qs = issues_qs.filter(project__product_id=product_filter)
        if environment_filter:
            issues_qs = issues_qs.filter(environment=environment_filter)
        
        # Group by date
        daily_counts = {}
        current_date = start_date
        while current_date <= end_date:
            daily_counts[current_date.isoformat()] = {
                'total': 0,
                'unresolved': 0,
                'new': 0
            }
            current_date += timedelta(days=1)
        
        # Fill in actual data
        for issue in issues_qs:
            date_key = issue.last_seen.date().isoformat()
            if date_key in daily_counts:
                daily_counts[date_key]['total'] += 1
                if issue.status == 'unresolved':
                    daily_counts[date_key]['unresolved'] += 1
                # Check if issue was created recently
                if (issue.last_seen.date() - issue.first_seen.date()).days <= 1:
                    daily_counts[date_key]['new'] += 1
        
        return {
            'labels': list(daily_counts.keys()),
            'datasets': [
                {
                    'label': 'Total Issues',
                    'data': [daily_counts[date]['total'] for date in daily_counts.keys()],
                    'color': '#3b82f6'
                },
                {
                    'label': 'Unresolved Issues',
                    'data': [daily_counts[date]['unresolved'] for date in daily_counts.keys()],
                    'color': '#ef4444'
                },
                {
                    'label': 'New Issues',
                    'data': [daily_counts[date]['new'] for date in daily_counts.keys()],
                    'color': '#f59e0b'
                }
            ]
        }
    
    def _get_critical_issues(self, product_filter=None, environment_filter=None) -> List[Dict]:
        """Get list of critical issues requiring attention"""
        from apps.sentry.models import SentryIssue
        
        issues_qs = SentryIssue.objects.filter(
            status='unresolved',
            level__in=['error', 'fatal']
        ).order_by('-count', '-last_seen')
        
        if product_filter:
            issues_qs = issues_qs.filter(project__product_id=product_filter)
        if environment_filter:
            issues_qs = issues_qs.filter(environment=environment_filter)
        
        critical_issues = []
        for issue in issues_qs[:10]:  # Top 10 critical issues
            # Check if linked to JIRA
            has_jira_link = hasattr(issue, 'sentryjiralink_set') and issue.sentryjiralink_set.exists()
            
            critical_issues.append({
                'id': issue.id,
                'title': issue.title[:100],
                'project': issue.project.name,
                'environment': issue.environment or 'Unknown',
                'level': issue.level,
                'count': issue.count,
                'user_count': issue.user_count,
                'last_seen': issue.last_seen.isoformat(),
                'has_jira_link': has_jira_link,
                'permalink': issue.permalink
            })
        
        return critical_issues
    
    def _get_environment_status(self, product_filter=None) -> List[Dict]:
        """Get environment status summary"""
        from apps.sentry.models import SentryIssue
        
        # Get unique environments
        environments_qs = SentryIssue.objects.exclude(
            environment__isnull=True
        ).exclude(environment__exact='')
        
        if product_filter:
            environments_qs = environments_qs.filter(project__product_id=product_filter)
        
        environments = environments_qs.values_list('environment', flat=True).distinct()
        
        env_status = []
        for env in environments:
            env_issues_qs = SentryIssue.objects.filter(environment=env)
            if product_filter:
                env_issues_qs = env_issues_qs.filter(project__product_id=product_filter)
            
            active_issues = env_issues_qs.filter(status='unresolved').count()
            total_issues = env_issues_qs.count()
            projects_count = env_issues_qs.values('project').distinct().count()
            
            # Calculate health score (higher is better)
            if total_issues > 0:
                health_score = max(0, 100 - (active_issues / total_issues * 100))
            else:
                health_score = 100
            
            env_status.append({
                'name': env,
                'active_issues': active_issues,
                'total_issues': total_issues,
                'projects_count': projects_count,
                'health_score': round(health_score, 1)
            })
        
        return sorted(env_status, key=lambda x: x['active_issues'], reverse=True)
    
    def _get_product_health_overview(self, product_filter=None) -> List[Dict]:
        """Get product health overview"""
        from apps.products.models import Product
        from apps.sentry.models import SentryIssue
        from apps.jira.models import JiraIssue
        from apps.sonarcloud.services_integration import ProductQualityService
        
        products_qs = Product.objects.all()
        if product_filter:
            products_qs = products_qs.filter(id=product_filter)
        
        product_health = []
        quality_service = ProductQualityService()
        
        for product in products_qs[:10]:  # Limit to 10 for performance
            # Get Sentry stats
            sentry_issues = SentryIssue.objects.filter(project__product=product)
            sentry_stats = {
                'total': sentry_issues.count(),
                'unresolved': sentry_issues.filter(status='unresolved').count()
            }
            
            # Get JIRA stats
            jira_tickets = JiraIssue.objects.filter(jira_project__product=product)
            jira_stats = {
                'total': jira_tickets.count(),
                'open': jira_tickets.exclude(status_category='done').count()
            }
            
            # Get quality score
            try:
                health_data = quality_service.calculate_product_health_score(product)
                quality_score = health_data.get('sonarcloud_health', {}).get('score')
                health_grade = health_data.get('health_grade', 'N/A')
            except:
                quality_score = None
                health_grade = 'N/A'
            
            product_health.append({
                'id': product.id,
                'name': product.name,
                'hierarchy_path': product.hierarchy_path,
                'sentry_issues': sentry_stats,
                'jira_tickets': jira_stats,
                'quality_score': quality_score,
                'health_grade': health_grade
            })
        
        return product_health
    
    def _get_integration_stats(self) -> Dict:
        """Get integration statistics"""
        from apps.jira.models import SentryJiraLink
        from apps.sonarcloud.models import SonarCloudProject
        from apps.sentry.models import SentryIssue
        
        total_sentry_issues = SentryIssue.objects.count()
        annotation_links = SentryJiraLink.objects.filter(
            creation_notes__icontains='annotation'
        ).count()
        fuzzy_links = SentryJiraLink.objects.filter(
            creation_notes__icontains='fuzzy matching'
        ).count()
        sonarcloud_projects = SonarCloudProject.objects.count()
        total_links = SentryJiraLink.objects.count()
        
        coverage_rate = (total_links / max(total_sentry_issues, 1)) * 100
        
        return {
            'annotation_links': annotation_links,
            'fuzzy_links': fuzzy_links,
            'sonarcloud_projects': sonarcloud_projects,
            'total_links': total_links,
            'coverage_rate': round(coverage_rate, 1)
        }