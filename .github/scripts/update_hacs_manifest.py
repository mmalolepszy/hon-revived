"""Bump the integration version in manifest.json before packaging.

Usage: update_hacs_manifest.py --version <version>
"""

import json
import os
import sys


def update_manifest() -> None:
    """Update the manifest file."""
    version = "0.0.0"
    for index, value in enumerate(sys.argv):
        if value in ["--version", "-V"]:
            version = sys.argv[index + 1]

    with open(
        f"{os.getcwd()}/custom_components/hon/manifest.json",
    ) as manifestfile:
        manifest = json.load(manifestfile)

    manifest["version"] = version

    with open(
        f"{os.getcwd()}/custom_components/hon/manifest.json",
        "w",
    ) as manifestfile:
        manifestfile.write(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


update_manifest()
