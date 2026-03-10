from django.apps import AppConfig


class PalestrasConfig(AppConfig):
    name = 'palestras'

    def ready(self):
        from . import db_functions  # noqa — registers UNACCENT and custom lookup
