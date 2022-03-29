from pulp_ansible.tests.functional.utils import gen_collection_in_distribution
from pulp_ansible.tests.functional.utils import SyncHelpersMixin, TestCaseUsingBindings

from pulpcore.client.pulp_ansible.exceptions import ApiException
from pulp_smash.pulp3.bindings import monitor_task


class CollectionDeletionTestCase(TestCaseUsingBindings, SyncHelpersMixin):
    """Test collection deletion."""

    def setUp(self):
        """Set up the collection deletion tests."""
        (self.repo, self.distribution) = self._create_empty_repo_and_distribution()

        self.collection_versions = ["1.0.0", "1.0.1"]

        collection = gen_collection_in_distribution(
            self.distribution.base_path, versions=self.collection_versions
        )

        self.collection_name = collection["name"]
        self.collection_namespace = collection["namespace"]

    def test_collection_deletion(self):
        """Test deleting an entire collection."""
        collections = self.collections_v3api.list(self.distribution.base_path)
        assert collections.meta.count == 1

        resp = self.collections_v3api.delete(
            path=self.distribution.base_path,
            name=self.collection_name,
            namespace=self.collection_namespace,
        )
        monitor_task(resp.task)

        collections = self.collections_v3api.list(self.distribution.base_path)
        assert collections.meta.count == 0

        versions = self.collections_versions_v3api.list(
            path=self.distribution.base_path,
            name=self.collection_name,
            namespace=self.collection_namespace,
        )

        assert versions.meta.count == 0

        try:
            self.collections_v3api.read(
                path=self.distribution.base_path,
                name=self.collection_name,
                namespace=self.collection_namespace,
            )

            # Fail if 404 isn't raised
            assert False
        except ApiException as e:
            assert e.status == 404

    def test_collection_version_deletion(self):
        """Test deleting a specific collection version."""
        collections = self.collections_v3api.list(self.distribution.base_path)
        assert collections.meta.count == 1

        versions = self.collections_versions_v3api.list(
            path=self.distribution.base_path,
            name=self.collection_name,
            namespace=self.collection_namespace,
        )
        assert versions.meta.count == len(self.collection_versions)

        # Delete one version
        to_delete = self.collection_versions.pop()

        resp = self.collections_versions_v3api.delete(
            path=self.distribution.base_path,
            name=self.collection_name,
            namespace=self.collection_namespace,
            version=to_delete,
        )

        monitor_task(resp.task)

        try:
            self.collections_versions_v3api.read(
                path=self.distribution.base_path,
                name=self.collection_name,
                namespace=self.collection_namespace,
                version=to_delete,
            )

            # Fail if 404 isn't raised
            assert False
        except ApiException as e:
            assert e.status == 404

        # Verify that the collection still exists
        collections = self.collections_v3api.list(self.distribution.base_path)
        assert collections.meta.count == 1

        # Verify that the other versions still exist
        versions = self.collections_versions_v3api.list(
            path=self.distribution.base_path,
            name=self.collection_name,
            namespace=self.collection_namespace,
        )
        assert versions.meta.count == len(self.collection_versions)

        # Delete the rest of the versions

        for to_delete in self.collection_versions:
            resp = self.collections_versions_v3api.delete(
                path=self.distribution.base_path,
                name=self.collection_name,
                namespace=self.collection_namespace,
                version=to_delete,
            )

            monitor_task(resp.task)

        # Verify all the versions have been deleted
        versions = self.collections_versions_v3api.list(
            path=self.distribution.base_path,
            name=self.collection_name,
            namespace=self.collection_namespace,
        )

        assert versions.meta.count == 0

        # With all the versions deleted, verify that the collection has also
        # been deleted
        try:
            self.collections_v3api.read(
                path=self.distribution.base_path,
                name=self.collection_name,
                namespace=self.collection_namespace,
            )

            # Fail if 404 isn't raised
            assert False
        except ApiException as e:
            assert e.status == 404

    def test_invalid_deletion(self):
        """Test deleting collections that are dependencies for other collections."""
        dependent_version = self.collection_versions.pop()
        dependent_collection = gen_collection_in_distribution(
            self.distribution.base_path,
            dependencies={f"{self.collection_namespace}.{self.collection_name}": dependent_version},
        )

        err_msg = f"{dependent_collection['namespace']}.{dependent_collection['name']} 1.0.0"

        # Verify entire collection can't be deleted
        try:
            self.collections_v3api.delete(
                path=self.distribution.base_path,
                name=self.collection_name,
                namespace=self.collection_namespace,
            )

            # Fail if 400 isn't raised
            assert False
        except ApiException as e:
            assert e.status == 400

            # check error message includes collection that's blocking delete
            assert err_msg in e.body

        # Verify specific version that's used can't be deleted
        try:
            self.collections_versions_v3api.delete(
                path=self.distribution.base_path,
                name=self.collection_name,
                namespace=self.collection_namespace,
                version=dependent_version,
            )

            # Fail if 400 isn't raised
            assert False
        except ApiException as e:
            assert e.status == 400

            # check error message includes collection that's blocking delete
            assert err_msg in e.body

        # Verify non dependent version can be deleted.
        resp = self.collections_versions_v3api.delete(
            path=self.distribution.base_path,
            name=self.collection_name,
            namespace=self.collection_namespace,
            version=self.collection_versions[0],
        )

        resp = monitor_task(resp.task)
