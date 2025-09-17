import logging
from typing import Dict, List, Optional, Tuple
from django.utils import timezone as django_timezone
from django.db import transaction

from .models import (
    SonarCloudProject, CodeIssue, SentrySonarLink, 
    JiraSonarLink, QualityIssueTicket
)

logger = logging.getLogger(__name__)


class SentryQualityService:
    """Service for integrating SonarCloud quality data with Sentry"""
    
    def __init__(self):
        pass
    
    def create_sentry_sonar_link(self, sentry_project, sonarcloud_project, 
                                user=None, **quality_settings) -> Tuple[bool, SentrySonarLink, str]:
        """Create a link between Sentry and SonarCloud projects"""
        try:
            # Check if link already exists
            existing_link = SentrySonarLink.objects.filter(
                sentry_project=sentry_project,
                sonarcloud_project=sonarcloud_project
            ).first()
            
            if existing_link:
                return False, existing_link, "Link already exists"
            
            # Create the link
            link = SentrySonarLink.objects.create(
                sentry_project=sentry_project,
                sonarcloud_project=sonarcloud_project,
                created_by_user=user,
                **quality_settings
            )
            
            return True, link, f"Successfully linked {sentry_project} to {sonarcloud_project}"
            
        except Exception as e:
            logger.error(f"Error creating Sentry-SonarCloud link: {str(e)}")
            return False, None, str(e)
    
    def check_release_quality_gate(self, sentry_project) -> Dict:
        """Check if a Sentry project passes quality gates for release"""
        try:
            # Get the SonarCloud link
            link = SentrySonarLink.objects.filter(
                sentry_project=sentry_project
            ).first()
            
            if not link:
                return {'status': 'no_link', 'message': 'No SonarCloud project linked'}
            
            return link.current_quality_status
            
        except Exception as e:
            logger.error(f"Error checking quality gate for {sentry_project}: {str(e)}")
            return {'status': 'error', 'message': str(e)}
    
    def get_quality_context_for_release(self, sentry_project) -> Dict:
        """Get quality context data for a Sentry release"""
        try:
            link = SentrySonarLink.objects.filter(
                sentry_project=sentry_project
            ).select_related('sonarcloud_project').first()
            
            if not link:
                return {'has_quality_data': False}
            
            project = link.sonarcloud_project
            
            return {
                'has_quality_data': True,
                'quality_gate_status': project.quality_gate_status,
                'reliability_rating': project.reliability_rating,
                'security_rating': project.security_rating,
                'maintainability_rating': project.maintainability_rating,
                'coverage': project.coverage,
                'technical_debt_minutes': project.technical_debt,
                'bugs': project.bugs,
                'vulnerabilities': project.vulnerabilities,
                'security_hotspots': project.security_hotspots,
                'code_smells': project.code_smells,
                'sonarcloud_url': project.sonarcloud_url,
                'last_analysis': project.last_analysis,
                'quality_score': project.overall_quality_score,
            }
            
        except Exception as e:
            logger.error(f"Error getting quality context for {sentry_project}: {str(e)}")
            return {'has_quality_data': False, 'error': str(e)}


class JiraQualityService:
    """Service for integrating SonarCloud quality data with JIRA"""
    
    def __init__(self):
        pass
    
    def create_jira_sonar_link(self, jira_project, sonarcloud_project,
                              user=None, **automation_settings) -> Tuple[bool, JiraSonarLink, str]:
        """Create a link between JIRA and SonarCloud projects"""
        try:
            # Check if link already exists
            existing_link = JiraSonarLink.objects.filter(
                jira_project=jira_project,
                sonarcloud_project=sonarcloud_project
            ).first()
            
            if existing_link:
                return False, existing_link, "Link already exists"
            
            # Create the link
            link = JiraSonarLink.objects.create(
                jira_project=jira_project,
                sonarcloud_project=sonarcloud_project,
                created_by_user=user,
                **automation_settings
            )
            
            return True, link, f"Successfully linked {jira_project} to {sonarcloud_project}"
            
        except Exception as e:
            logger.error(f"Error creating JIRA-SonarCloud link: {str(e)}")
            return False, None, str(e)
    
    def create_jira_ticket_from_quality_issue(self, sonarcloud_issue: CodeIssue, 
                                            jira_sonar_link: JiraSonarLink,
                                            creation_reason: str = 'manual') -> Tuple[bool, str]:
        """Create a JIRA ticket from a SonarCloud quality issue"""
        try:
            # Check if ticket already exists
            existing_ticket = QualityIssueTicket.objects.filter(
                sonarcloud_issue=sonarcloud_issue,
                jira_sonar_link=jira_sonar_link
            ).first()
            
            if existing_ticket:
                return False, f"Ticket already exists: {existing_ticket.jira_issue.jira_key}"
            
            # Build ticket content based on issue type
            summary = self._build_ticket_summary(sonarcloud_issue)
            description = self._build_ticket_description(sonarcloud_issue)
            
            # Determine issue type and priority
            issue_type = jira_sonar_link.default_issue_type
            priority = jira_sonar_link.default_priority
            
            if sonarcloud_issue.type in ['VULNERABILITY', 'SECURITY_HOTSPOT']:
                issue_type = jira_sonar_link.security_issue_type
                priority = jira_sonar_link.security_priority
            
            # Create labels
            labels = [
                'sonarcloud',
                f'type-{sonarcloud_issue.type.lower()}',
                f'severity-{sonarcloud_issue.severity.lower()}'
            ]
            
            # Create JIRA ticket
            from apps.jira.services import SentryJiraLinkService
            jira_service = SentryJiraLinkService(jira_sonar_link.jira_project.jira_organization)
            
            success, jira_response = jira_service.client.create_issue(
                project_key=jira_sonar_link.jira_project.jira_key,
                issue_type=issue_type,
                summary=summary,
                description=description,
                priority=priority,
                labels=labels
            )
            
            if not success:
                return False, f"Failed to create JIRA ticket: {jira_response.get('message', 'Unknown error')}"
            
            # Get the created JIRA issue
            jira_key = jira_response.get('key')
            
            # Fetch the issue details and create local record
            from apps.jira.services import JiraSyncService
            sync_service = JiraSyncService(jira_sonar_link.jira_project.jira_organization)
            success, issue_data = sync_service.client.get_issue(jira_key)
            
            if success:
                sync_service._sync_single_issue(jira_sonar_link.jira_project, issue_data)
                
                # Get the created JiraIssue object
                from apps.jira.models import JiraIssue
                jira_issue = JiraIssue.objects.get(
                    jira_project=jira_sonar_link.jira_project,
                    jira_key=jira_key
                )
                
                # Create the quality issue ticket link
                QualityIssueTicket.objects.create(
                    sonarcloud_issue=sonarcloud_issue,
                    jira_issue=jira_issue,
                    jira_sonar_link=jira_sonar_link,
                    creation_reason=creation_reason,
                    auto_created=(creation_reason != 'manual')
                )
                
                return True, f"Successfully created JIRA ticket {jira_key}"
            else:
                return False, f"Created JIRA ticket {jira_key} but failed to sync locally"
            
        except Exception as e:
            logger.error(f"Error creating JIRA ticket from quality issue: {str(e)}")
            return False, str(e)
    
    def _build_ticket_summary(self, issue: CodeIssue) -> str:
        """Build JIRA ticket summary from SonarCloud issue"""
        type_prefix = {
            'BUG': '[Bug]',
            'VULNERABILITY': '[Security]',
            'SECURITY_HOTSPOT': '[Security Hotspot]',
            'CODE_SMELL': '[Code Quality]'
        }.get(issue.type, '[Quality]')
        
        return f"{type_prefix} {issue.message[:80]}"
    
    def _build_ticket_description(self, issue: CodeIssue) -> str:
        """Build JIRA ticket description from SonarCloud issue"""
        description_parts = [
            f"SonarCloud Issue: {issue.message}",
            f"Type: {issue.get_type_display()}",
            f"Severity: {issue.get_severity_display()}",
            f"Rule: {issue.rule}",
            "",
            f"File: {issue.component}",
        ]
        
        if issue.line:
            description_parts.append(f"Line: {issue.line}")
        
        if issue.effort:
            description_parts.append(f"Effort to Fix: {issue.effort}")
        
        description_parts.extend([
            "",
            f"SonarCloud Project: {issue.project.name}",
            f"SonarCloud URL: {issue.project.sonarcloud_url}",
            "",
            "This ticket was automatically created from a SonarCloud quality issue."
        ])
        
        return "\n".join(description_parts)
    
    def process_automated_ticket_creation(self, jira_sonar_link: JiraSonarLink) -> Dict:
        """Process automated ticket creation based on link settings"""
        results = {
            'security_tickets': 0,
            'debt_tickets': 0,
            'coverage_tickets': 0,
            'errors': []
        }
        
        try:
            project = jira_sonar_link.sonarcloud_project
            
            # Create security tickets
            if jira_sonar_link.auto_create_security_tickets:
                security_issues = project.issues.filter(
                    type__in=['VULNERABILITY', 'SECURITY_HOTSPOT'],
                    severity__in=['BLOCKER', 'CRITICAL', 'MAJOR', 'MINOR'][:CodeIssue.Severity.choices.index((jira_sonar_link.security_severity_threshold, '')) + 1],
                    status='OPEN'
                ).exclude(
                    jira_tickets__jira_sonar_link=jira_sonar_link
                )
                
                for issue in security_issues:
                    success, message = self.create_jira_ticket_from_quality_issue(
                        issue, jira_sonar_link, 'security'
                    )
                    if success:
                        results['security_tickets'] += 1
                    else:
                        results['errors'].append(f"Security ticket creation failed: {message}")
            
            # Create technical debt tickets
            if jira_sonar_link.auto_create_debt_tickets:
                debt_threshold_minutes = jira_sonar_link.debt_threshold_hours * 60
                debt_issues = project.issues.filter(
                    type='CODE_SMELL',
                    debt__gte=debt_threshold_minutes,
                    status='OPEN'
                ).exclude(
                    jira_tickets__jira_sonar_link=jira_sonar_link
                )
                
                for issue in debt_issues:
                    success, message = self.create_jira_ticket_from_quality_issue(
                        issue, jira_sonar_link, 'debt'
                    )
                    if success:
                        results['debt_tickets'] += 1
                    else:
                        results['errors'].append(f"Debt ticket creation failed: {message}")
            
            # Update sync tracking
            jira_sonar_link.last_ticket_creation_sync = django_timezone.now()
            jira_sonar_link.tickets_created_count += (
                results['security_tickets'] + 
                results['debt_tickets'] + 
                results['coverage_tickets']
            )
            jira_sonar_link.save()
            
        except Exception as e:
            logger.error(f"Error in automated ticket creation: {str(e)}")
            results['errors'].append(str(e))
        
        return results


class ProductQualityService:
    """Service for calculating unified product health scores"""
    
    def __init__(self):
        pass
    
    def calculate_product_health_score(self, product) -> Dict:
        """Calculate unified health score for a product"""
        try:
            health_data = {
                'product': product,
                'overall_score': 0,
                'sentry_health': self._calculate_sentry_health(product),
                'sonarcloud_health': self._calculate_sonarcloud_health(product),
                'jira_health': self._calculate_jira_health(product),
                'recommendations': []
            }
            
            # Calculate weighted overall score
            weights = {'sentry': 0.4, 'sonarcloud': 0.4, 'jira': 0.2}
            
            total_score = (
                health_data['sentry_health']['score'] * weights['sentry'] +
                health_data['sonarcloud_health']['score'] * weights['sonarcloud'] +
                health_data['jira_health']['score'] * weights['jira']
            )
            
            health_data['overall_score'] = round(total_score, 1)
            health_data['health_grade'] = self._score_to_grade(total_score)
            
            # Generate recommendations
            health_data['recommendations'] = self._generate_recommendations(health_data)
            
            return health_data
            
        except Exception as e:
            logger.error(f"Error calculating product health for {product}: {str(e)}")
            return {'error': str(e)}
    
    def _calculate_sentry_health(self, product) -> Dict:
        """Calculate Sentry-based health metrics"""
        sentry_projects = product.sentryproject_set.all()
        
        if not sentry_projects.exists():
            return {'score': 100, 'status': 'no_data', 'details': 'No Sentry projects'}
        
        total_issues = sum(p.total_issues for p in sentry_projects)
        unresolved_issues = sum(p.unresolved_issues for p in sentry_projects)
        
        if total_issues == 0:
            return {'score': 100, 'status': 'excellent', 'details': 'No issues'}
        
        error_rate = (unresolved_issues / total_issues) * 100
        
        # Score based on error rate (lower is better)
        if error_rate < 5:
            score = 100 - error_rate
        elif error_rate < 15:
            score = 95 - (error_rate * 2)
        else:
            score = max(50 - error_rate, 0)
        
        return {
            'score': round(score, 1),
            'error_rate': round(error_rate, 1),
            'total_issues': total_issues,
            'unresolved_issues': unresolved_issues,
            'status': 'excellent' if score >= 90 else 'good' if score >= 70 else 'needs_attention'
        }
    
    def _calculate_sonarcloud_health(self, product) -> Dict:
        """Calculate SonarCloud-based health metrics"""
        sonar_projects = product.sonarcloud_projects.all()
        
        if not sonar_projects.exists():
            return {'score': 100, 'status': 'no_data', 'details': 'No SonarCloud projects'}
        
        # Calculate average quality score
        quality_scores = [p.overall_quality_score for p in sonar_projects if p.overall_quality_score]
        
        if not quality_scores:
            return {'score': 50, 'status': 'no_analysis', 'details': 'No quality analysis available'}
        
        avg_quality = sum(quality_scores) / len(quality_scores)
        
        # Factor in quality gate status
        projects_with_gates = sonar_projects.exclude(quality_gate_status='NONE')
        if projects_with_gates.exists():
            passing_gates = projects_with_gates.filter(quality_gate_status='OK').count()
            gate_pass_rate = (passing_gates / projects_with_gates.count()) * 100
            
            # Combine quality score and gate pass rate
            final_score = (avg_quality * 0.7) + (gate_pass_rate * 0.3)
        else:
            final_score = avg_quality
        
        return {
            'score': round(final_score, 1),
            'average_quality': round(avg_quality, 1),
            'projects_analyzed': len(quality_scores),
            'quality_gates_passing': projects_with_gates.filter(quality_gate_status='OK').count(),
            'quality_gates_total': projects_with_gates.count(),
            'status': 'excellent' if final_score >= 90 else 'good' if final_score >= 70 else 'needs_attention'
        }
    
    def _calculate_jira_health(self, product) -> Dict:
        """Calculate JIRA-based health metrics"""
        jira_projects = product.jira_projects.all()
        
        if not jira_projects.exists():
            return {'score': 100, 'status': 'no_data', 'details': 'No JIRA projects'}
        
        total_issues = sum(p.total_issues for p in jira_projects)
        open_issues = sum(p.open_issues for p in jira_projects)
        
        if total_issues == 0:
            return {'score': 100, 'status': 'excellent', 'details': 'No issues'}
        
        resolution_rate = ((total_issues - open_issues) / total_issues) * 100
        
        # Score based on resolution rate (higher is better)
        score = resolution_rate
        
        return {
            'score': round(score, 1),
            'resolution_rate': round(resolution_rate, 1),
            'total_issues': total_issues,
            'open_issues': open_issues,
            'status': 'excellent' if score >= 90 else 'good' if score >= 70 else 'needs_attention'
        }
    
    def _score_to_grade(self, score: float) -> str:
        """Convert numeric score to letter grade"""
        if score >= 95:
            return 'A+'
        elif score >= 90:
            return 'A'
        elif score >= 85:
            return 'B+'
        elif score >= 80:
            return 'B'
        elif score >= 75:
            return 'C+'
        elif score >= 70:
            return 'C'
        elif score >= 65:
            return 'D+'
        elif score >= 60:
            return 'D'
        else:
            return 'F'
    
    def _generate_recommendations(self, health_data: Dict) -> List[str]:
        """Generate actionable recommendations based on health data"""
        recommendations = []
        
        # Sentry recommendations
        sentry = health_data['sentry_health']
        if sentry.get('status') == 'needs_attention':
            if sentry.get('error_rate', 0) > 10:
                recommendations.append("🔴 High error rate detected. Review and resolve Sentry issues.")
        
        # SonarCloud recommendations
        sonar = health_data['sonarcloud_health']
        if sonar.get('status') == 'needs_attention':
            recommendations.append("🟡 Code quality needs improvement. Address SonarCloud quality gate failures.")
        
        # JIRA recommendations
        jira = health_data['jira_health']
        if jira.get('status') == 'needs_attention':
            if jira.get('resolution_rate', 0) < 70:
                recommendations.append("🟠 Low issue resolution rate. Focus on closing open JIRA tickets.")
        
        # Overall recommendations
        if health_data['overall_score'] < 70:
            recommendations.append("⚠️ Overall product health is below target. Consider creating improvement plan.")
        
        return recommendations