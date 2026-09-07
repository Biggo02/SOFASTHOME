from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        from . import rental_document_signals  # noqa: F401
        from . import rental_views
        from .rental_contract_generator import generate_contract_pdf

        rental_views._contract_pdf = generate_contract_pdf
