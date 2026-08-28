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

# # Getting Started with Data Agents
#
# **Required first step after installation**
#
# This Jumpstart teaches you how to create, optimize, govern, extend, and
# evaluate Microsoft Fabric Data Agents. You will compare a baseline semantic
# model with an AI-ready model, build Data Agents over one and multiple data
# sources, and measure response quality with repeatable evaluations.
#
# **Run this notebook now without changing any values:** select **Run all** and
# wait for the final success message. This one-time setup:
#
# 1. Downloads and validates the two immutable PBIX assets.
# 2. Imports the baseline and AI-ready semantic models and reports.
# 3. Moves the imported items into this Jumpstart's workspace folder.
# 4. Runs a populated-data DAX validation against both semantic models.
#
# Do not continue to the labs until setup succeeds. Rerunning is safe because
# imports use `CreateOrOverwrite`.
#
# **Workshop instructions:** [Open the lab instructions on
# GitHub](https://github.com/pawarbi/fda-l400/tree/main/documentation/lab-instructions).
# This link will move to the Microsoft repository when the Jumpstart source is
# transferred.

# MARKDOWN ********************

# ## Workshop map
#
# ```text
# SetupDataAgentJumpstart
#     -> ManufacturingOps model + report
#     -> ManufacturingOpsAIReady model + report
#     |
#     +-> Lab 1: create and optimize Data Agents
#     |
#     +-> Lab 2: calibrate and run evaluations
#     |
#     +-> Lab 3: add OpsRefData and publish a multi-source Data Agent
# ```
#
# | Lab | What you will do | Items needed at the start | Items created or used |
# | --- | --- | --- | --- |
# | **Setup - Prepare the workspace** | Run this notebook once to import, organize, and validate the populated workshop assets. | `SetupDataAgentJumpstart` | `ManufacturingOps` semantic model and report; `ManufacturingOpsAIReady` semantic model and report |
# | **Lab 1 - Create and optimize Data Agents** | Create a first Data Agent, inspect generated DAX and responses, compare the baseline and AI-ready models, configure Prep data for AI and agent instructions, compare runtimes, and use Code Interpreter. | Both imported semantic models and reports | A baseline Data Agent and an optimized AI-ready Data Agent that you create in the Fabric portal |
# | **Lab 2 - Evaluate Data Agents** | Calibrate an LLM-as-Judge, run a fixed evaluation set through the Data Agent SDK, and inspect accuracy, reasoning, latency, and MLflow results. | Your optimized AI-ready Data Agent from Lab 1; `JudgeCalibration`; `EvaluateDataAgent` | An evaluation Lakehouse, an MLflow experiment, a registered champion judge, and evaluation runs |
# | **Lab 3 - Add multiple data sources** | Build a Lakehouse reference source, add it to a copied agent configuration with the Python SDK, publish the multi-source agent, and refine it with Build agent with AI. | Your AI-ready Data Agent from Lab 1; `BuildOpsRefData`; `CreateMultiSourceDataAgent` | `OpsRefData` Lakehouse and SQL endpoint; a new Data Agent whose name ends in `_MultiSource` |
#
# `RefreshSemanticModel` is optional maintenance. It is not required for the
# initial workshop because the imported PBIX files already contain populated
# cached data.

# MARKDOWN ********************

# ## Step 1 - Run setup without changes
#
# The parameter cell below contains the tested source and timeout values for
# this Jumpstart build. **Do not edit them for the workshop.** Maintainers use
# these parameters only when validating another source repository or release.

# CELL ********************

# PARAMETERS
REPOSITORY = "pawarbi/fda-l400"
REPOSITORY_REF = "v1.0.2"
EXPECTED_FOLDER_NAME = "getting-started-data-agents"
IMPORT_TIMEOUT_MINUTES = 10
POLL_INTERVAL_SECONDS = 5

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

import hashlib
import io
import json
import time
from urllib.parse import quote
from uuid import UUID

import notebookutils
import requests


RAW_BASE_URL = (
    f"https://raw.githubusercontent.com/{REPOSITORY}/{REPOSITORY_REF}"
)

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
        "Could not discover the SetupDataAgentJumpstart folder through the "
        f"Fabric Core item API: HTTP {notebook_item_response.status_code} "
        f"{notebook_item_response.text}"
    )

notebook_item = notebook_item_response.json()
folder_id_value = notebook_item.get("folderId")
if not folder_id_value:
    raise RuntimeError(
        "SetupDataAgentJumpstart is at workspace root. The recommended Jumpstart "
        f"install requires this notebook inside the {EXPECTED_FOLDER_NAME} folder. "
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
        headers={"User-Agent": "getting-started-data-agents-installer"},
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
    "\nPlacement confirmed: both populated PBIX imports succeeded and every "
    f"returned report and semantic model is in {folder_name} ({folder_id})."
)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## Step 5 - Verify populated data in both semantic models
#
# SemPy runs this exact DAX query against `ManufacturingOps` and
# `ManufacturingOpsAIReady` in the current workspace:
#
# ```dax
# EVALUATE
#     TOPN(2, 'Customers')
# ```
#
# A bounded retry handles brief post-import model availability delays. Any
# permanent query failure or result other than exactly two rows stops the
# notebook without printing final installation success.

# CELL ********************

import sempy.fabric as fabric


DAX_QUERY = """EVALUATE
    TOPN(2, 'Customers')"""
DAX_VALIDATION_ATTEMPTS = 12
DAX_RETRY_SECONDS = 10
SEMANTIC_MODELS = ["ManufacturingOps", "ManufacturingOpsAIReady"]


def validate_populated_model(model_name):
    for attempt in range(1, DAX_VALIDATION_ATTEMPTS + 1):
        print(
            f"DAX validation attempt {attempt}/{DAX_VALIDATION_ATTEMPTS}: "
            f"{model_name}"
        )
        try:
            result = fabric.evaluate_dax(
                dataset=model_name,
                dax_string=DAX_QUERY,
                workspace=workspace_id,
            )
        except Exception as exc:
            if attempt == DAX_VALIDATION_ATTEMPTS:
                raise RuntimeError(
                    f"DAX validation failed for {model_name} after "
                    f"{DAX_VALIDATION_ATTEMPTS} attempts: {exc}"
                ) from exc
            print(
                f"{model_name} is not queryable yet: "
                f"{type(exc).__name__}: {exc}. "
                f"Retrying in {DAX_RETRY_SECONDS} seconds."
            )
            time.sleep(DAX_RETRY_SECONDS)
            continue

        row_count = len(result.index)
        if row_count != 2:
            raise RuntimeError(
                f"DAX validation for {model_name} returned {row_count} rows; "
                "expected exactly 2. The imported model data is not ready or "
                "does not match the workshop PBIX."
            )
        print(f"DAX validation passed: {model_name} returned exactly 2 rows.")
        return result

    raise RuntimeError(f"DAX validation retry loop ended unexpectedly: {model_name}")


dax_validation_results = {}
for semantic_model in SEMANTIC_MODELS:
    dax_result = validate_populated_model(semantic_model)
    dax_validation_results[semantic_model] = dax_result
    print(f"\n{semantic_model} validation preview:")
    display(dax_result.head(2))

if set(dax_validation_results) != set(SEMANTIC_MODELS):
    raise RuntimeError(
        "DAX validation did not complete for both workshop semantic models."
    )

print("\nPopulated-data validation summary:")
for semantic_model in SEMANTIC_MODELS:
    print(
        f"- {semantic_model}: "
        f"{len(dax_validation_results[semantic_model].index)} rows"
    )

print(
    "\nSUCCESS: Both populated PBIX imports succeeded, every returned report "
    f"and semantic model is in {folder_name} ({folder_id}), and both semantic "
    "models returned exactly 2 rows for the required DAX validation."
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
#   flow so `SetupDataAgentJumpstart` is inside
#   `getting-started-data-agents`; the notebook
#   intentionally stops before importing when no containing folder is detected.
# - **Name conflicts:** the notebook intentionally uses `CreateOrOverwrite`,
#   replacing the same-named report and semantic model.
# - **Failed import:** read the surfaced import response and import ID, correct
#   the reported issue, then select **Run all** again.
# - **Timed-out import:** use the surfaced import ID to inspect the import in
#   Power BI/Fabric. If it is no longer progressing, rerun the notebook.
# - **Move failure:** both imports may already exist at workspace root. The
#   notebook surfaces the Fabric API response and does not print final success.
#   Correct permissions or folder placement, then rerun.
# - **DAX validation retries:** brief post-import availability errors are logged
#   and retried for up to two minutes. A permanent SemPy/query failure or any
#   row count other than exactly two names the affected semantic model and stops
#   without final success.
# - **Rerun behavior:** rerunning is safe and imports both PBIX files again.
#   If a previous run stopped after one import, the next run overwrites that
#   item and completes the pair.
# ## Continue after setup
#
# 1. Compare the `ManufacturingOps` and `ManufacturingOpsAIReady` reports and
#    semantic models.
# 2. Create the base Data Agent from `ManufacturingOpsAIReady`.
# 3. Run `BuildOpsRefData` to create the Lakehouse reference source.
# 4. Run `CreateMultiSourceDataAgent` to add the Lakehouse source.
# 5. Run `JudgeCalibration`, then `EvaluateDataAgent`.
#
# `RefreshSemanticModel` is optional maintenance and is not required for the
# initial walkthrough. Use it only for a future data update or to repair the
# anonymous Web connection.
