from django.contrib.postgres import search as psql_search
from django.db import migrations


CREATE_REPOSITORY_COLLECTIONVERSION_VIEW = '''
CREATE OR REPLACE VIEW repository_collection_version AS
SELECT
	distinct
	concat(cr.pulp_id, ':', acv.content_ptr_id) AS id,
	cr.pulp_id as repository_id,
	acv.content_ptr_id as collectionversion_id,
	cc.pulp_id as content_id,
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
			AND acv.content_ptr_id=crc2.content_id
	)>=1
ORDER BY
	acv.namespace,
	acv.name,
	acv.version,
	reponame
;
'''


DROP_REPOSITORY_COLLECTIONVERSION_VIEW = '''
DROP VIEW IF EXISTS repository_collection_version;
'''


class Migration(migrations.Migration):

    dependencies = [
        ('ansible', '0046_add_fulltext_search_fix'),
    ]

    operations = [
        migrations.RunSQL(
            sql=CREATE_REPOSITORY_COLLECTIONVERSION_VIEW,
            reverse_sql=DROP_REPOSITORY_COLLECTIONVERSION_VIEW,
        ),
    ]
