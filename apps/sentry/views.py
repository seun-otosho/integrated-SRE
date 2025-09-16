from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta

from .models import SentryOrganization, SentryProject, SentryIssue, SentrySyncLog
from .services import sync_organization
from .client import SentryAPIClient


@staff_member_required
def dashboard(request):
    """Main dashboard showing overview of all Sentry data"""
    
    # Get summary statistics
    total_orgs = SentryOrganization.objects.count()
    active_orgs = SentryOrganization.objects.filter(sync_enabled=True).count()
    total_projects = SentryProject.objects.count()
    total_issues = SentryIssue.objects.count()
    unresolved_issues = SentryIssue.objects.filter(status='unresolved').count()
    
    # Recent sync logs
    recent_syncs = SentrySyncLog.objects.select_related('organization').order_by('-started_at')[:10]
    
    # Issues by status
    issues_by_status = SentryIssue.objects.values('status').annotate(count=Count('id'))
    
    # Recent issues
    recent_issues = SentryIssue.objects.select_related('project', 'project__organization').order_by('-last_seen')[:10]
    
    # Organizations needing sync
    now = timezone.now()
    orgs_needing_sync = []
    for org in SentryOrganization.objects.filter(sync_enabled=True):
        if not org.last_sync:
            orgs_needing_sync.append(org)
        else:
            time_since_sync = now - org.last_sync
            min_interval = timedelta(hours=org.sync_interval_hours)
            if time_since_sync >= min_interval:
                orgs_needing_sync.append(org)
    
    context = {
        'total_orgs': total_orgs,
        'active_orgs': active_orgs,
        'total_projects': total_projects,
        'total_issues': total_issues,
        'unresolved_issues': unresolved_issues,
        'recent_syncs': recent_syncs,
        'issues_by_status': issues_by_status,
        'recent_issues': recent_issues,
        'orgs_needing_sync': orgs_needing_sync,
    }
    
    return render(request, 'sentry/dashboard.html', context)


@staff_member_required
def organizations_list(request):
    """List all Sentry organizations"""
    organizations = SentryOrganization.objects.annotate(
        projects_count=Count('projects'),
        issues_count=Count('projects__issues')
    ).order_by('name')
    
    return render(request, 'sentry/organizations_list.html', {'organizations': organizations})


@staff_member_required
def organization_detail(request, org_id):
    """Detailed view of a Sentry organization"""
    organization = get_object_or_404(SentryOrganization, id=org_id)
    
    projects = organization.projects.annotate(
        issues_count=Count('issues'),
        unresolved_count=Count('issues', filter=Q(issues__status='unresolved'))
    ).order_by('name')
    
    recent_syncs = organization.sync_logs.order_by('-started_at')[:5]
    
    # Recent issues across all projects
    recent_issues = SentryIssue.objects.filter(
        project__organization=organization
    ).select_related('project').order_by('-last_seen')[:10]
    
    context = {
        'organization': organization,
        'projects': projects,
        'recent_syncs': recent_syncs,
        'recent_issues': recent_issues,
    }
    
    return render(request, 'sentry/organization_detail.html', context)


@staff_member_required
def project_detail(request, project_id):
    """Detailed view of a Sentry project"""
    project = get_object_or_404(SentryProject, id=project_id)
    
    # Issues with filtering
    status_filter = request.GET.get('status', '')
    issues = project.issues.all()
    
    if status_filter:
        issues = issues.filter(status=status_filter)
    
    issues = issues.order_by('-last_seen')[:50]  # Limit for performance
    
    # Issue statistics
    issue_stats = project.issues.values('status').annotate(count=Count('id'))
    
    context = {
        'project': project,
        'issues': issues,
        'issue_stats': issue_stats,
        'status_filter': status_filter,
    }
    
    return render(request, 'sentry/project_detail.html', context)


@staff_member_required
def issue_detail(request, issue_id):
    """Detailed view of a Sentry issue"""
    issue = get_object_or_404(SentryIssue, id=issue_id)
    
    # Recent events for this issue
    events = issue.events.order_by('-date_created')[:20]
    
    context = {
        'issue': issue,
        'events': events,
    }
    
    return render(request, 'sentry/issue_detail.html', context)


@staff_member_required
def sync_organization(request, org_id):
    """Trigger sync for a specific organization"""
    organization = get_object_or_404(SentryOrganization, id=org_id)
    
    if request.method == 'POST':
        try:
            sync_log = sync_organization(org_id)
            if sync_log and sync_log.status == 'success':
                messages.success(
                    request, 
                    f'Successfully synced {organization.name}: '
                    f'{sync_log.projects_synced} projects, '
                    f'{sync_log.issues_synced} issues, '
                    f'{sync_log.events_synced} events'
                )
            else:
                messages.error(request, f'Sync failed: {sync_log.error_message if sync_log else "Unknown error"}')
        except Exception as e:
            messages.error(request, f'Sync failed: {str(e)}')
    
    return redirect('sentry:organization_detail', org_id=org_id)


@staff_member_required
def test_connection(request):
    """Test Sentry API connection"""
    if request.method == 'POST':
        api_token = request.POST.get('api_token')
        api_url = request.POST.get('api_url', 'https://sentry.io/api/0/')
        
        if not api_token:
            return JsonResponse({'success': False, 'message': 'API token is required'})
        
        try:
            client = SentryAPIClient(api_token, api_url)
            success, message = client.test_connection()
            
            return JsonResponse({
                'success': success,
                'message': message
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Connection test failed: {str(e)}'
            })
    
    return JsonResponse({'success': False, 'message': 'POST method required'})