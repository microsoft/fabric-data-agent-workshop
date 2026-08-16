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

# # ImportWorkshopAssets (instructor only)
#
# Reusable instructor utility for importing both canonical populated workshop
# PBIX files into explicitly selected Fabric workspaces. The target workspace
# can be a name or GUID and does not need to be the notebook's workspace.
#
# The function uses `CreateOrOverwrite`, verifies the returned report and
# semantic model IDs, and moves all returned assets together with the Fabric
# Core `bulkMove` API. Model queries are disabled unless
# `validate_models=True`.
#
# By default, `import_workshop_assets(workspace)` resolves the unique
# `data-agent-l400` folder and creates it at workspace root if it is missing.
# Pass `folder=None` explicitly to place the imported assets at workspace root.
#
# Required delegated scopes and access:
#
# - Power BI Imports API: `Dataset.ReadWrite.All`
# - Fabric Core workspace/folder/item APIs: `Workspace.ReadWrite.All`
# - Contributor or higher on each target workspace

# CELL ********************

import hashlib
import io
import json
import time
from pathlib import PurePosixPath
from urllib.parse import quote
from uuid import UUID

import notebookutils
import requests


DEFAULT_REPOSITORY = "pawarbi/fda-l400"
DEFAULT_REPO_REF = "v0.1.8-test"
DEFAULT_DESTINATION_FOLDER = "data-agent-l400"
DEFAULT_IMPORT_TIMEOUT_MINUTES = 10
DEFAULT_POLL_INTERVAL_SECONDS = 5
DEFAULT_VALIDATION_ATTEMPTS = 12
DEFAULT_VALIDATION_RETRY_SECONDS = 10

PBIX_ASSETS = (
    {
        "file_name": "ManufacturingOps.pbix",
        "sha256": "BFC0F3EA44F51EE5A3BE0739BDF268EE298336066CC734306594B4C6B1428F09",
    },
    {
        "file_name": "ManufacturingOpsAIReady.pbix",
        "sha256": "95C9F8D395AD3197EB7EB835BB542521C9DBF8C31077C3218842E8B931A9F8EE",
    },
)

DAX_QUERY = """EVALUATE
    TOPN(2, 'Customers')"""

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

def _as_uuid(value, label):
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a GUID; received {value!r}.") from exc


def _is_uuid(value):
    try:
        UUID(str(value))
        return True
    except (TypeError, ValueError):
        return False


def _error_text(response):
    request_id = response.headers.get("requestId") or response.headers.get(
        "x-ms-request-id"
    )
    suffix = f" Request ID: {request_id}." if request_id else ""
    return f"HTTP {response.status_code}: {response.text}{suffix}"


def _raise_api_error(response, operation, required_access):
    if response.status_code in (401, 403):
        raise PermissionError(
            f"{operation} was denied. Required access: {required_access}. "
            f"{_error_text(response)}"
        )
    raise RuntimeError(f"{operation} failed. {_error_text(response)}")


def _get_with_retry(url, headers=None, timeout=60, operation="GET request"):
    last_response = None
    for attempt in range(1, 5):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
        except requests.RequestException as exc:
            if attempt == 4:
                raise RuntimeError(
                    f"{operation} failed after {attempt} attempts: {exc}"
                ) from exc
            time.sleep(min(2**attempt, 10))
            continue

        last_response = response
        if response.status_code not in (429, 500, 502, 503, 504):
            return response
        if attempt < 4:
            delay = int(response.headers.get("Retry-After", min(2**attempt, 10)))
            time.sleep(delay)

    return last_response


def _list_pages(url, headers, operation, required_access):
    values = []
    next_url = url
    while next_url:
        response = _get_with_retry(
            next_url,
            headers=headers,
            timeout=60,
            operation=operation,
        )
        if response.status_code != 200:
            _raise_api_error(response, operation, required_access)
        try:
            payload = response.json()
            values.extend(payload.get("value", []))
            next_url = payload.get("continuationUri")
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                f"{operation} returned invalid JSON. {_error_text(response)}"
            ) from exc
    return values


def _acquire_headers():
    power_bi_token = notebookutils.credentials.getToken("pbi")
    fabric_token = notebookutils.credentials.getToken("pbi")
    if not power_bi_token:
        raise PermissionError(
            "Power BI token acquisition returned an empty token. "
            "Dataset.ReadWrite.All is required."
        )
    if not fabric_token:
        raise PermissionError(
            "Fabric token acquisition returned an empty token. "
            "Workspace.ReadWrite.All is required."
        )
    return (
        {"Authorization": f"Bearer {power_bi_token}"},
        {
            "Authorization": f"Bearer {fabric_token}",
            "Content-Type": "application/json",
        },
    )


def _resolve_workspace(workspace, fabric_headers):
    if workspace is None or not str(workspace).strip():
        raise ValueError("workspace must be a workspace name or GUID.")

    workspace_value = str(workspace).strip()
    if _is_uuid(workspace_value):
        workspace_id = _as_uuid(workspace_value, "workspace")
        url = f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}"
        response = _get_with_retry(
            url,
            headers=fabric_headers,
            operation=f"Reading workspace {workspace_id}",
        )
        if response.status_code != 200:
            _raise_api_error(
                response,
                f"Reading workspace {workspace_id}",
                "Workspace.ReadWrite.All and access to the target workspace",
            )
        resolved = response.json()
        return {
            "id": workspace_id,
            "name": resolved.get("displayName", ""),
            "input": workspace,
        }

    workspaces = _list_pages(
        "https://api.fabric.microsoft.com/v1/workspaces",
        fabric_headers,
        "Listing accessible Fabric workspaces",
        "Workspace.ReadWrite.All",
    )
    matches = [
        item
        for item in workspaces
        if str(item.get("displayName", "")).casefold() == workspace_value.casefold()
    ]
    if not matches:
        raise LookupError(
            f"No accessible Fabric workspace is named {workspace_value!r}."
        )
    if len(matches) > 1:
        match_ids = [item.get("id") for item in matches]
        raise LookupError(
            f"Workspace name {workspace_value!r} is ambiguous; matching IDs: "
            f"{match_ids}. Pass a workspace GUID."
        )
    return {
        "id": _as_uuid(matches[0].get("id"), "resolved workspace ID"),
        "name": matches[0].get("displayName", ""),
        "input": workspace,
    }


def _resolve_folder(
    workspace_id,
    folder,
    create_folder_if_missing,
    fabric_headers,
):
    if folder is None or not str(folder).strip():
        return {"id": None, "name": None, "location": "workspace root"}

    folder_value = str(folder).strip()
    base_url = (
        f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/folders"
    )
    if _is_uuid(folder_value):
        folder_id = _as_uuid(folder_value, "folder")
        response = _get_with_retry(
            f"{base_url}/{folder_id}",
            headers=fabric_headers,
            operation=f"Reading folder {folder_id}",
        )
        if response.status_code != 200:
            _raise_api_error(
                response,
                f"Reading folder {folder_id} in workspace {workspace_id}",
                "Workspace.ReadWrite.All and access to the target workspace",
            )
        resolved = response.json()
        return {
            "id": folder_id,
            "name": resolved.get("displayName", ""),
            "location": resolved.get("displayName", folder_id),
        }

    folders = _list_pages(
        base_url,
        fabric_headers,
        f"Listing folders in workspace {workspace_id}",
        "Workspace.ReadWrite.All and access to the target workspace",
    )
    matches = [
        item
        for item in folders
        if str(item.get("displayName", "")).casefold() == folder_value.casefold()
    ]
    if len(matches) > 1:
        match_ids = [item.get("id") for item in matches]
        raise LookupError(
            f"Folder name {folder_value!r} is ambiguous in workspace "
            f"{workspace_id}; matching IDs: {match_ids}. Pass a folder GUID."
        )
    if matches:
        return {
            "id": _as_uuid(matches[0].get("id"), "resolved folder ID"),
            "name": matches[0].get("displayName", ""),
            "location": matches[0].get("displayName", folder_value),
        }
    if not create_folder_if_missing:
        raise LookupError(
            f"No folder named {folder_value!r} exists in workspace {workspace_id}. "
            "Pass create_folder_if_missing=True to create it at workspace root."
        )

    response = requests.post(
        base_url,
        headers=fabric_headers,
        json={"displayName": folder_value},
        timeout=60,
    )
    if response.status_code != 201:
        _raise_api_error(
            response,
            f"Creating folder {folder_value!r} in workspace {workspace_id}",
            "Contributor or higher and Workspace.ReadWrite.All",
        )
    created = response.json()
    return {
        "id": _as_uuid(created.get("id"), "created folder ID"),
        "name": created.get("displayName", folder_value),
        "location": created.get("displayName", folder_value),
    }


def _check_name_conflicts(workspace_id, fabric_headers):
    items = _list_pages(
        f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items",
        fabric_headers,
        f"Listing items in workspace {workspace_id}",
        "Workspace.ReadWrite.All and access to the target workspace",
    )
    expected_names = {
        PurePosixPath(asset["file_name"]).stem.casefold()
        for asset in PBIX_ASSETS
    }
    conflicts = []
    for expected_name in expected_names:
        for item_type in ("Report", "SemanticModel"):
            matches = [
                item
                for item in items
                if str(item.get("type", "")).casefold() == item_type.casefold()
                and str(item.get("displayName", "")).casefold() == expected_name
            ]
            if len(matches) > 1:
                conflicts.append(
                    {
                        "name": expected_name,
                        "type": item_type,
                        "ids": [item.get("id") for item in matches],
                    }
                )
    if conflicts:
        raise RuntimeError(
            "CreateOrOverwrite cannot be used unambiguously because duplicate "
            "same-name report or semantic model items already exist: "
            f"{json.dumps(conflicts)}"
        )


def _download_asset(asset, repository, repo_ref):
    asset_path = f"assets/pbix/{asset['file_name']}"
    url = (
        f"https://raw.githubusercontent.com/{repository}/"
        f"{quote(repo_ref, safe='')}/{quote(asset_path, safe='/')}"
    )
    response = _get_with_retry(
        url,
        headers={"User-Agent": "fda-l400-instructor-importer"},
        timeout=180,
        operation=f"Downloading {asset['file_name']}",
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"Downloading {asset['file_name']} from {url} failed. "
            f"{_error_text(response)}"
        )
    content = response.content
    if content.startswith(b"version https://git-lfs.github.com/spec/v1"):
        raise RuntimeError(
            f"{asset_path} resolved to a Git LFS pointer, not PBIX content."
        )
    actual_hash = hashlib.sha256(content).hexdigest().upper()
    if actual_hash != asset["sha256"]:
        raise RuntimeError(
            f"SHA-256 mismatch for {asset['file_name']}: expected "
            f"{asset['sha256']}, received {actual_hash}. Source: {url}"
        )
    return content, url


def _import_asset(
    workspace_id,
    asset,
    content,
    power_bi_headers,
    import_timeout_minutes,
    poll_interval_seconds,
):
    file_name = asset["file_name"]
    import_url = (
        "https://api.powerbi.com/v1.0/myorg/groups/"
        f"{workspace_id}/imports?datasetDisplayName={quote(file_name)}"
        "&nameConflict=CreateOrOverwrite"
    )
    try:
        response = requests.post(
            import_url,
            headers=power_bi_headers,
            files={
                "file": (
                    file_name,
                    io.BytesIO(content),
                    "application/octet-stream",
                )
            },
            timeout=600,
        )
    except requests.Timeout as exc:
        raise TimeoutError(
            f"PBIX upload timed out for {file_name}. The server may still have "
            "accepted the import; inspect the target workspace before retrying."
        ) from exc
    except requests.RequestException as exc:
        raise RuntimeError(f"PBIX upload failed for {file_name}: {exc}") from exc

    if response.status_code not in (200, 201, 202):
        _raise_api_error(
            response,
            f"Uploading {file_name} with CreateOrOverwrite",
            "Dataset.ReadWrite.All and Contributor or higher",
        )
    try:
        import_id = _as_uuid(response.json().get("id"), "Power BI import ID")
    except (AttributeError, TypeError, ValueError) as exc:
        raise RuntimeError(
            f"Upload for {file_name} did not return a valid import ID. "
            f"{_error_text(response)}"
        ) from exc

    status_url = (
        "https://api.powerbi.com/v1.0/myorg/groups/"
        f"{workspace_id}/imports/{import_id}"
    )
    deadline = time.monotonic() + import_timeout_minutes * 60
    last_state = "Unknown"
    while time.monotonic() < deadline:
        status_response = _get_with_retry(
            status_url,
            headers=power_bi_headers,
            operation=f"Polling import {import_id} for {file_name}",
        )
        if status_response.status_code != 200:
            _raise_api_error(
                status_response,
                f"Polling import {import_id} for {file_name}",
                "Dataset.ReadWrite.All and access to the target workspace",
            )
        details = status_response.json()
        last_state = details.get("importState", "Unknown")
        if last_state == "Succeeded":
            artifacts = []
            for item_type, entries in (
                ("SemanticModel", details.get("datasets", [])),
                ("Report", details.get("reports", [])),
            ):
                if not entries:
                    raise RuntimeError(
                        f"Import {import_id} succeeded for {file_name}, but no "
                        f"{item_type} was returned. Details: {json.dumps(details)}"
                    )
                for entry in entries:
                    artifacts.append(
                        {
                            "id": _as_uuid(
                                entry.get("id"),
                                f"{item_type} ID from import {import_id}",
                            ),
                            "name": entry.get("name", ""),
                            "type": item_type,
                            "sourceFile": file_name,
                            "importId": import_id,
                        }
                    )
            return {
                "sourceFile": file_name,
                "importId": import_id,
                "status": last_state,
                "artifacts": artifacts,
            }
        if last_state == "Failed":
            raise RuntimeError(
                f"PBIX import failed for {file_name} (import {import_id}): "
                f"{json.dumps(details)}"
            )
        time.sleep(poll_interval_seconds)

    raise TimeoutError(
        f"PBIX import timed out for {file_name} after {import_timeout_minutes} "
        f"minutes (import {import_id}, last state {last_state!r})."
    )


def _get_item(workspace_id, item_id, fabric_headers):
    response = _get_with_retry(
        f"https://api.fabric.microsoft.com/v1/workspaces/"
        f"{workspace_id}/items/{item_id}",
        headers=fabric_headers,
        operation=f"Reading imported item {item_id}",
    )
    if response.status_code != 200:
        _raise_api_error(
            response,
            f"Reading imported item {item_id}",
            "Workspace.ReadWrite.All and access to the target workspace",
        )
    return response.json()


def _place_and_verify(workspace_id, folder_info, artifacts, fabric_headers):
    artifacts_by_id = {artifact["id"]: artifact for artifact in artifacts}
    if len(artifacts_by_id) != len(artifacts):
        raise RuntimeError(
            "Import responses returned duplicate artifact IDs; refusing an "
            "ambiguous folder move."
        )
    if len(artifacts_by_id) > 50:
        raise RuntimeError("Fabric bulkMove supports at most 50 item IDs.")

    expected_folder_id = folder_info["id"]
    before = {
        item_id: _get_item(workspace_id, item_id, fabric_headers)
        for item_id in artifacts_by_id
    }
    placement_differs = any(
        (str(item.get("folderId")).lower() if item.get("folderId") else None)
        != (expected_folder_id.lower() if expected_folder_id else None)
        for item in before.values()
    )
    if placement_differs:
        payload = {"items": list(artifacts_by_id)}
        if expected_folder_id:
            payload["targetFolderId"] = expected_folder_id
        response = requests.post(
            f"https://api.fabric.microsoft.com/v1/workspaces/"
            f"{workspace_id}/items/bulkMove",
            headers=fabric_headers,
            json=payload,
            timeout=60,
        )
        if response.status_code != 200:
            _raise_api_error(
                response,
                "Moving all returned reports and semantic models together",
                "Contributor or higher and Workspace.ReadWrite.All",
            )

    confirmed = []
    placement_errors = []
    for item_id, artifact in artifacts_by_id.items():
        item = _get_item(workspace_id, item_id, fabric_headers)
        actual_folder_id = item.get("folderId") or None
        if (
            actual_folder_id.casefold() if actual_folder_id else None
        ) != (
            expected_folder_id.casefold() if expected_folder_id else None
        ):
            placement_errors.append(
                {
                    "id": item_id,
                    "name": item.get("displayName") or artifact["name"],
                    "expectedFolderId": expected_folder_id,
                    "actualFolderId": actual_folder_id,
                }
            )
        confirmed.append(
            {
                **artifact,
                "name": item.get("displayName") or artifact["name"],
                "type": item.get("type") or artifact["type"],
                "folderId": actual_folder_id,
                "folderName": folder_info["name"],
            }
        )
    if placement_errors:
        raise RuntimeError(
            "Import succeeded, but final folder placement verification failed: "
            f"{json.dumps(placement_errors)}"
        )
    return confirmed


def _validate_models(
    workspace_id,
    artifacts,
    attempts,
    retry_seconds,
):
    import sempy.fabric as fabric

    models = [
        artifact
        for artifact in artifacts
        if artifact["type"].casefold() == "semanticmodel"
    ]
    if len(models) != len(PBIX_ASSETS):
        raise RuntimeError(
            f"Expected {len(PBIX_ASSETS)} returned semantic models for DAX "
            f"validation; received {len(models)}."
        )

    validation = {}
    for model in models:
        last_error = None
        for attempt in range(1, attempts + 1):
            try:
                result = fabric.evaluate_dax(
                    dataset=model["id"],
                    dax_string=DAX_QUERY,
                    workspace=workspace_id,
                )
                row_count = len(result.index)
                if row_count != 2:
                    raise RuntimeError(
                        f"DAX validation returned {row_count} rows; expected 2."
                    )
                validation[model["name"]] = {
                    "semanticModelId": model["id"],
                    "status": "succeeded",
                    "rowCount": row_count,
                    "attempt": attempt,
                }
                break
            except Exception as exc:
                last_error = exc
                if attempt < attempts:
                    time.sleep(retry_seconds)
        else:
            raise RuntimeError(
                f"DAX validation failed for semantic model {model['name']!r} "
                f"({model['id']}) after {attempts} attempts using the required "
                f"query {DAX_QUERY!r}: {type(last_error).__name__}: {last_error}"
            ) from last_error
    return validation

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## Callable import function
#
# The default call targets the `data-agent-l400` folder and creates it at
# workspace root if it is missing. A folder name is resolved across the entire
# workspace and must be unique; a GUID selects an exact folder. Pass
# `folder=None` explicitly to target workspace root. Set
# `create_folder_if_missing=False` when a missing named folder must be an error.

# CELL ********************

def import_workshop_assets(
    workspace,
    folder=DEFAULT_DESTINATION_FOLDER,
    validate_models: bool = False,
    create_folder_if_missing: bool = True,
    repo_ref: str = DEFAULT_REPO_REF,
    repository: str = DEFAULT_REPOSITORY,
    import_timeout_minutes: int = DEFAULT_IMPORT_TIMEOUT_MINUTES,
    poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
    validation_attempts: int = DEFAULT_VALIDATION_ATTEMPTS,
    validation_retry_seconds: int = DEFAULT_VALIDATION_RETRY_SECONDS,
):
    """Import both PBIX assets; the default destination is data-agent-l400."""
    if import_timeout_minutes <= 0:
        raise ValueError("import_timeout_minutes must be greater than zero.")
    if poll_interval_seconds <= 0:
        raise ValueError("poll_interval_seconds must be greater than zero.")
    if validation_attempts <= 0:
        raise ValueError("validation_attempts must be greater than zero.")
    if validation_retry_seconds < 0:
        raise ValueError("validation_retry_seconds cannot be negative.")
    if not repo_ref or not str(repo_ref).strip():
        raise ValueError("repo_ref cannot be empty.")
    if not repository or "/" not in str(repository):
        raise ValueError("repository must use the 'owner/repository' form.")

    power_bi_headers, fabric_headers = _acquire_headers()
    workspace_info = _resolve_workspace(workspace, fabric_headers)
    workspace_id = workspace_info["id"]
    folder_info = _resolve_folder(
        workspace_id,
        folder,
        create_folder_if_missing,
        fabric_headers,
    )
    _check_name_conflicts(workspace_id, fabric_headers)

    import_results = []
    source_assets = []
    for asset in PBIX_ASSETS:
        content, source_url = _download_asset(asset, repository, str(repo_ref))
        source_assets.append(
            {
                "fileName": asset["file_name"],
                "url": source_url,
                "sha256": asset["sha256"],
                "bytes": len(content),
            }
        )
        import_results.append(
            _import_asset(
                workspace_id,
                asset,
                content,
                power_bi_headers,
                import_timeout_minutes,
                poll_interval_seconds,
            )
        )

    if len(import_results) != len(PBIX_ASSETS):
        raise RuntimeError(
            f"Only {len(import_results)} of {len(PBIX_ASSETS)} imports succeeded."
        )
    artifacts = [
        artifact
        for import_result in import_results
        for artifact in import_result["artifacts"]
    ]
    confirmed_items = _place_and_verify(
        workspace_id,
        folder_info,
        artifacts,
        fabric_headers,
    )

    validation = {
        "requested": bool(validate_models),
        "status": "not_requested",
        "query": DAX_QUERY,
        "models": {},
    }
    if validate_models:
        validation["models"] = _validate_models(
            workspace_id,
            confirmed_items,
            validation_attempts,
            validation_retry_seconds,
        )
        validation["status"] = "succeeded"

    result = {
        "success": True,
        "workspace": workspace_info,
        "folder": folder_info,
        "source": {
            "repository": repository,
            "repoRef": str(repo_ref),
            "assets": source_assets,
        },
        "imports": import_results,
        "importedItems": confirmed_items,
        "validation": validation,
    }
    print(
        f"SUCCESS: imported {len(import_results)} PBIX files and verified "
        f"{len(confirmed_items)} returned items in "
        f"{folder_info['location']} for workspace "
        f"{workspace_info['name']} ({workspace_id}). "
        f"Model validation: {validation['status']}."
    )
    return result

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## Disabled multi-workspace example
#
# Edit the targets and change `if False` only when an instructor is ready to
# perform the imports. Each call returns a structured result dictionary.

# CELL ********************

if False:
    targets = [
        "Workshop Workspace A",
        "11111111-2222-3333-4444-555555555555",
    ]
    results = []
    for target_workspace in targets:
        results.append(
            import_workshop_assets(
                workspace=target_workspace,
                validate_models=False,
            )
        )
    display(results)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }
