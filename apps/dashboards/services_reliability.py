"""
Product Reliability Calculation Service
Enhanced data analysis for accurate reliability scoring
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from django.utils import timezone
from django.db.models import Count, Avg, Q, Max, Min
from django.db.models.functions import TruncDate

from apps.products.models import Product
from apps.sentry.models import SentryProject, SentryIssue
from apps.jira.models import JiraProject, JiraIssue
from apps.sonarcloud.models import SonarCloudProject, QualityMeasurement

logger = logging.getLogger(__name__)


class ProductReliabilityService:
    """Service for calculating comprehensive product reliability scores"""
    
    def __init__(self):
        self.default_weights = {
            'runtime': 0.40,      # Sentry data
            'quality': 0.30,      # SonarCloud data
            'operations': 0.20,   # JIRA data
            'system_health': 0.10 # Infrastructure data
        }
    
    def calculate_product_reliability(self, product: Product, days: int = 30) -> Dict[str, Any]:
        """
        Calculate comprehensive reliability score for a product
        """
        end_time = timezone.now()
        start_time = end_time - timedelta(days=days)
        
        runtime_data = self._calculate_runtime_reliability(product, start_time, end_time)
        quality_data = self._calculate_code_quality_reliability(product, start_time, end_time)
        operations_data = self._calculate_operations_reliability(product, start_time, end_time)
        system_health_data = self._calculate_system_health(product, start_time, end_time)
        
        # Calculate weighted overall score
        overall_score = (
            runtime_data['score'] * self.default_weights['runtime'] +
            quality_data['score'] * self.default_weights['quality'] +
            operations_data['score'] * self.default_weights['operations'] +
            system_health_data['score'] * self.default_weights['system_health']
        )
        
        return {
            'product': product.name,
            'overall_score': round(overall_score, 1),
            'period_days': days,
            'calculated_at': timezone.now(),
            'components': {
                'runtime': runtime_data,
                'quality': quality_data,
                'operations': operations_data,
                'system_health': system_health_data
            },
            'health_status': self._get_health_status(overall_score),
            'recommendations': self._get_recommendations(runtime_data, quality_data, operations_data)
        }
    
    def _calculate_runtime_reliability(self, product: Product, start_time: datetime, end_time: datetime) -> Dict[str, Any]:
        """
        Enhanced Sentry runtime reliability calculation
        """
        # Get Sentry data
        sentry_projects = SentryProject.objects.filter(product=product)
        total_issues = SentryIssue.objects.filter(project__product=product)
        recent_issues = total_issues.filter(first_seen__gte=start_time)
        
        if not total_issues.exists():
            return {
                'score': 85.0,  # Default for no data
                'metrics': {'reason': 'No Sentry data available'},
                'trend': 'unknown'
            }
        
        # Enhanced metrics calculation
        critical_issues = total_issues.filter(level__in=['error', 'fatal'])
        resolved_issues = total_issues.filter(status='resolved')
        
        # Fix: Better resolution rate calculation
        total_count = total_issues.count()
        resolved_count = resolved_issues.count()
        resolution_rate = (resolved_count / total_count * 100) if total_count > 0 else 0
        
        # Enhanced error rate calculation
        recent_count = recent_issues.count()
        error_frequency = (recent_count / max(total_count, 1)) * 100
        
        # Critical issue impact
        critical_count = critical_issues.count()
        critical_impact = min(critical_count * 2, 40)  # Max 40 point penalty
        
        # Calculate score with improved logic
        base_score = 100
        error_penalty = min(error_frequency * 1.5, 30)  # Max 30 point penalty
        resolution_bonus = (resolution_rate / 100) * 20  # Up to 20 point bonus
        
        runtime_score = max(0, base_score - error_penalty - critical_impact + resolution_bonus)
        
        # Trend analysis
        older_issues = total_issues.filter(
            first_seen__gte=start_time - timedelta(days=30),
            first_seen__lt=start_time
        )
        trend = self._calculate_trend(older_issues.count(), recent_count)
        
        return {
            'score': round(runtime_score, 1),
            'metrics': {
                'total_issues': total_count,
                'recent_issues': recent_count,
                'critical_issues': critical_count,
                'resolution_rate': round(resolution_rate, 1),
                'error_frequency': round(error_frequency, 1),
                'projects_monitored': sentry_projects.count()
            },
            'trend': trend,
            'details': {
                'resolved_issues': resolved_count,
                'unresolved_issues': total_count - resolved_count,
                'error_penalty': round(error_penalty, 1),
                'critical_penalty': round(critical_impact, 1),
                'resolution_bonus': round(resolution_bonus, 1)
            }
        }
    
    def _calculate_code_quality_reliability(self, product: Product, start_time: datetime, end_time: datetime) -> Dict[str, Any]:
        """
        Enhanced SonarCloud code quality calculation
        """
        sonar_projects = SonarCloudProject.objects.filter(product=product)
        quality_measures = QualityMeasurement.objects.filter(
            project__product=product
        ).order_by('-analysis_date')
        
        if not quality_measures.exists():
            return {
                'score': 60.0,  # Default for no data
                'metrics': {'reason': 'No SonarCloud data available'},
                'trend': 'unknown'
            }
        
        # Get latest quality data
        latest_measure = quality_measures.first()
        
        # Enhanced quality scoring
        quality_gate_score = 100 if latest_measure.quality_gate_status == 'OK' else 0
        coverage_score = float(latest_measure.coverage or 0)
        
        # Bug and security penalties
        bug_density = latest_measure.bugs / max(latest_measure.lines_of_code or 1, 1) * 1000
        bug_penalty = min(bug_density * 5, 25)  # Max 25 point penalty
        
        security_penalty = min(latest_measure.security_hotspots * 2, 15)  # Max 15 point penalty
        code_smell_penalty = min(latest_measure.code_smells / 100, 20)  # Max 20 point penalty
        
        # Calculate quality score
        quality_score = max(0, 
            (quality_gate_score * 0.3) + 
            (coverage_score * 0.4) + 
            (30 - bug_penalty - security_penalty - code_smell_penalty)
        )
        
        # Historical trend analysis
        historical_measures = quality_measures.filter(
            analysis_date__gte=start_time - timedelta(days=30)
        )
        trend = self._calculate_quality_trend(historical_measures)
        
        return {
            'score': round(quality_score, 1),
            'metrics': {
                'quality_gate': latest_measure.quality_gate_status,
                'coverage': latest_measure.coverage,
                'bugs': latest_measure.bugs,
                'security_hotspots': latest_measure.security_hotspots,
                'code_smells': latest_measure.code_smells,
                'lines_of_code': latest_measure.lines_of_code,
                'projects_analyzed': sonar_projects.count()
            },
            'trend': trend,
            'details': {
                'bug_density': round(bug_density, 2),
                'bug_penalty': round(bug_penalty, 1),
                'security_penalty': round(security_penalty, 1),
                'code_smell_penalty': round(code_smell_penalty, 1),
                'quality_gate_score': quality_gate_score
            }
        }
    
    def _calculate_operations_reliability(self, product: Product, start_time: datetime, end_time: datetime) -> Dict[str, Any]:
        """
        Enhanced JIRA operations reliability calculation
        """
        jira_projects = JiraProject.objects.filter(product=product)
        total_issues = JiraIssue.objects.filter(jira_project__product=product)
        recent_issues = total_issues.filter(jira_created__gte=start_time)
        
        if not total_issues.exists():
            return {
                'score': 75.0,  # Default for no data
                'metrics': {'reason': 'No JIRA data available'},
                'trend': 'unknown'
            }
        
        # Enhanced operations metrics
        total_count = total_issues.count()
        recent_count = recent_issues.count()
        
        # Issue type analysis
        bugs = total_issues.filter(issue_type='Bug')
        incidents = total_issues.filter(issue_type__icontains='Incident')
        high_priority = total_issues.filter(priority__in=['High', 'Highest'])
        
        # Resolution analysis
        resolved_issues = total_issues.filter(resolution_date__isnull=False)
        resolution_rate = (resolved_issues.count() / total_count * 100) if total_count > 0 else 0
        
        # Response time analysis (enhanced)
        response_metrics = self._calculate_jira_response_times(recent_issues)
        
        # Calculate operations score
        base_score = 100
        incident_penalty = min((recent_count / max(total_count, 1)) * 50, 30)
        bug_penalty = min((bugs.count() / max(total_count, 1)) * 30, 20)
        priority_penalty = min((high_priority.count() / max(total_count, 1)) * 40, 25)
        resolution_bonus = (resolution_rate / 100) * 15
        
        operations_score = max(0, base_score - incident_penalty - bug_penalty - priority_penalty + resolution_bonus)
        
        # Trend analysis
        older_issues = total_issues.filter(
            jira_created__gte=start_time - timedelta(days=30),
            jira_created__lt=start_time
        )
        trend = self._calculate_trend(older_issues.count(), recent_count)
        
        return {
            'score': round(operations_score, 1),
            'metrics': {
                'total_issues': total_count,
                'recent_issues': recent_count,
                'bugs': bugs.count(),
                'incidents': incidents.count(),
                'high_priority': high_priority.count(),
                'resolution_rate': round(resolution_rate, 1),
                'projects_tracked': jira_projects.count(),
                **response_metrics
            },
            'trend': trend,
            'details': {
                'incident_penalty': round(incident_penalty, 1),
                'bug_penalty': round(bug_penalty, 1),
                'priority_penalty': round(priority_penalty, 1),
                'resolution_bonus': round(resolution_bonus, 1)
            }
        }
    
    def _calculate_system_health(self, product: Product, start_time: datetime, end_time: datetime) -> Dict[str, Any]:
        """
        System health calculation (placeholder for Azure integration)
        """
        # TODO: Integrate with Azure metrics when available
        return {
            'score': 95.0,  # Default until Azure integration
            'metrics': {
                'uptime': 99.5,
                'response_time': 250,  # ms
                'error_rate': 0.1
            },
            'trend': 'stable',
            'details': {
                'data_source': 'default_values',
                'note': 'Azure integration pending'
            }
        }
    
    def _calculate_jira_response_times(self, issues_queryset) -> Dict[str, Any]:
        """
        Calculate enhanced JIRA response and resolution metrics
        """
        if not issues_queryset.exists():
            return {
                'avg_response_time_hours': 0,
                'avg_resolution_time_hours': 0,
                'sla_compliance': 0
            }
        
        resolved_issues = issues_queryset.filter(resolution_date__isnull=False)
        
        if not resolved_issues.exists():
            return {
                'avg_response_time_hours': 0,
                'avg_resolution_time_hours': 0,
                'sla_compliance': 0
            }
        
        # Calculate resolution times
        resolution_times = []
        for issue in resolved_issues:
            if issue.jira_created and issue.resolution_date:
                resolution_time = issue.resolution_date - issue.jira_created
                resolution_times.append(resolution_time.total_seconds() / 3600)  # Convert to hours
        
        avg_resolution_time = sum(resolution_times) / len(resolution_times) if resolution_times else 0
        
        # SLA compliance (assuming 24h SLA for high priority, 72h for others)
        sla_compliant = 0
        for issue in resolved_issues:
            if issue.jira_created and issue.resolution_date:
                resolution_time = issue.resolution_date - issue.jira_created
                sla_threshold = 24 if issue.priority in ['High', 'Highest'] else 72
                if resolution_time.total_seconds() / 3600 <= sla_threshold:
                    sla_compliant += 1
        
        sla_compliance = (sla_compliant / resolved_issues.count() * 100) if resolved_issues.exists() else 0
        
        return {
            'avg_response_time_hours': 2,  # Placeholder - would need first response tracking
            'avg_resolution_time_hours': round(avg_resolution_time, 1),
            'sla_compliance': round(sla_compliance, 1)
        }
    
    def _calculate_trend(self, previous_count: int, current_count: int) -> str:
        """Calculate trend direction"""
        if previous_count == 0:
            return 'new_data'
        
        change_percent = ((current_count - previous_count) / previous_count) * 100
        
        if change_percent > 10:
            return 'worsening'
        elif change_percent < -10:
            return 'improving'
        else:
            return 'stable'
    
    def _calculate_quality_trend(self, historical_measures) -> str:
        """Calculate quality trend from historical SonarCloud data"""
        if historical_measures.count() < 2:
            return 'insufficient_data'
        
        latest = historical_measures.first()
        oldest = historical_measures.last()
        
        # Compare quality gates
        if latest.quality_gate_status == 'OK' and oldest.quality_gate_status != 'OK':
            return 'improving'
        elif latest.quality_gate_status != 'OK' and oldest.quality_gate_status == 'OK':
            return 'worsening'
        
        # Compare coverage
        latest_coverage = float(latest.coverage or 0)
        oldest_coverage = float(oldest.coverage or 0)
        
        if latest_coverage > oldest_coverage + 5:
            return 'improving'
        elif latest_coverage < oldest_coverage - 5:
            return 'worsening'
        else:
            return 'stable'
    
    def _get_health_status(self, score: float) -> str:
        """Get health status indicator"""
        if score >= 90:
            return 'excellent'
        elif score >= 80:
            return 'good'
        elif score >= 70:
            return 'needs_attention'
        elif score >= 60:
            return 'poor'
        else:
            return 'critical'
    
    def _get_recommendations(self, runtime_data: Dict, quality_data: Dict, operations_data: Dict) -> List[str]:
        """Generate actionable recommendations"""
        recommendations = []
        
        # Runtime recommendations
        if runtime_data['score'] < 70:
            if runtime_data['metrics'].get('resolution_rate', 0) < 50:
                recommendations.append("🔥 Focus on resolving existing Sentry issues - low resolution rate")
            if runtime_data['metrics'].get('critical_issues', 0) > 10:
                recommendations.append("🔥 Prioritize critical error resolution - high critical issue count")
        
        # Quality recommendations  
        if quality_data['score'] < 70:
            coverage = quality_data['metrics'].get('coverage')
            if coverage is not None and float(coverage or 0) < 60:
                recommendations.append("✅ Increase test coverage - currently below recommended 60%")
            elif coverage is None:
                recommendations.append("✅ Set up test coverage tracking in SonarCloud")
            if quality_data['metrics'].get('quality_gate') != 'OK':
                recommendations.append("✅ Fix quality gate failures in SonarCloud")
        
        # Operations recommendations
        if operations_data['score'] < 70:
            if operations_data['metrics'].get('resolution_rate', 0) < 60:
                recommendations.append("🎫 Improve JIRA issue resolution process")
            if operations_data['metrics'].get('high_priority', 0) > 20:
                recommendations.append("🎫 Address high-priority issue backlog")
        
        return recommendations
    
    def get_all_products_reliability(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get reliability scores for all products"""
        products = Product.objects.all()
        results = []
        
        for product in products:
            try:
                reliability_data = self.calculate_product_reliability(product, days)
                results.append(reliability_data)
            except Exception as e:
                logger.error(f"Failed to calculate reliability for {product.name}: {e}")
                results.append({
                    'product': product.name,
                    'overall_score': 0,
                    'error': str(e)
                })
        
        # Sort by overall score descending
        results.sort(key=lambda x: x.get('overall_score', 0), reverse=True)
        return results