from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Count, Q

from .models import JiraOrganization, JiraProject, JiraIssue, SentryJiraLink
from .services import sync_jira_organization, SentryJiraLinkService


@staff_member_required
def dashboard(request):
    """Main JIRA dashboard"""
    # Basic statistics
    total_orgs = JiraOrganization.objects.count()
    active_orgs = JiraOrganization.objects.filter(sync_enabled=True).count()
    total_projects = JiraProject.objects.count()
    total_issues = JiraIssue.objects.count()
    open_issues = JiraIssue.objects.filter(status_category='new').count()
    
    context = {
        'total_orgs': total_orgs,
        'active_orgs': active_orgs,
        'total_projects': total_projects,
        'total_issues': total_issues,
        'open_issues': open_issues,
    }
    
    return render(request, 'jira/dashboard.html', context)


@staff_member_required
def organizations_list(request):
    """List all JIRA organizations"""
    organizations = JiraOrganization.objects.annotate(
        projects_count=Count('projects'),
        issues_count=Count('projects__issues')
    ).order_by('name')
    
    return render(request, 'jira/organizations_list.html', {'organizations': organizations})


@staff_member_required
def organization_detail(request, org_id):
    """Detailed view of a JIRA organization"""
    organization = get_object_or_404(JiraOrganization, id=org_id)
    
    projects = organization.projects.annotate(
        issues_count=Count('issues'),
        open_count=Count('issues', filter=Q(issues__status_category='new'))
    ).order_by('name')
    
    context = {
        'organization': organization,
        'projects': projects,
    }
    
    return render(request, 'jira/organization_detail.html', context)


@staff_member_required
def project_detail(request, project_id):
    """Detailed view of a JIRA project"""
    project = get_object_or_404(JiraProject, id=project_id)
    
    # Issues with filtering
    status_filter = request.GET.get('status', '')
    issues = project.issues.all()
    
    if status_filter:
        issues = issues.filter(status_category=status_filter)
    
    issues = issues.order_by('-jira_updated')[:50]  # Limit for performance
    
    context = {
        'project': project,
        'issues': issues,
        'status_filter': status_filter,
    }
    
    return render(request, 'jira/project_detail.html', context)


@staff_member_required
def issue_detail(request, issue_id):
    """Detailed view of a JIRA issue"""
    issue = get_object_or_404(JiraIssue, id=issue_id)
    
    # Check for linked Sentry issues
    sentry_links = issue.sentryjiralink_set.select_related('sentry_issue').all()
    
    context = {
        'issue': issue,
        'sentry_links': sentry_links,
    }
    
    return render(request, 'jira/issue_detail.html', context)


@staff_member_required
def sync_organization(request, org_id):
    """Trigger sync for a specific organization"""
    organization = get_object_or_404(JiraOrganization, id=org_id)
    
    if request.method == 'POST':
        try:
            sync_log = sync_jira_organization(org_id)
            if sync_log and sync_log.status == 'success':
                messages.success(
                    request, 
                    f'Successfully synced {organization.name}: '
                    f'{sync_log.projects_synced} projects, '
                    f'{sync_log.issues_synced} issues'
                )
            else:
                messages.error(request, f'Sync failed: {sync_log.error_message if sync_log else "Unknown error"}')
        except Exception as e:
            messages.error(request, f'Sync failed: {str(e)}')
    
    return redirect('jira:organization_detail', org_id=org_id)


@staff_member_required
def test_connection(request, org_id):
    """Test JIRA API connection"""
    organization = get_object_or_404(JiraOrganization, id=org_id)
    
    if request.method == 'POST':
        try:
            from .client import JiraAPIClient
            client = JiraAPIClient(organization.base_url, organization.username, organization.api_token)
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


@staff_member_required
def create_jira_from_sentry(request, sentry_issue_id):
    """Create a JIRA issue from a Sentry issue"""
    from apps.sentry.models import SentryIssue
    
    sentry_issue = get_object_or_404(SentryIssue, id=sentry_issue_id)
    
    if request.method == 'POST':
        jira_project_id = request.POST.get('jira_project')
        issue_type = request.POST.get('issue_type', 'Bug')
        priority = request.POST.get('priority', 'Medium')
        assignee_account_id = request.POST.get('assignee_account_id', '')
        
        if not jira_project_id:
            messages.error(request, 'Please select a JIRA project')
            return redirect(request.META.get('HTTP_REFERER', '/'))
        
        jira_project = get_object_or_404(JiraProject, id=jira_project_id)
        
        # Create JIRA issue
        link_service = SentryJiraLinkService()
        success, jira_issue, message = link_service.create_jira_issue_from_sentry(
            sentry_issue=sentry_issue,
            jira_project=jira_project,
            issue_type=issue_type,
            priority=priority,
            assignee_account_id=assignee_account_id if assignee_account_id else None,
            user=request.user
        )
        
        if success:
            messages.success(request, message)
            return redirect('jira:issue_detail', issue_id=jira_issue.id)
        else:
            messages.error(request, message)
    
    # Get available JIRA projects for the form
    jira_projects = JiraProject.objects.filter(
        jira_organization__sync_enabled=True
    ).select_related('jira_organization')
    
    context = {
        'sentry_issue': sentry_issue,
        'jira_projects': jira_projects,
    }
    
    return render(request, 'jira/create_from_sentry.html', context)


@staff_member_required
def sentry_jira_links(request):
    """View all Sentry-JIRA links"""
    links = SentryJiraLink.objects.select_related(
        'sentry_issue', 'jira_issue', 'jira_issue__jira_project'
    ).order_by('-created_at')[:100]
    
    context = {
        'links': links,
    }
    
    return render(request, 'jira/links.html', context)