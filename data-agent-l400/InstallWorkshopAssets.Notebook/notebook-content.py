# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "jupyter",
# META     "jupyter_kernel_name": "python3.11"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse_name": "",
# META       "default_lakehouse_workspace_id": ""
# META     }
# META   }
# META }

# MARKDOWN ********************

# # InstallWorkshopAssets - Fabric Data Agent L400
#
# **Required once after installation.**
#
# Select **Run all** in the same workspace where Jumpstart installed the
# notebooks. This notebook imports the populated `ManufacturingOps.pbix` and
# `ManufacturingOpsAIReady.pbix` files through the Power BI Imports API.
# Their cached data is available immediately after successful import, so the
# workshop labs do not require a semantic model refresh.
#
# Wait for the final success message confirming both PBIX imports before
# opening reports or creating the Fabric Data Agent.
#
# The imports use `CreateOrOverwrite`. A safe rerun replaces the same-named
# reports and semantic models, including empty Git-deployed items left by an
# older `v0.1.3-test` installation.

# MARKDOWN ********************

# ## Step 1 - Review the immutable asset manifest
#
# The assets are downloaded from the immutable `v0.1.5-test` tag. SHA-256
# validation prevents an incomplete download or Git LFS pointer from being
# imported.

# CELL ********************

import hashlib
import io
import json
import time
from urllib.parse import quote
from uuid import UUID

import notebookutils
import requests
import sempy.fabric as fabric


REPOSITORY = "pawarbi/fda-l400"
REPOSITORY_REF = "v0.1.5-test"
RAW_BASE_URL = (
    f"https://raw.githubusercontent.com/{REPOSITORY}/{REPOSITORY_REF}"
)
IMPORT_TIMEOUT_MINUTES = 10
POLL_INTERVAL_SECONDS = 5

PBIX_ASSETS = [
    {
        "file_name": "ManufacturingOps.pbix",
        "sha256": "BFC0F3EA44F51EE5A3BE0739BDF268EE298336066CC734306594B4C6B1428F09",
    },
    {
        "file_name": "ManufacturingOpsAIReady.pbix",
        "sha256": "95C9F8D395AD3197EB7EB835BB542521C9DBF8C31077C3218842E8B931A9F8EE",
    },
]

for asset in PBIX_ASSETS:
    asset["path"] = f"assets/pbix/{asset['file_name']}"
    asset["url"] = f"{RAW_BASE_URL}/{quote(asset['path'], safe='/')}"

print("Source:", f"{REPOSITORY}@{REPOSITORY_REF}")
for asset in PBIX_ASSETS:
    print("PBIX:", asset["url"])

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## Step 2 - Discover the current workspace and acquire a Power BI token
#
# No workspace ID is hardcoded. The current notebook workspace is always the
# import target.

# CELL ********************

workspace_id = str(fabric.get_notebook_workspace_id())
try:
    workspace_id = str(UUID(workspace_id))
except ValueError as exc:
    raise RuntimeError(
        f"Fabric returned an invalid notebook workspace ID: {workspace_id!r}"
    ) from exc

access_token = notebookutils.credentials.getToken("pbi")
if not access_token:
    raise RuntimeError("Power BI token acquisition returned an empty token.")

print("Target workspace:", workspace_id)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## Step 3 - Download, validate, import, and poll each PBIX
#
# Each upload uses `CreateOrOverwrite`. The notebook surfaces HTTP, import, and
# timeout failures directly; it does not print the final success message unless
# both imports reach `Succeeded`.

# CELL ********************

def download_pbix(asset):
    response = requests.get(
        asset["url"],
        headers={"User-Agent": "fabric-data-agent-l400-installer"},
        timeout=180,
    )
    response.raise_for_status()
    content = response.content
    if content.startswith(b"version https://git-lfs.github.com/spec/v1"):
        raise RuntimeError(
            f"{asset['path']} resolved to a Git LFS pointer instead of PBIX content."
        )

    actual_hash = hashlib.sha256(content).hexdigest().upper()
    if actual_hash != asset["sha256"]:
        raise RuntimeError(
            f"SHA-256 mismatch for {asset['file_name']}: "
            f"expected {asset['sha256']}, received {actual_hash}."
        )
    print(
        f"Downloaded and validated: {asset['file_name']} "
        f"({len(content):,} bytes)"
    )
    return content


def import_pbix(asset, pbix_content):
    file_name = asset["file_name"]
    import_url = (
        "https://api.powerbi.com/v1.0/myorg/groups/"
        f"{workspace_id}/imports"
        f"?datasetDisplayName={quote(file_name)}"
        "&nameConflict=CreateOrOverwrite"
    )
    response = requests.post(
        import_url,
        headers={"Authorization": f"Bearer {access_token}"},
        files={
            "file": (
                file_name,
                io.BytesIO(pbix_content),
                "application/octet-stream",
            )
        },
        timeout=600,
    )
    if response.status_code not in (200, 201, 202):
        raise RuntimeError(
            f"PBIX upload failed for {file_name}: "
            f"HTTP {response.status_code} {response.text}"
        )

    try:
        import_id = response.json()["id"]
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(
            f"PBIX upload for {file_name} did not return an import ID: "
            f"HTTP {response.status_code} {response.text}"
        ) from exc

    print(f"Upload accepted: {file_name} (import ID: {import_id})")
    status_url = (
        "https://api.powerbi.com/v1.0/myorg/groups/"
        f"{workspace_id}/imports/{import_id}"
    )
    attempts = max(
        1,
        IMPORT_TIMEOUT_MINUTES * 60 // POLL_INTERVAL_SECONDS,
    )
    last_state = "Unknown"
    for _ in range(attempts):
        status_response = requests.get(
            status_url,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=60,
        )
        status_response.raise_for_status()
        import_result = status_response.json()
        state = import_result.get("importState", "Unknown")
        if state != last_state:
            print(f"Import state for {file_name}: {state}")
            last_state = state

        if state == "Succeeded":
            datasets = import_result.get("datasets", [])
            reports = import_result.get("reports", [])
            if not datasets or not reports:
                raise RuntimeError(
                    f"PBIX import {import_id} succeeded for {file_name}, but "
                    "the response did not include both a semantic model and report."
                )
            return {
                "file": file_name,
                "importId": import_id,
                "semanticModel": datasets[0].get("name", ""),
                "semanticModelId": datasets[0].get("id", ""),
                "report": reports[0].get("name", ""),
                "reportId": reports[0].get("id", ""),
                "reportUrl": reports[0].get("webUrl", ""),
                "status": state,
            }
        if state == "Failed":
            raise RuntimeError(
                f"PBIX import failed for {file_name} (import ID: {import_id}): "
                f"{json.dumps(import_result)}"
            )
        time.sleep(POLL_INTERVAL_SECONDS)

    raise TimeoutError(
        f"PBIX import timed out for {file_name} after "
        f"{IMPORT_TIMEOUT_MINUTES} minutes (import ID: {import_id}, "
        f"last state: {last_state})."
    )


import_results = []
for pbix_asset in PBIX_ASSETS:
    print(f"\nStarting PBIX import: {pbix_asset['file_name']}")
    content = download_pbix(pbix_asset)
    result = import_pbix(pbix_asset, content)
    import_results.append(result)
    print(
        f"Import succeeded: {result['file']} -> "
        f"{result['semanticModel']} / {result['report']}"
    )

if len(import_results) != len(PBIX_ASSETS):
    raise RuntimeError(
        f"Only {len(import_results)} of {len(PBIX_ASSETS)} PBIX imports succeeded."
    )

print("\nSUCCESS: Both populated workshop PBIX imports completed successfully.")
print("The reports and semantic models are ready for the workshop labs.")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## Troubleshooting and reruns
#
# - **Import permissions (401/403):** confirm you can create and overwrite
#   Power BI reports and semantic models in this workspace and that its capacity
#   supports the Power BI Imports API.
# - **Name conflicts:** the notebook intentionally uses `CreateOrOverwrite`.
#   It replaces the same-named report and semantic model, including empty
#   Git-deployed items from an older `v0.1.3-test` installation.
# - **Failed import:** read the surfaced import response and import ID, correct
#   the reported issue, then select **Run all** again.
# - **Timed-out import:** use the surfaced import ID to inspect the import in
#   Power BI/Fabric. If it is no longer progressing, rerun the notebook.
# - **Rerun behavior:** rerunning is safe and imports both PBIX files again.
#   If a previous run stopped after one import, the next run overwrites that
#   item and completes the pair.
#
# The imported PBIX files already contain cached data, so
# `RefreshSemanticModel` is optional maintenance and is not required for the
# lab. A future data refresh requires the anonymous Web connection to be bound;
# use `RefreshSemanticModel` when updating data or repairing that connection.
