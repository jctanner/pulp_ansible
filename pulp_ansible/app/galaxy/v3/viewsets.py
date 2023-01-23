from rest_framework.pagination import PageNumberPagination
from rest_framework import viewsets

from pulp_ansible.app.galaxy.v3.serializers import (
    CollectionVersionSearchListSerializer,
)

from pulp_ansible.app.models import (
    RepositoryCollectionVersionIndex,
)

from pulp_ansible.app.galaxy.v3.filters import CollectionVersionSearchFilter


class CollectionVersionSearchViewSetPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 1000


class CollectionVersionSearchViewSet(viewsets.ModelViewSet):

    serializer_class = CollectionVersionSearchListSerializer
    pagination_class = CollectionVersionSearchViewSetPagination
    # filter_backends = (DjangoFilterBackend,)
    filterset_class = CollectionVersionSearchFilter

    def get_queryset(self):
        return RepositoryCollectionVersionIndex.objects.all()
