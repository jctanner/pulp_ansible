#!/usr/bin/env bash

# WARNING: DO NOT EDIT!
#
# This file was generated by plugin_template, and is managed by it. Please use
# './plugin-template --github pulp_ansible' to update this file.
#
# For more info visit https://github.com/pulp/plugin_template

# make sure this script runs at the repo root
cd "$(dirname "$(realpath -e "$0")")"/../../..
REPO_ROOT="$PWD"

set -euv

source .github/workflows/scripts/utils.sh

if [[ "$TEST" = "docs" || "$TEST" = "publish" ]]; then
  pip install -r ../pulpcore/doc_requirements.txt
  pip install -r doc_requirements.txt
fi

pip install -r functest_requirements.txt

cd .ci/ansible/

TAG=ci_build

if [ -e $REPO_ROOT/../galaxy-importer ]; then
  GALAXY_IMPORTER=./galaxy-importer
else
  GALAXY_IMPORTER=git+https://github.com/ansible/galaxy-importer.git@master
fi
if [[ "$TEST" == "plugin-from-pypi" ]]; then
  PLUGIN_NAME=pulp_ansible
elif [[ "${RELEASE_WORKFLOW:-false}" == "true" ]]; then
  PLUGIN_NAME=./pulp_ansible/dist/pulp_ansible-$PLUGIN_VERSION-py3-none-any.whl
else
  PLUGIN_NAME=./pulp_ansible
fi
if [[ "${RELEASE_WORKFLOW:-false}" == "true" ]]; then
  # Install the plugin only and use published PyPI packages for the rest
  # Quoting ${TAG} ensures Ansible casts the tag as a string.
  cat >> vars/main.yaml << VARSYAML
image:
  name: pulp
  tag: "${TAG}"
plugins:
  - name: pulpcore
    source: pulpcore<3.17
  - name: pulp_ansible
    source:  "${PLUGIN_NAME}"
  - name: galaxy-importer
    source: galaxy-importer
services:
  - name: pulp
    image: "pulp:${TAG}"
    volumes:
      - ./settings:/etc/pulp
VARSYAML
else
  cat >> vars/main.yaml << VARSYAML
image:
  name: pulp
  tag: "${TAG}"
plugins:
  - name: pulp_ansible
    source: "${PLUGIN_NAME}"
  - name: galaxy-importer
    source: $GALAXY_IMPORTER
  - name: pulpcore
    source: ./pulpcore
services:
  - name: pulp
    image: "pulp:${TAG}"
    volumes:
      - ./settings:/etc/pulp
VARSYAML
fi

cat >> vars/main.yaml << VARSYAML
pulp_settings: {"allowed_export_paths": "/tmp", "allowed_import_paths": "/tmp", "ansible_api_hostname": "https://pulp:443", "ansible_content_hostname": "https://pulp:443/pulp/content"}
pulp_scheme: https

pulp_container_tag: https

VARSYAML

if [ "$TEST" = "s3" ]; then
  export MINIO_ACCESS_KEY=AKIAIT2Z5TDYPX3ARJBA
  export MINIO_SECRET_KEY=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
  sed -i -e '/^services:/a \
  - name: minio\
    image: minio/minio\
    env:\
      MINIO_ACCESS_KEY: "'$MINIO_ACCESS_KEY'"\
      MINIO_SECRET_KEY: "'$MINIO_SECRET_KEY'"\
    command: "server /data"' vars/main.yaml
  sed -i -e '$a s3_test: true\
minio_access_key: "'$MINIO_ACCESS_KEY'"\
minio_secret_key: "'$MINIO_SECRET_KEY'"' vars/main.yaml
fi

ansible-playbook build_container.yaml
ansible-playbook start_container.yaml
echo ::group::SSL
# Copy pulp CA
sudo docker cp pulp:/etc/pulp/certs/pulp_webserver.crt /usr/local/share/ca-certificates/pulp_webserver.crt

# Hack: adding pulp CA to certifi.where()
CERTIFI=$(python -c 'import certifi; print(certifi.where())')
cat /usr/local/share/ca-certificates/pulp_webserver.crt | sudo tee -a $CERTIFI

# Hack: adding pulp CA to default CA file
CERT=$(python -c 'import ssl; print(ssl.get_default_verify_paths().openssl_cafile)')
cat $CERTIFI | sudo tee -a $CERT

# Updating certs
sudo update-ca-certificates
echo ::endgroup::

echo ::group::PIP_LIST
cmd_prefix bash -c "pip3 list && pip3 install pipdeptree && pipdeptree"
echo ::endgroup::
