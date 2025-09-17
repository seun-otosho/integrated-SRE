from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.http import require_http_methods
from django.contrib import messages

from .models import SonarCloudOrganization, SonarCloudProject
from .services import sync_sonarcloud_organization


def dashboard(request):
    """SonarCloud dashboard showing overview of all organizations and projects"""
    organizations = SonarCloudOrganization.objects.all()
    
    # Get summary statistics
    total_projects = SonarCloudProject.objects.count()
    projects_with_quality_gate = SonarCloudProject.objects.exclude(quality_gate_status='NONE').count()
    projects_passing_gate = SonarCloudProject.objects.filter(quality_gate_status='OK').count()
    
    # Get recent projects
    recent_projects = SonarCloudProject.objects.filter(
        last_analysis__isnull=False
    ).order_by('-last_analysis')[:10]
    
    context = {
        'organizations': organizations,
        'total_projects': total_projects,
        'projects_with_quality_gate': projects_with_quality_gate,
        'projects_passing_gate': projects_passing_gate,
        'recent_projects': recent_projects,
    }
    
    return render(request, 'sonarcloud/dashboard.html', context)


def organizations_list(request):
    """List all SonarCloud organizations"""
    organizations = SonarCloudOrganization.objects.all()
    
    context = {
        'organizations': organizations,
    }
    
    return render(request, 'sonarcloud/organizations_list.html', context)


def organization_detail(request, org_id):
    """Detail view for a specific SonarCloud organization"""
    organization = get_object_or_404(SonarCloudOrganization, id=org_id)
    projects = organization.projects.all().order_by('name')
    
    # Get organization statistics
    total_projects = projects.count()
    projects_with_analysis = projects.filter(last_analysis__isnull=False).count()
    projects_passing_gate = projects.filter(quality_gate_status='OK').count()
    projects_failing_gate = projects.filter(quality_gate_status='ERROR').count()
    
    context = {
        'organization': organization,
        'projects': projects,
        'total_projects': total_projects,
        'projects_with_analysis': projects_with_analysis,
        'projects_passing_gate': projects_passing_gate,
        'projects_failing_gate': projects_failing_gate,
    }
    
    return render(request, 'sonarcloud/organization_detail.html', context)


def project_detail(request, project_id):
    """Detail view for a specific SonarCloud project"""
    project = get_object_or_404(SonarCloudProject, id=project_id)
    
    # Get recent measurements for trend analysis
    recent_measurements = project.measurements.order_by('-analysis_date')[:10]
    
    # Get recent issues
    recent_issues = project.issues.order_by('-creation_date')[:20]
    
    context = {
        'project': project,
        'recent_measurements': recent_measurements,
        'recent_issues': recent_issues,
    }
    
    return render(request, 'sonarcloud/project_detail.html', context)


@staff_member_required
@require_http_methods(["POST"])
def sync_organization(request, org_id):
    """Trigger sync for a specific organization"""
    organization = get_object_or_404(SonarCloudOrganization, id=org_id)
    
    try:
        sync_log = sync_sonarcloud_organization(org_id)
        
        if sync_log and sync_log.status == 'success':
            return JsonResponse({
                'success': True,
                'message': f'Successfully synced {organization.name}: '
                          f'{sync_log.projects_synced} projects, '
                          f'{sync_log.measures_synced} measures, '
                          f'{sync_log.issues_synced} issues'
            })
        else:
            error_msg = sync_log.error_message if sync_log else 'Unknown error'
            return JsonResponse({
                'success': False,
                'message': f'Sync failed: {error_msg}'
            })
            
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Sync failed: {str(e)}'
        })


@staff_member_required
@require_http_methods(["POST"])
def test_connection(request, org_id):
    """Test connection to a specific organization"""
    organization = get_object_or_404(SonarCloudOrganization, id=org_id)
    
    try:
        from .client import SonarCloudAPIClient
        client = SonarCloudAPIClient(organization.api_token)
        success, message = client.test_connection()
        
        # Update connection status
        from django.utils import timezone
        organization.last_connection_test = timezone.now()
        if success:
            organization.connection_status = 'connected'
            organization.connection_error = ''
        else:
            organization.connection_status = 'failed'
            organization.connection_error = message
        organization.save()
        
        return JsonResponse({
            'success': success,
            'message': message
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Connection test failed: {str(e)}'
        })