from django.db import models
from django.core.exceptions import ValidationError


class Product(models.Model):
    name = models.CharField(max_length=255)
    parent = models.ForeignKey("self", models.DO_NOTHING, related_name='sub_products', null=True, blank=True)
    description = models.TextField(blank=True, help_text="Description of this product or feature")
    
    # Product metadata
    owner_team = models.CharField(max_length=100, blank=True, help_text="Team responsible for this product")
    priority = models.CharField(
        max_length=20, 
        choices=[
            ('critical', 'Critical'),
            ('high', 'High'),
            ('medium', 'Medium'),
            ('low', 'Low')
        ],
        default='medium',
        help_text="Business priority of this product"
    )
    
    # Status tracking
    is_active = models.BooleanField(default=True, help_text="Whether this product is currently active")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'products'
        verbose_name = 'Product'
        verbose_name_plural = 'Products'
        ordering = ['name']
    
    def clean(self):
        """Prevent circular references in hierarchy"""
        if self.parent:
            # Check if setting this parent would create a cycle
            current = self.parent
            while current:
                if current == self:
                    raise ValidationError("A product cannot be its own ancestor.")
                current = current.parent
    
    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
    
    def __str__(self):
        if self.parent:
            return f"{self.parent.name} → {self.name}"
        return self.name
    
    @property
    def hierarchy_path(self):
        """Get the full hierarchy path as a string"""
        path = []
        current = self
        while current:
            path.insert(0, current.name)
            current = current.parent
        return ' → '.join(path)
    
    @property
    def all_descendants(self):
        """Get all descendant products recursively"""
        descendants = list(self.sub_products.all())
        for child in self.sub_products.all():
            descendants.extend(child.all_descendants)
        return descendants
    
    @property
    def sentry_projects_count(self):
        """Count of directly linked Sentry projects"""
        return self.sentryproject_set.count()
    
    @property
    def total_sentry_projects_count(self):
        """Count of Sentry projects including all descendants"""
        count = self.sentry_projects_count
        for descendant in self.all_descendants:
            count += descendant.sentry_projects_count
        return count
    
    def get_issue_stats(self):
        """Get aggregated issue statistics for this product and all descendants"""
        from apps.sentry.models import SentryIssue
        
        # Get all product IDs (self + descendants)
        product_ids = [self.id] + [p.id for p in self.all_descendants]
        
        # Aggregate issue stats
        issues = SentryIssue.objects.filter(project__product_id__in=product_ids)
        
        return {
            'total_issues': issues.count(),
            'unresolved_issues': issues.filter(status='unresolved').count(),
            'resolved_issues': issues.filter(status='resolved').count(),
            'ignored_issues': issues.filter(status='ignored').count(),
        }

