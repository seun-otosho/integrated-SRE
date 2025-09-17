from django.apps import AppConfig


class SonarcloudConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.sonarcloud'
    verbose_name = 'SonarCloud Integration'