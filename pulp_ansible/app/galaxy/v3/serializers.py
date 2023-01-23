import semantic_version
from django.conf import settings
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes
from rest_framework.reverse import reverse
from rest_framework import serializers, relations

from pulp_ansible.app import models
from pulpcore.plugin.models import ContentArtifact, RepositoryVersion


def _get_distro_context(context):
    distro_context = {}
    if "path" in context:
        distro_context["path"] = context["path"]
    if "distro_base_path" in context:
        distro_context["distro_base_path"] = context["distro_base_path"]
    return distro_context


class CollectionSerializer(serializers.ModelSerializer):
    """A serializer for a Collection."""

    deprecated = serializers.SerializerMethodField()
    created_at = serializers.SerializerMethodField()
    updated_at = serializers.SerializerMethodField()
    href = serializers.SerializerMethodField()

    versions_url = serializers.SerializerMethodField()
    highest_version = serializers.SerializerMethodField()

    class Meta:
        fields = (
            "href",
            "namespace",
            "name",
            "deprecated",
            "versions_url",
            "highest_version",
            "created_at",
            "updated_at",
        )
        model = models.Collection

    def get_deprecated(self, obj) -> bool:
        """Get deprecated."""
        return obj.pk in self.context["deprecated_collections"]

    def get_href(self, obj) -> str:
        """Get href."""
        ctx = _get_distro_context(self.context)
        return reverse(
            settings.ANSIBLE_URL_NAMESPACE + "collections-detail",
            kwargs={**ctx, "namespace": obj.namespace, "name": obj.name},
        )

    def get_versions_url(self, obj) -> str:
        """Get a link to a collection versions list."""
        ctx = _get_distro_context(self.context)
        return reverse(
            settings.ANSIBLE_URL_NAMESPACE + "collection-versions-list",
            kwargs={**ctx, "namespace": obj.namespace, "name": obj.name},
        )

    @extend_schema_field(OpenApiTypes.DATETIME)
    def get_created_at(self, obj):
        """Get the timestamp of the lowest version CollectionVersion's created timestamp."""
        return obj.pulp_created

    @extend_schema_field(OpenApiTypes.DATETIME)
    def get_updated_at(self, obj):
        """Get the timestamp of the highest version CollectionVersion's created timestamp."""
        if obj.repo_version_added_at and obj.repo_version_removed_at:
            return max(obj.repo_version_added_at, obj.repo_version_removed_at)

        return obj.repo_version_added_at or obj.repo_version_removed_at

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_highest_version(self, obj):
        """Get a highest version and its link."""
        available_versions = self.context["available_versions"][obj.pk]
        version = sorted(
            available_versions, key=lambda ver: semantic_version.Version(ver), reverse=True
        )[0]
        ctx = _get_distro_context(self.context)
        href = reverse(
            settings.ANSIBLE_URL_NAMESPACE + "collection-versions-detail",
            kwargs={
                **ctx,
                "namespace": obj.namespace,
                "name": obj.name,
                "version": version,
            },
        )
        return {"href": href, "version": version}


class CollectionVersionListSerializer(serializers.ModelSerializer):
    """A serializer for a CollectionVersion list item."""

    href = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(source="collection.pulp_created")
    updated_at = serializers.DateTimeField(source="collection.pulp_last_updated")

    class Meta:
        fields = (
            "version",
            "href",
            "created_at",
            "updated_at",
            "requires_ansible",
        )
        model = models.CollectionVersion

    def get_href(self, obj) -> str:
        """
        Get href.
        """
        ctx = _get_distro_context(self.context)

        return reverse(
            settings.ANSIBLE_URL_NAMESPACE + "collection-versions-detail",
            kwargs={
                **ctx,
                "namespace": obj.namespace,
                "name": obj.name,
                "version": obj.version,
            },
        )


class ArtifactRefSerializer(serializers.Serializer):
    """A serializer for an Artifact reference."""

    filename = serializers.CharField(source="relative_path")
    sha256 = serializers.CharField(source="artifact.sha256")
    size = serializers.IntegerField(source="artifact.size")


class CollectionRefSerializer(serializers.Serializer):
    """
    A serializer for a Collection reference.
    """

    id = serializers.CharField(source="pk")
    name = serializers.CharField()
    href = serializers.SerializerMethodField()

    def get_href(self, obj) -> str:
        """Returns link to a collection."""
        ctx = _get_distro_context(self.context)
        return reverse(
            settings.ANSIBLE_URL_NAMESPACE + "collections-detail",
            kwargs={**ctx, "namespace": obj.namespace, "name": obj.name},
        )


class CollectionMetadataSerializer(serializers.ModelSerializer):
    """
    A serializer for a CollectionVersion metadata.
    """

    tags = relations.ManyRelatedField(relations.StringRelatedField())

    class Meta:
        model = models.CollectionVersion
        fields = (
            "authors",
            "contents",
            "dependencies",
            "description",
            "documentation",
            "homepage",
            "issues",
            "license",
            "repository",
            "tags",
        )


class CollectionNamespaceSerializer(serializers.Serializer):
    """
    A serializer for a Collection Version namespace field.
    """

    name = serializers.CharField(source="namespace")


class CollectionVersionSignatureSerializer(serializers.ModelSerializer):
    """
    A serializer for the signatures on a Collection Version.
    """

    signature = serializers.SerializerMethodField()
    signing_service = serializers.SlugRelatedField(
        slug_field="name",
        allow_null=True,
        read_only=True,
    )

    def get_signature(self, obj):
        """
        Get the signature data.
        """
        return obj.data

    class Meta:
        model = models.CollectionVersionSignature
        fields = ("signature", "pubkey_fingerprint", "signing_service", "pulp_created")


class UnpaginatedCollectionVersionSerializer(CollectionVersionListSerializer):
    """
    A serializer for unpaginated CollectionVersion.
    """

    collection = CollectionRefSerializer(read_only=True)
    artifact = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()
    git_url = serializers.SerializerMethodField()
    git_commit_sha = serializers.SerializerMethodField()

    metadata = CollectionMetadataSerializer(source="*", read_only=True)
    namespace = CollectionNamespaceSerializer(source="*", read_only=True)
    signatures = serializers.SerializerMethodField()

    class Meta:
        model = models.CollectionVersion
        fields = CollectionVersionListSerializer.Meta.fields + (
            "artifact",
            "collection",
            "download_url",
            "name",
            "namespace",
            "signatures",
            "metadata",
            "git_url",
            "git_commit_sha",
        )

    @extend_schema_field(ArtifactRefSerializer)
    def get_artifact(self, obj):
        """
        Get atrifact summary.
        """
        content_artifact = ContentArtifact.objects.select_related("artifact").filter(content=obj)
        if content_artifact.get().artifact:
            return ArtifactRefSerializer(content_artifact.get()).data

    def get_download_url(self, obj) -> str:
        """
        Get artifact download URL.
        """
        content_artifact = ContentArtifact.objects.select_related("artifact").filter(content=obj)
        if content_artifact.get().artifact:
            distro_base_path = self.context.get("path", self.context["distro_base_path"])
            filename_path = obj.relative_path.lstrip("/")

            # Note: We're using ANSIBLE_API_HOSTNAME here instead of calling reverse with request=
            # because using the request context to generate the full URL causes the download URL
            # to be inaccessible when pulp is running behind a reverse proxy.
            host = settings.ANSIBLE_API_HOSTNAME.strip("/")
            path = reverse(
                settings.ANSIBLE_URL_NAMESPACE + "collection-artifact-download",
                kwargs={"distro_base_path": distro_base_path, "filename": filename_path},
            ).strip("/")

            return f"{host}/{path}"

    def get_git_url(self, obj) -> str:
        """
        Get the git URL.
        """
        content_artifact = ContentArtifact.objects.select_related("artifact").filter(content=obj)
        if not content_artifact.get().artifact:
            return content_artifact.get().remoteartifact_set.all()[0].url[:-47]

    def get_git_commit_sha(self, obj) -> str:
        """
        Get the git commit sha.
        """
        content_artifact = ContentArtifact.objects.select_related("artifact").filter(content=obj)
        if not content_artifact.get().artifact:
            return content_artifact.get().remoteartifact_set.all()[0].url[-40:]

    def get_signatures(self, obj):
        """
        Get the signatures.
        """
        filtered_signatures = obj.signatures.filter(pk__in=self.context.get("sigs", []))
        return CollectionVersionSignatureSerializer(filtered_signatures, many=True).data


class CollectionVersionSerializer(UnpaginatedCollectionVersionSerializer):
    """
    A serializer for a CollectionVersion.
    """

    manifest = serializers.JSONField(
        help_text="A JSON field holding MANIFEST.json data.", read_only=True
    )
    files = serializers.JSONField(help_text="A JSON field holding FILES.json data.", read_only=True)

    class Meta:
        model = models.CollectionVersion
        fields = UnpaginatedCollectionVersionSerializer.Meta.fields + (
            "manifest",
            "files",
        )


class CollectionVersionDocsSerializer(serializers.ModelSerializer):
    """A serializer to display the docs_blob of a CollectionVersion."""

    docs_blob = serializers.JSONField()

    class Meta:
        fields = ("docs_blob",)
        model = models.CollectionVersion


class RepoMetadataSerializer(serializers.ModelSerializer):
    """A serializer to display RepositoryVersion metadata."""

    published = serializers.DateTimeField(source="pulp_created")

    class Meta:
        fields = ("published",)
        model = RepositoryVersion


class ClientConfigurationSerializer(serializers.Serializer):
    """Configuration settings for the ansible-galaxy client."""

    default_distribution_path = serializers.CharField(allow_null=True)



class CollectionVersionSearchListSerializer(CollectionVersionListSerializer):

    # broken ...
    href = serializers.SerializerMethodField()

    # override because RepositoryContent != CollectionVersion without a cast ...
    pulp_id = serializers.SerializerMethodField()
    namespace = serializers.SerializerMethodField()
    name = serializers.SerializerMethodField()
    version = serializers.SerializerMethodField()
    is_highest = serializers.SerializerMethodField()
    #is_deprecated = serializers.SerializerMethodField()
    is_signed = serializers.SerializerMethodField()
    created_at = serializers.SerializerMethodField()
    updated_at = serializers.SerializerMethodField()
    requires_ansible = serializers.SerializerMethodField()
    dependencies = serializers.SerializerMethodField()
    tags = serializers.SerializerMethodField()
    signatures = serializers.SerializerMethodField()

    repository_name = serializers.SerializerMethodField()

    class Meta:
        fields = (
            "pulp_id",
            "namespace",
            "name",
            "version",
            "is_highest",
            #"is_deprecated",
            "is_signed",
            "href",
            "created_at",
            "updated_at",
            "requires_ansible",
            "dependencies",
            "repository_name",
            "tags",
            "signatures"
        )
        model = models.CollectionVersion

    def get_collection_version(self, obj):
        if isinstance(obj, models.CollectionVersion):
            return obj
        return obj.collection_version

    def get_pulp_id(self, obj):

        '''
        print(f'GET_PULP_ID obj:{obj}')
        for x in dir(obj):
            if x.startswith('_'):
                continue
            if x[0] != x[0].lower():
                continue
            print('\t' + x)
            #print('\t\t' + getattr(obj, x))

        #return self.get_collection_version(obj).pulp_id
        #return obj.pulp_id
        '''
        return obj.pk

    def get_namespace(self, obj):
        return self.get_collection_version(obj).namespace

    def get_name(self, obj):
        return self.get_collection_version(obj).name

    def get_version(self, obj):
        return self.get_collection_version(obj).version

    def get_created_at(self, obj):
        return self.get_collection_version(obj).pulp_created

    def get_updated_at(self, obj):
        return self.get_collection_version(obj).pulp_last_updated

    def get_is_highest(self, obj):
        return self.get_collection_version(obj).is_highest

    def get_requires_ansible(self, obj):
        return self.get_collection_version(obj).requires_ansible

    def get_dependencies(self, obj):
        return self.get_collection_version(obj).dependencies

    def get_href(self, obj) -> str:
        """Get href."""

        ctx = _get_distro_context({
            "path": obj.reponame,
            "distro_base_path": obj.reponame}
        )
        cv = self.get_collection_version(obj)
        return reverse(
            settings.ANSIBLE_URL_NAMESPACE + "collection-versions-detail",
            kwargs={**ctx, "namespace": cv.namespace, "name": cv.name, "version": cv.version},
        )

    def get_is_deprecated(self, obj):
        return obj.is_deprecated

    def get_is_signed(self, obj):
        return obj.sig_count > 0

    def get_tags(self, obj):
        return [x.name for x in self.get_collection_version(obj).tags.all()]

    def get_repository_name(self, obj):
        return obj.reponame

    def get_signatures(self, obj):
        if hasattr(obj, 'filtered_signatures'):
            return obj.filtered_signatures
        return []
