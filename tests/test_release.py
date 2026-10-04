from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import yaml

import main


class ReleaseTests(unittest.TestCase):
    def test_previous_version(self):
        versions = ["0.0.2", "0.0.10", "0.0.11", "0.1.0"]
        self.assertEqual(main._get_previous_version(versions, "0.0.11"), "0.0.10")

    def test_missing_previous_version(self):
        with self.assertRaises(ValueError):
            main._get_previous_version(["0.0.3"], "0.0.3")

    def test_prepare_release(self):
        digest = "sha256:" + "a" * 64
        with TemporaryDirectory() as directory:
            operator = Path(directory) / "operators/openstack-lightspeed-operator"
            (operator / "0.0.2").mkdir(parents=True)
            release = operator / "0.0.3"
            (release / "manifests").mkdir(parents=True)
            csv_path = release / "manifests/openstack-lightspeed-operator.clusterserviceversion.yaml"
            csv_path.write_text("""\
metadata:
  annotations: {}
spec:
  install:
    spec:
      deployments:
        - spec:
            template:
              spec:
                containers:
                  - env:
                      - name: OPENSHIFT_LIGHTSPEED_OPERATOR_VERSION
                        value: old
""")
            with patch("main._get_operator_image_digest", return_value=digest):
                main.main(directory, "0.0.3", "1.0.9", "latest")

            csv = yaml.safe_load(csv_path.read_text())
            self.assertEqual(csv["metadata"]["name"], "openstack-lightspeed-operator.v0.0.3")
            self.assertEqual(csv["spec"]["version"], "0.0.3")
            self.assertEqual(csv["spec"]["replaces"], "openstack-lightspeed-operator.v0.0.2")
            self.assertEqual(
                csv["metadata"]["annotations"]["containerImage"],
                f"quay.io/openstack-lightspeed/operator@{digest}",
            )
            deployment = csv["spec"]["install"]["spec"]["deployments"][0]
            env = deployment["spec"]["template"]["spec"]["containers"][0]["env"]
            self.assertEqual(env[0]["value"], "1.0.9")

            config = yaml.safe_load((release / "release-config.yaml").read_text())
            self.assertEqual(len(config["catalog_templates"]), 2)
            for template in config["catalog_templates"]:
                self.assertEqual(template["replaces"], "openstack-lightspeed-operator.v0.0.2")


if __name__ == "__main__":
    unittest.main()
