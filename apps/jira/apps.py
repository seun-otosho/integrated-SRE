from django.apps import AppConfig


class JiraConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.jira"
    verbose_name = "JIRA Integration"