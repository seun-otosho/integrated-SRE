from django.apps import AppConfig


class AzureConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.azure'
    verbose_name = 'Azure Application Insights'
    
    def ready(self):
        """Initialize Azure integration when Django starts"""
        pass