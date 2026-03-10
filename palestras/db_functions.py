import unicodedata

from django.db.backends.signals import connection_created
from django.db.models import CharField, TextField
from django.db.models.lookups import Lookup


def strip_accents(s):
    if s is None:
        return None
    return ''.join(
        c for c in unicodedata.normalize('NFD', s)
        if unicodedata.category(c) != 'Mn'
    ).lower()


def _register_sqlite_unaccent(sender, connection, **kwargs):
    if connection.vendor == 'sqlite':
        connection.connection.create_function('UNACCENT', 1, strip_accents)


connection_created.connect(_register_sqlite_unaccent)


class UnaccentIContains(Lookup):
    lookup_name = 'unaccent_icontains'

    def as_sql(self, compiler, connection):
        lhs, lhs_params = self.process_lhs(compiler, connection)
        rhs = strip_accents(self.rhs)
        return f"UNACCENT({lhs}) LIKE %s", lhs_params + (f'%{rhs}%',)


for _field_class in (CharField, TextField):
    _field_class.register_lookup(UnaccentIContains)
