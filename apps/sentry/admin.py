from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from .models import (
    SentryOrganization, SentryProject, SentryIssue, 
    SentryEvent, SentrySyncLog
)
from .services import sync_organization


@admin.register(SentryOrganization)
class SentryOrganizationAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'sync_enabled', 'sync_interval_hours', 'last_sync_display', 'projects_count', 'sync_actions']
    list_filter = ['sync_enabled', 'sync_interval_hours', 'created_at']
    search_fields = ['name', 'slug']
    readonly_fields = ['sentry_id', 'date_created', 'created_at', 'updated_at', 'last_sync']
    
    fieldsets = (
        ('Organization Info', {
            'fields': ('name', 'slug', 'sentry_id', 'avatar_url', 'date_created')
        }),
        ('API Configuration', {
            'fields': ('api_token', 'api_url')
        }),
        ('Sync Settings', {
            'fields': ('sync_enabled', 'sync_interval_hours', 'last_sync')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['sync_selected_organizations', 'enable_sync', 'disable_sync']
    
    def get_urls(self):
        """Add custom URLs for bulk operations"""
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path(
                'bulk-assign-issues-to-product/',
                self.admin_site.admin_view(self.bulk_assign_issues_to_product_view),
                name='sentry_bulk_assign_issues_to_product',
            ),
        ]
        return custom_urls + urls
    
    def bulk_assign_issues_to_product_view(self, request):
        """View for selecting product for bulk assignment"""
        from django.shortcuts import render, redirect
        from django.contrib import messages
        from apps.products.models import Product
        from apps.sentry.models import SentryProject
        
        project_ids = request.session.get('bulk_assign_project_ids', [])
        if not project_ids:
            messages.error(request, 'No projects found for bulk assignment.')
            return redirect('admin:sentry_sentryissue_changelist')
        
        projects = SentryProject.objects.filter(id__in=project_ids).select_related('organization', 'product')
        
        if request.method == 'POST':
            product_id = request.POST.get('product')
            if product_id:
                try:
                    product = Product.objects.get(id=product_id)
                    updated_count = SentryProject.objects.filter(id__in=project_ids).update(product=product)
                    
                    messages.success(
                        request,
                        f'Successfully assigned {updated_count} projects to "{product.name}"'
                    )
                    
                    # Clear session data
                    del request.session['bulk_assign_project_ids']
                    
                except Product.DoesNotExist:
                    messages.error(request, 'Selected product does not exist.')
            else:
                messages.warning(request, 'Please select a product.')
            
            return redirect('admin:sentry_sentryissue_changelist')
        
        # Get all products for selection
        products = Product.objects.all().order_by('name')
        
        context = {
            'projects': projects,
            'products': products,
            'title': 'Bulk Assign Projects to Product',
            'opts': self.model._meta,
        }
        
        return render(request, 'admin/sentry/bulk_assign_to_product.html', context)
    
    def last_sync_display(self, obj):
        if obj.last_sync:
            time_diff = timezone.now() - obj.last_sync
            if time_diff < timedelta(hours=1):
                return format_html('<span style="color: green;">{}min ago</span>', int(time_diff.total_seconds() / 60))
            elif time_diff < timedelta(hours=24):
                return format_html('<span style="color: orange;">{}h ago</span>', int(time_diff.total_seconds() / 3600))
            else:
                return format_html('<span style="color: red;">{}d ago</span>', time_diff.days)
        return format_html('<span style="color: gray;">Never</span>')
    last_sync_display.short_description = 'Last Sync'
    
    def projects_count(self, obj):
        count = obj.projects.count()
        url = reverse('admin:sentry_sentryproject_changelist') + f'?organization__id__exact={obj.id}'
        return format_html('<a href="{}">{} projects</a>', url, count)
    projects_count.short_description = 'Projects'
    
    def sync_actions(self, obj):
        sync_url = reverse('admin:sentry_sentryorganization_change', args=[obj.pk]) + '?sync=true'
        return format_html(
            '<a class="button" href="{}">Sync Now</a>',
            sync_url
        )
    sync_actions.short_description = 'Actions'
    
    def sync_selected_organizations(self, request, queryset):
        synced_count = 0
        for org in queryset.filter(sync_enabled=True):
            try:
                sync_organization(org.id)
                synced_count += 1
            except Exception as e:
                self.message_user(request, f'Failed to sync {org.name}: {str(e)}', level='ERROR')
        
        self.message_user(request, f'Successfully triggered sync for {synced_count} organizations.')
    sync_selected_organizations.short_description = 'Sync selected organizations'
    
    def enable_sync(self, request, queryset):
        count = queryset.update(sync_enabled=True)
        self.message_user(request, f'Enabled sync for {count} organizations.')
    enable_sync.short_description = 'Enable sync'
    
    def disable_sync(self, request, queryset):
        count = queryset.update(sync_enabled=False)
        self.message_user(request, f'Disabled sync for {count} organizations.')
    disable_sync.short_description = 'Disable sync'


@admin.register(SentryProject)
class SentryProjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'organization', 'product_display', 'platform', 'status', 'total_issues', 'unresolved_issues', 'last_issue']
    list_filter = ['platform', 'status', 'organization', 'product', 'created_at']
    search_fields = ['name', 'slug', 'organization__name', 'product__name']
    readonly_fields = ['sentry_id', 'date_created', 'first_event', 'created_at', 'updated_at']
    actions = ['bulk_assign_to_product', 'remove_product_assignment']
    
    fieldsets = (
        ('Project Info', {
            'fields': ('organization', 'name', 'slug', 'sentry_id', 'platform', 'status')
        }),
        ('Product Mapping', {
            'fields': ('product',),
            'description': 'Link this Sentry project to a business product for better organization'
        }),
        ('Details', {
            'fields': ('date_created', 'first_event', 'has_access', 'is_public', 'is_bookmarked')
        }),
        ('Statistics', {
            'fields': ('total_issues', 'resolved_issues', 'unresolved_issues')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def product_display(self, obj):
        if obj.product:
            url = reverse('admin:products_product_change', args=[obj.product.pk])
            return format_html('<a href="{}">{}</a>', url, obj.product.hierarchy_path)
        return format_html('<span style="color: #999;">No product assigned</span>')
    product_display.short_description = 'Product'
    
    def last_issue(self, obj):
        last_issue = obj.issues.first()
        if last_issue:
            url = reverse('admin:sentry_sentryissue_change', args=[last_issue.pk])
            return format_html('<a href="{}">{}</a>', url, last_issue.last_seen.strftime('%Y-%m-%d %H:%M'))
        return '-'
    last_issue.short_description = 'Last Issue'
    
    def bulk_assign_to_product(self, request, queryset):
        """Bulk assign selected projects to a product"""
        from django.http import HttpResponseRedirect
        from django.urls import reverse
        
        project_ids = list(queryset.values_list('id', flat=True))
        request.session['bulk_assign_project_ids'] = project_ids
        
        url = reverse('admin:sentry_bulk_assign_projects_to_product')
        return HttpResponseRedirect(url)
    
    bulk_assign_to_product.short_description = 'Bulk assign to product'
    
    def remove_product_assignment(self, request, queryset):
        """Remove product assignment from selected projects"""
        count = queryset.update(product=None)
        self.message_user(request, f'Removed product assignment from {count} projects.')
    remove_product_assignment.short_description = 'Remove product assignment'
    
    def get_urls(self):
        """Add custom URLs for bulk operations"""
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path(
                'bulk-assign-to-product/',
                self.admin_site.admin_view(self.bulk_assign_projects_to_product_view),
                name='sentry_bulk_assign_projects_to_product',
            ),
        ]
        return custom_urls + urls
    
    def bulk_assign_projects_to_product_view(self, request):
        """View for bulk assigning projects to a product"""
        from django.shortcuts import render, redirect
        from django.contrib import messages
        from apps.products.models import Product
        
        project_ids = request.session.get('bulk_assign_project_ids', [])
        if not project_ids:
            messages.error(request, 'No projects selected for bulk assignment.')
            return redirect('admin:sentry_sentryproject_changelist')
        
        projects = SentryProject.objects.filter(id__in=project_ids).select_related('organization', 'product')
        
        if request.method == 'POST':
            product_id = request.POST.get('product')
            if product_id:
                try:
                    product = Product.objects.get(id=product_id)
                    updated_count = SentryProject.objects.filter(id__in=project_ids).update(product=product)
                    
                    messages.success(
                        request,
                        f'Successfully assigned {updated_count} projects to "{product.name}"'
                    )
                    
                    # Clear session data
                    del request.session['bulk_assign_project_ids']
                    
                except Product.DoesNotExist:
                    messages.error(request, 'Selected product does not exist.')
            else:
                # Remove assignment if no product selected
                updated_count = SentryProject.objects.filter(id__in=project_ids).update(product=None)
                messages.success(request, f'Removed product assignment from {updated_count} projects.')
                del request.session['bulk_assign_project_ids']
            
            return redirect('admin:sentry_sentryproject_changelist')
        
        # Get all products for selection
        products = Product.objects.all().order_by('name')
        
        context = {
            'projects': projects,
            'products': products,
            'title': 'Bulk Assign Projects to Product',
            'opts': self.model._meta,
        }
        
        return render(request, 'admin/sentry/bulk_assign_projects_to_product.html', context)


@admin.register(SentryIssue)
class SentryIssueAdmin(admin.ModelAdmin):
    list_display = ['title_short', 'project', 'status', 'level', 'count', 'user_count', 'quality_context', 'last_seen']
    list_filter = ['status', 'level', 'last_seen', 'first_seen', 'project', 'project__organization']
    search_fields = ['title', 'culprit', 'sentry_id']
    readonly_fields = ['sentry_id', 'permalink', 'first_seen', 'created_at', 'updated_at']
    date_hierarchy = 'last_seen'
    
    fieldsets = (
        ('Issue Info', {
            'fields': ('project', 'title', 'culprit', 'sentry_id', 'permalink')
        }),
        ('Status & Details', {
            'fields': ('status', 'level', 'type', 'metadata')
        }),
        ('Statistics', {
            'fields': ('count', 'user_count', 'first_seen', 'last_seen')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['mark_resolved', 'mark_ignored', 'bulk_assign_to_product']
    
    def title_short(self, obj):
        title = obj.title[:80] + '...' if len(obj.title) > 80 else obj.title
        url = obj.permalink if obj.permalink else '#'
        return format_html('<a href="{}" target="_blank">{}</a>', url, title)
    title_short.short_description = 'Title'
    
    def mark_resolved(self, request, queryset):
        count = queryset.update(status=SentryIssue.Status.RESOLVED)
        self.message_user(request, f'Marked {count} issues as resolved.')
    mark_resolved.short_description = 'Mark as resolved'
    
    def mark_ignored(self, request, queryset):
        count = queryset.update(status=SentryIssue.Status.IGNORED)
        self.message_user(request, f'Marked {count} issues as ignored.')
    mark_ignored.short_description = 'Mark as ignored'
    
    def bulk_assign_to_product(self, request, queryset):
        """Bulk assign projects to a product"""
        from django.http import HttpResponseRedirect
        from django.urls import reverse
        
        # Get unique projects from selected issues
        project_ids = list(queryset.values_list('project_id', flat=True).distinct())
        
        if not project_ids:
            self.message_user(request, 'No projects found in selected issues.', level='ERROR')
            return
        
        # Store project IDs in session for bulk assignment
        request.session['bulk_assign_project_ids'] = project_ids
        
        # Redirect to product selection view
        url = reverse('admin:sentry_bulk_assign_issues_to_product')
        return HttpResponseRedirect(url)
    
    bulk_assign_to_product.short_description = 'Assign projects to product (via issues)'
    
    def quality_context(self, obj):
        """Display SonarCloud quality context if available"""
        try:
            # Check if SonarCloud integration is available
            from apps.sonarcloud.services_integration import SentryQualityService
            service = SentryQualityService()
            quality_data = service.get_quality_context_for_release(obj.project)
            
            if quality_data.get('has_quality_data'):
                quality_gate = quality_data.get('quality_gate_status', 'NONE')
                reliability = quality_data.get('reliability_rating', '')
                security = quality_data.get('security_rating', '')
                maintainability = quality_data.get('maintainability_rating', '')
                
                # Quality gate indicator
                gate_color = {
                    'OK': 'green', 'ERROR': 'red', 'WARN': 'orange', 'NONE': 'gray'
                }.get(quality_gate, 'gray')
                
                gate_icon = {
                    'OK': '✅', 'ERROR': '❌', 'WARN': '⚠️', 'NONE': '❓'
                }.get(quality_gate, '❓')
                
                # Ratings display
                ratings = []
                for rating, label in [(reliability, 'R'), (security, 'S'), (maintainability, 'M')]:
                    if rating:
                        color = {
                            'A': 'green', 'B': 'yellowgreen', 'C': 'orange', 
                            'D': 'orangered', 'E': 'red'
                        }.get(rating, 'gray')
                        ratings.append(f'<span style="color: {color}; font-weight: bold;" title="{label}">{rating}</span>')
                    else:
                        ratings.append('<span style="color: gray;">-</span>')
                
                return format_html(
                    '<span style="color: {};">{}</span> {}',
                    gate_color, gate_icon, '/'.join(ratings)
                )
            else:
                return format_html('<span style="color: gray;" title="No SonarCloud data">-</span>')
                
        except ImportError:
            return format_html('<span style="color: gray;" title="SonarCloud not configured">-</span>')
        except Exception:
            return format_html('<span style="color: gray;">-</span>')
    
    quality_context.short_description = 'Quality'


@admin.register(SentryEvent)
class SentryEventAdmin(admin.ModelAdmin):
    list_display = ['event_id', 'issue_title', 'platform', 'environment', 'user_email', 'date_created']
    list_filter = ['platform', 'environment', 'date_created', 'issue__project']
    search_fields = ['event_id', 'sentry_id', 'message', 'user_email']
    readonly_fields = ['sentry_id', 'event_id', 'date_created', 'created_at']
    date_hierarchy = 'date_created'
    
    fieldsets = (
        ('Event Info', {
            'fields': ('issue', 'event_id', 'sentry_id', 'message', 'date_created')
        }),
        ('Environment', {
            'fields': ('platform', 'environment', 'release')
        }),
        ('User Info', {
            'fields': ('user_id', 'user_email', 'user_ip')
        }),
        ('Context & Data', {
            'fields': ('context', 'tags', 'extra'),
            'classes': ('collapse',)
        }),
    )
    
    def issue_title(self, obj):
        return obj.issue.title[:50] + '...' if len(obj.issue.title) > 50 else obj.issue.title
    issue_title.short_description = 'Issue'


@admin.register(SentrySyncLog)
class SentrySyncLogAdmin(admin.ModelAdmin):
    list_display = ['started_at', 'organization', 'status', 'duration_display', 'projects_synced', 'issues_synced', 'events_synced']
    list_filter = ['status', 'organization', 'started_at']
    readonly_fields = ['started_at', 'completed_at', 'duration_seconds']
    date_hierarchy = 'started_at'
    
    fieldsets = (
        ('Sync Info', {
            'fields': ('organization', 'status', 'started_at', 'completed_at', 'duration_seconds')
        }),
        ('Results', {
            'fields': ('projects_synced', 'issues_synced', 'events_synced')
        }),
        ('Errors', {
            'fields': ('error_message', 'error_details'),
            'classes': ('collapse',)
        }),
    )
    
    def duration_display(self, obj):
        if obj.duration_seconds:
            return f"{obj.duration_seconds:.1f}s"
        return '-'
    duration_display.short_description = 'Duration'
    
    def has_add_permission(self, request):
        return False  # Sync logs are created automatically