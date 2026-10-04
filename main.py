import argparse
import os
import re

import requests
import yaml


def _is_dir_name_semver(dir_name: str) -> bool:
    return re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", dir_name) is not None


def _get_all_versions(repo_path: str) -> list[str]:
    dir_names = os.listdir(os.path.join(repo_path, "operators/openstack-lightspeed-operator"))
    return [
        dir_name for dir_name in dir_names
        if _is_dir_name_semver(dir_name)
        and os.path.isdir(os.path.join(repo_path, "operators/openstack-lightspeed-operator", dir_name))
    ]


def _get_previous_version(all_versions: list[str], new_version: str) -> str:
    def version_key(version: str) -> tuple[int, ...]:
        return tuple(int(part) for part in version.split("."))

    previous_versions = [
        version for version in all_versions
        if version_key(version) < version_key(new_version)
    ]
    if not previous_versions:
        raise ValueError(f"No existing release precedes {new_version}.")
    return max(previous_versions, key=version_key)


def _get_operator_image_digest(image_tag: str) -> str:
    response = requests.get(
        "https://quay.io/api/v1/repository/openstack-lightspeed/operator/tag/",
        params={"specificTag": image_tag, "onlyActiveTags": "true"},
        timeout=30,
    )
    response.raise_for_status()

    tags = response.json().get("tags", [])
    for tag in tags:
        if tag.get("name") == image_tag:
            digest = tag.get("manifest_digest", "")
            if re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
                return digest
    raise ValueError(f"No active operator image with a valid digest for tag {image_tag!r}.")


def _modify_csv(
    repo_path: str,
    new_version: str,
    previous_version: str,
    operator_image_digest: str,
    openshift_lightspeed_operator_version: str,
) -> None:
    csv_path = os.path.join(
        repo_path,
        f"operators/openstack-lightspeed-operator/{new_version}/manifests/openstack-lightspeed-operator.clusterserviceversion.yaml"
    )

    def set_openshift_lightspeed_operator_version(node) -> None:
        if isinstance(node, dict):
            if node.get("name") == "OPENSHIFT_LIGHTSPEED_OPERATOR_VERSION":
                node["value"] = openshift_lightspeed_operator_version

            for child in node.values():
                set_openshift_lightspeed_operator_version(child)

        elif isinstance(node, list):
            for item in node:
                set_openshift_lightspeed_operator_version(item)

    with open(csv_path) as f:
        csv = yaml.safe_load(f)
        csv["metadata"]["name"] = f"openstack-lightspeed-operator.v{new_version}"
        csv["metadata"]["annotations"]["containerImage"] = f"quay.io/openstack-lightspeed/operator@{operator_image_digest}"
        csv["metadata"]["annotations"]["support"] = "Community"
        csv["spec"]["displayName"] = "OpenStack Lightspeed (Community)"
        csv["spec"]["replaces"] = f"openstack-lightspeed-operator.v{previous_version}"
        csv["spec"]["version"] = new_version
        set_openshift_lightspeed_operator_version(csv)
    with open(csv_path, "w") as f:
        yaml.safe_dump(csv, f)


def _create_release_config(repo_path: str, previous_version: str, new_version: str) -> None:
    release_config = {
        "catalog_templates": [
            {
                "template_name": "v4.16.yaml",
                "channels": ["alpha"],
                "replaces": f"openstack-lightspeed-operator.v{previous_version}",
            },
            {
                "template_name": "v4.18.yaml",
                "channels": ["alpha"],
                "replaces": f"openstack-lightspeed-operator.v{previous_version}",
            },
        ]
    }

    release_config_path = os.path.join(repo_path, f"operators/openstack-lightspeed-operator/{new_version}/release-config.yaml")

    with open(release_config_path, "w") as f:
        yaml.safe_dump(release_config, f)


def main(
    repo_path: str,
    new_version: str,
    openshift_lightspeed_operator_version: str,
    image_tag: str,
):
    if not _is_dir_name_semver(new_version):
        raise ValueError("new_version must have the form X.Y.Z (for example, 0.0.3).")
    all_versions = _get_all_versions(repo_path)
    previous_version = _get_previous_version(all_versions, new_version)
    operator_image_digest = _get_operator_image_digest(image_tag)
    _modify_csv(
        repo_path=repo_path,
        new_version=new_version,
        previous_version=previous_version,
        openshift_lightspeed_operator_version=openshift_lightspeed_operator_version,
        operator_image_digest=operator_image_digest,
    )
    _create_release_config(
        repo_path=repo_path,
        previous_version=previous_version,
        new_version=new_version,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prepare an OpenStack Lightspeed community release.")
    parser.add_argument("--repo-path", default=os.environ.get("REPO_PATH", "/tmp/community-operators-prod"))
    parser.add_argument("--new-version", required=True)
    parser.add_argument("--openshift-lightspeed-operator-version", required=True)
    parser.add_argument("--image-tag", default="latest")
    args = parser.parse_args()
    main(
        repo_path=args.repo_path,
        new_version=args.new_version,
        openshift_lightspeed_operator_version=args.openshift_lightspeed_operator_version,
        image_tag=args.image_tag,
    )
