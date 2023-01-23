import datetime
import operator

from django.db.models import Value, F, CharField
from django.db.models import When, Case, Count
from django.db.models import Q
from django.db.models import Prefetch
from django.db.models import OuterRef
from django.db.models import Subquery
from django.db.models import sql

from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models.functions import Concat
from django_filters import filters
from rest_framework import viewsets

from pulp_ansible.app.galaxy.v3.serializers import (
    CollectionVersionSearchListSerializer,
    CollectionVersionListSerializer
)

from pulpcore.app.models import RepositoryContent

from pulp_ansible.app.models import (
    AnsibleCollectionDeprecated,
    AnsibleDistribution,
    CollectionVersion,
    CollectionVersionSignature,
)

from pulp_ansible.app.viewsets import (
    CollectionVersionFilter,
)

from pulp_ansible.app.galaxy.v3.filters import CollectionVersionSearchFilter


from django.db.models import QuerySet
from django.db.models.query import ModelIterable


class QuerySet2(QuerySet):

    model = CollectionVersion
    _sticky_filter = None
    _for_write = None
    _result_cache = None
    _prefetch_related_lookups = ()
    _prefetch_done = False
    _known_related_objects = {}
    _fields = None
    _defer_next_filter = False
    _deferred_filter = None
    _db = None
    _iterable_class = ModelIterable

    def __init__(self, raw=None, model=None, query=None, using=None, hints=None):
        self._db = using
        self._raw = raw

    @property
    def _hints(self):
        return {}

    @property
    def _query(self):
        #return sql.Query(self.model)
        #return self._raw
        return self

    def get_count(self, using=None):
        return 10

    def chain(self):
        return self

    def set_limits(self, start, stop):
        return

    def get_compiler(self, using=None):
        return self

    def execute_sql(self, chunked_fetch=None, chunk_size=None):
        return None

    @property
    def select(self):
        return self._raw

    @property
    def klass_info(self):
        return {
            'model': self.model,
            'select_fields': [0,1]
        }

    @property
    def annotation_col_map(self):
        return None

    def all(self):
        return self


class CollectionVersionSearchViewSetPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 1000


class CollectionVersionSearchViewSet(viewsets.ModelViewSet):

    serializer_class = CollectionVersionSearchListSerializer
    pagination_class = CollectionVersionSearchViewSetPagination
    #filter_backends = (DjangoFilterBackend,)
    #filterset_class = CollectionVersionSearchFilter

    def get_queryset(self):

        # need a default where to reduce the cartesian product
        where_clause = '''
            cc.pulp_id=crc.content_id
            AND
            (
                SELECT
                    COUNT(*)
                FROM
                    core_repositorycontent crc2
                WHERE
                    crc2.content_id=cc.pulp_id
                    AND
                    crc2.repository_id=cr.pulp_id
                    AND
                    acv.content_ptr_id=crc2.content_id
            )>=1'''

        # filter on signed or !signed
        signed_raw = self.request.query_params.get('signed')
        if signed_raw is not None:
            signed_bool = False
            if signed_raw in [True, "True", "true", "t", 1, "1"]:
                signed_bool = True

            where_clause += '\n'
            where_clause += '\t\tAND'
            where_clause += '\n'
            where_clause += '''\t\t(
                SELECT
                    COUNT(*)
                FROM
                    core_repositorycontent crc4,
                    ansible_collectionversionsignature acvs
                WHERE
                    crc4.repository_id=crc.repository_id
                    AND
                    crc4.content_id=acvs.content_ptr_id
            )'''
            if signed_bool:
                where_clause += '>=1'
            else:
                where_clause += '=0'

        # use a cartesian product to make combinations of repoversion, collectionversion
        # and then reduce down to actual things by where clauses
        return CollectionVersion.objects.raw(f'''
            SELECT
                distinct
                acv.*,
                cr.name as reponame,
                acv.namespace,
                acv.name,
                acv.version,
                (
                    SELECT
                        COUNT(*)
                    FROM
                        core_repositorycontent crc2
                    WHERE
                        crc2.content_id=cc.pulp_id
                        AND
                        crc2.repository_id=cr.pulp_id
                        AND
                        acv.content_ptr_id=crc2.content_id
                ) as rc_count,
                (
                    SELECT
                        COUNT(*)
                    FROM
                        ansible_collectionversionsignature acvs
                    WHERE
                        acvs.signed_collection_id=acv.content_ptr_id
                        AND
                        (
                            SELECT
                                COUNT(*)
                            FROM
                                core_repositorycontent crc3
                            WHERE
                                crc3.repository_id=crc.repository_id
                                AND
                                crc3.content_id=acvs.content_ptr_id
                        )>=1
                ) as sig_count
            FROM
                ansible_collectionversion acv,
                core_content cc,
                core_repositorycontent crc
            inner join core_repository cr ON crc.repository_id=cr.pulp_id
            WHERE
                {where_clause}
            ORDER BY
                acv.namespace,
                acv.name,
                acv.version,
                reponame
        ''')
