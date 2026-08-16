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
# After both imports succeed, the notebook automatically moves every returned
# report and semantic model into the same `data-agent-l400` folder as this
# notebook. Wait for the final success message confirming both imports and
# folder placement before opening reports or creating the Fabric Data Agent.
#
# The imports use `CreateOrOverwrite`. A safe rerun replaces the same-named
# reports and semantic models, including empty Git-deployed items left by an
# older `v0.1.3-test` installation.

# MARKDOWN ********************

# ## Step 1 - Review the immutable asset manifest
#
# The assets are downloaded from the immutable `v0.1.6-test` tag. SHA-256
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


REPOSITORY = "pawarbi/fda-l400"
REPOSITORY_REF = "v0.1.6-test"
EXPECTED_FOLDER_NAME = "data-agent-l400"
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

# ## Step 2 - Discover this notebook's workspace folder and acquire tokens
#
# No workspace, notebook, or folder ID is hardcoded. Runtime context identifies
# the current workspace and notebook. The Fabric Core item API then resolves
# this notebook's actual `folderId`.
#
# The recommended install requires this notebook to be inside a workspace
# folder. If it is at workspace root or folder discovery fails, the notebook
# stops before importing anything.

# CELL ********************

def require_uuid(value, label):
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Invalid or missing {label}: {value!r}") from exc


runtime_context = notebookutils.runtime.context
workspace_id = require_uuid(
    runtime_context.get("currentWorkspaceId"),
    "currentWorkspaceId in notebook runtime context",
)
notebook_id = require_uuid(
    runtime_context.get("currentNotebookId"),
    "currentNotebookId in notebook runtime context",
)

# The NotebookUtils `pbi` audience is documented for both Power BI and Fabric
# REST APIs. Acquire separate token values so each API call path is explicit.
power_bi_token = notebookutils.credentials.getToken("pbi")
fabric_api_token = notebookutils.credentials.getToken("pbi")
if not power_bi_token:
    raise RuntimeError("Power BI API token acquisition returned an empty token.")
if not fabric_api_token:
    raise RuntimeError("Fabric API token acquisition returned an empty token.")

fabric_headers = {
    "Authorization": f"Bearer {fabric_api_token}",
    "Content-Type": "application/json",
}
notebook_item_url = (
    "https://api.fabric.microsoft.com/v1/workspaces/"
    f"{workspace_id}/items/{notebook_id}"
)
notebook_item_response = requests.get(
    notebook_item_url,
    headers=fabric_headers,
    timeout=60,
)
if notebook_item_response.status_code != 200:
    raise RuntimeError(
        "Could not discover the InstallWorkshopAssets folder through the "
        f"Fabric Core item API: HTTP {notebook_item_response.status_code} "
        f"{notebook_item_response.text}"
    )

notebook_item = notebook_item_response.json()
folder_id_value = notebook_item.get("folderId")
if not folder_id_value:
    raise RuntimeError(
        "InstallWorkshopAssets is at workspace root. The recommended Jumpstart "
        "install requires this notebook inside the data-agent-l400 folder. "
        "No PBIX files were imported."
    )
folder_id = require_uuid(folder_id_value, "notebook folderId")

folder_url = (
    "https://api.fabric.microsoft.com/v1/workspaces/"
    f"{workspace_id}/folders/{folder_id}"
)
folder_response = requests.get(folder_url, headers=fabric_headers, timeout=60)
if folder_response.status_code != 200:
    raise RuntimeError(
        f"Could not read notebook folder {folder_id}: "
        f"HTTP {folder_response.status_code} {folder_response.text}"
    )
folder = folder_response.json()
folder_name = folder.get("displayName", "")

print("Target workspace:", workspace_id)
print("Current notebook:", f"{notebook_item.get('displayName', '')} ({notebook_id})")
print("Destination folder:", f"{folder_name} ({folder_id})")
if folder_name != EXPECTED_FOLDER_NAME:
    print(
        f"WARNING: expected folder name {EXPECTED_FOLDER_NAME!r}, found "
        f"{folder_name!r}. The actual containing folder ID will be used."
    )

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
        headers={"Authorization": f"Bearer {power_bi_token}"},
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
            headers={"Authorization": f"Bearer {power_bi_token}"},
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
                    "the response did not include both semantic model and report "
                    f"IDs. Import details: {json.dumps(import_result)}"
                )
            artifacts = []
            for item_type, imported_items in (
                ("SemanticModel", datasets),
                ("Report", reports),
            ):
                for imported_item in imported_items:
                    item_id = imported_item.get("id")
                    if not item_id:
                        raise RuntimeError(
                            f"PBIX import {import_id} omitted an expected "
                            f"{item_type} ID for {file_name}. "
                            f"Import details: {json.dumps(import_result)}"
                        )
                    artifacts.append(
                        {
                            "id": require_uuid(
                                item_id,
                                f"{item_type} ID returned by import {import_id}",
                            ),
                            "name": imported_item.get("name", ""),
                            "type": item_type,
                            "importId": import_id,
                            "sourceFile": file_name,
                        }
                    )
            return {
                "file": file_name,
                "importId": import_id,
                "artifacts": artifacts,
                "status": state,
                "details": import_result,
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
    imported_summary = ", ".join(
        f"{artifact['type']} {artifact['name'] or artifact['id']}"
        for artifact in result["artifacts"]
    )
    print(f"Import succeeded: {result['file']} -> {imported_summary}")

if len(import_results) != len(PBIX_ASSETS):
    raise RuntimeError(
        f"Only {len(import_results)} of {len(PBIX_ASSETS)} PBIX imports succeeded."
    )

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## Step 4 - Move and verify all imported artifacts
#
# The Fabric Core `bulkMove` request includes all returned report and semantic
# model IDs that are not already in this notebook's folder. They are moved
# together to respect parent/child move rules. Final success is printed only
# after every returned artifact is confirmed in the destination folder.

# CELL ********************

def get_fabric_item(item_id):
    item_url = (
        "https://api.fabric.microsoft.com/v1/workspaces/"
        f"{workspace_id}/items/{item_id}"
    )
    response = requests.get(item_url, headers=fabric_headers, timeout=60)
    if response.status_code != 200:
        raise RuntimeError(
            f"Could not inspect imported item {item_id}: "
            f"HTTP {response.status_code} {response.text}"
        )
    return response.json()


artifacts_by_id = {}
for import_result in import_results:
    for artifact in import_result["artifacts"]:
        artifacts_by_id[artifact["id"]] = artifact

expected_artifact_count = sum(
    len(import_result["artifacts"])
    for import_result in import_results
)
if len(artifacts_by_id) != expected_artifact_count:
    raise RuntimeError(
        "The PBIX import responses contained duplicate report or semantic model "
        "IDs. Refusing to continue without an unambiguous artifact set. "
        f"Import details: {json.dumps(import_results)}"
    )

items_before_move = {
    item_id: get_fabric_item(item_id)
    for item_id in artifacts_by_id
}
items_to_move = [
    item_id
    for item_id, item in items_before_move.items()
    if str(item.get("folderId", "")).lower() != folder_id.lower()
]

if items_to_move:
    bulk_move_url = (
        "https://api.fabric.microsoft.com/v1/workspaces/"
        f"{workspace_id}/items/bulkMove"
    )
    bulk_move_response = requests.post(
        bulk_move_url,
        headers=fabric_headers,
        json={
            "targetFolderId": folder_id,
            "items": items_to_move,
        },
        timeout=60,
    )
    if bulk_move_response.status_code != 200:
        raise RuntimeError(
            "Both PBIX imports succeeded, but moving the returned reports and "
            "semantic models into the Jumpstart folder failed. The imported "
            "items may remain at workspace root. "
            f"HTTP {bulk_move_response.status_code} {bulk_move_response.text}"
        )
    print(
        f"Moved {len(items_to_move)} imported artifacts into "
        f"{folder_name} ({folder_id})."
    )
else:
    print(
        "All returned reports and semantic models are already in "
        f"{folder_name} ({folder_id}); no move was required."
    )

confirmed_items = []
placement_errors = []
for item_id, artifact in artifacts_by_id.items():
    item = get_fabric_item(item_id)
    actual_folder_id = str(item.get("folderId", ""))
    if actual_folder_id.lower() != folder_id.lower():
        placement_errors.append(
            {
                "id": item_id,
                "name": item.get("displayName") or artifact["name"] or item_id,
                "type": item.get("type") or artifact["type"],
                "folderId": actual_folder_id or "<workspace root>",
            }
        )
    confirmed_items.append(
        {
            "name": item.get("displayName") or artifact["name"] or item_id,
            "type": item.get("type") or artifact["type"],
            "id": item_id,
            "folder": folder_name,
            "folderId": actual_folder_id,
        }
    )

if placement_errors:
    raise RuntimeError(
        "Both PBIX imports succeeded, but not all returned artifacts were "
        f"confirmed in folder {folder_name!r} ({folder_id}). The affected "
        "items may remain at workspace root or another folder: "
        f"{json.dumps(placement_errors)}"
    )

print("\nImported artifact placement:")
print(f"{'Type':<16} {'Name':<32} {'ID':<38} Folder")
for item in sorted(
    confirmed_items,
    key=lambda value: (value["type"], value["name"]),
):
    print(
        f"{item['type']:<16} {item['name']:<32} "
        f"{item['id']:<38} {item['folder']} ({item['folderId']})"
    )

print(
    "\nSUCCESS: Both populated PBIX imports succeeded and every returned "
    f"report and semantic model is in {folder_name} ({folder_id})."
)
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
# - **Folder move permissions:** the Fabric Core `bulkMove` API requires
#   Contributor or higher workspace role and delegated `Workspace.ReadWrite.All`.
# - **Notebook at workspace root:** reinstall using the recommended Jumpstart
#   flow so `InstallWorkshopAssets` is inside `data-agent-l400`; the notebook
#   intentionally stops before importing when no containing folder is detected.
# - **Name conflicts:** the notebook intentionally uses `CreateOrOverwrite`.
#   It replaces the same-named report and semantic model, including empty
#   Git-deployed items from an older `v0.1.3-test` installation.
# - **Failed import:** read the surfaced import response and import ID, correct
#   the reported issue, then select **Run all** again.
# - **Timed-out import:** use the surfaced import ID to inspect the import in
#   Power BI/Fabric. If it is no longer progressing, rerun the notebook.
# - **Move failure:** both imports may already exist at workspace root. The
#   notebook surfaces the Fabric API response and does not print final success.
#   Correct permissions or folder placement, then rerun.
# - **Rerun behavior:** rerunning is safe and imports both PBIX files again.
#   If a previous run stopped after one import, the next run overwrites that
#   item and completes the pair.
#
# The imported PBIX files already contain cached data, so
# `RefreshSemanticModel` is optional maintenance and is not required for the
# lab. A future data refresh requires the anonymous Web connection to be bound;
# use `RefreshSemanticModel` when updating data or repairing that connection.
