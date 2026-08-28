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

# # Refresh semantic models
#
# **Optional maintenance; not required for the lab.**
#
# `SetupDataAgentJumpstart` imports populated PBIX files whose cached data is
# sufficient for the workshop labs. Run this notebook only for a future data
# update or when you need to bind, repair, or rebind the anonymous public Web
# connection before refreshing `ManufacturingOps` and
# `ManufacturingOpsAIReady`.
#
# This notebook does not create or configure a Fabric Data Agent.

# MARKDOWN ********************

# ## Step 1 - Review parameters

# CELL ********************

# PARAMETERS
CONFIGURE_ANONYMOUS_WEB_CONNECTIONS = True
REFRESH_SEMANTIC_MODELS = True

SOURCE_REPOSITORY = "microsoft/fabric-data-agent-workshop"
SEMANTIC_MODELS = ["ManufacturingOps", "ManufacturingOpsAIReady"]
EXPECTED_WEB_SOURCE_PREFIX = (
    f"https://raw.githubusercontent.com/{SOURCE_REPOSITORY}/"
)
EXPECTED_WEB_SOURCE_SUFFIX = "/data/mfg-ops-data"

print("Expected source repository:", SOURCE_REPOSITORY)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## Step 2 - Configure the public GitHub Web connection
#
# Run this cell once after installation. No GitHub credential or token is required.

# CELL ********************

import hashlib
import time

import notebookutils
import requests
import sempy.fabric as fabric


workspace_id = str(fabric.get_notebook_workspace_id())
access_token = notebookutils.credentials.getToken("pbi")


def list_fabric_values(url):
    headers = {"Authorization": f"Bearer {access_token}"}
    values = []
    next_url = url
    while next_url:
        response = requests.get(next_url, headers=headers, timeout=60)
        response.raise_for_status()
        payload = response.json()
        values.extend(payload.get("value", []))
        next_url = payload.get("continuationUri")
    return values


def get_web_creation_metadata():
    types = list_fabric_values(
        "https://api.fabric.microsoft.com/v1/connections/"
        "supportedConnectionTypes?showAllCreationMethods=true"
    )
    web_type = next(
        (item for item in types if item.get("type", "").lower() == "web"),
        None,
    )
    if web_type is None:
        raise RuntimeError("The tenant did not return Web as a supported connection type.")
    if "Anonymous" not in web_type.get("supportedCredentialTypes", []):
        raise RuntimeError("The tenant does not support Anonymous Web connections.")
    if not web_type.get("supportsSkipTestConnection"):
        raise RuntimeError("The tenant does not support skipTestConnection for Web.")

    for method in web_type.get("creationMethods", []):
        parameters = method.get("parameters", [])
        names = {parameter.get("name", "").lower() for parameter in parameters}
        required = {
            parameter.get("name", "").lower()
            for parameter in parameters
            if parameter.get("required")
        }
        if "url" in names and required.issubset({"url"}):
            return method
    raise RuntimeError("No supported Web creation method accepts only a URL.")


def find_anonymous_web_connection(connection_details):
    for connection in list_fabric_values(
        "https://api.fabric.microsoft.com/v1/connections"
    ):
        if (
            connection.get("connectivityType") == "ShareableCloud"
            and connection.get("connectionDetails") == connection_details
            and connection.get("credentialDetails", {}).get("credentialType")
            == "Anonymous"
        ):
            return connection
    return None


def create_anonymous_web_connection(connection_details):
    creation_method = get_web_creation_metadata()
    path = connection_details["path"]
    parameters = []
    for parameter in creation_method.get("parameters", []):
        if parameter.get("name", "").lower() == "url":
            parameters.append(
                {
                    "dataType": parameter["dataType"],
                    "name": parameter["name"],
                    "value": path,
                }
            )
        elif parameter.get("required"):
            raise RuntimeError(
                f"Unsupported required Web parameter: {parameter['name']}"
            )

    suffix = hashlib.sha256(path.encode("utf-8")).hexdigest()[:8]
    response = requests.post(
        "https://api.fabric.microsoft.com/v1/connections",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={
            "connectivityType": "ShareableCloud",
            "displayName": f"data_agents_GitHub_Web_{suffix}",
            "connectionDetails": {
                "type": "Web",
                "creationMethod": creation_method["name"],
                "parameters": parameters,
            },
            "privacyLevel": "Public",
            "credentialDetails": {
                "singleSignOnType": "None",
                "connectionEncryption": "NotEncrypted",
                "skipTestConnection": True,
                "credentials": {"credentialType": "Anonymous"},
            },
        },
        timeout=60,
    )
    if response.status_code != 201:
        raise RuntimeError(
            "Anonymous Web connection creation failed: "
            f"HTTP {response.status_code} {response.text}"
        )
    return response.json()


def find_model_id(model_name):
    items = fabric.list_items(workspace=workspace_id)
    matches = items[
        (items["Type"] == "SemanticModel")
        & (items["Display Name"] == model_name)
    ]
    if matches.empty:
        raise RuntimeError(
            f"Semantic model {model_name!r} was not found in this workspace."
        )
    return str(matches.iloc[0]["Id"])


def bind_anonymous_web_connection(model_name):
    model_id = find_model_id(model_name)
    connections_url = (
        "https://api.fabric.microsoft.com/v1/workspaces/"
        f"{workspace_id}/items/{model_id}/connections"
    )
    references = []
    for _ in range(30):
        references = [
            reference
            for reference in list_fabric_values(connections_url)
            if reference.get("connectionDetails", {}).get("type", "").lower()
            == "web"
            and reference.get("connectionDetails", {})
            .get("path", "")
            .startswith(EXPECTED_WEB_SOURCE_PREFIX)
            and reference.get("connectionDetails", {})
            .get("path", "")
            .rstrip("/")
            .endswith(EXPECTED_WEB_SOURCE_SUFFIX)
        ]
        if references:
            break
        time.sleep(5)
    if not references:
        raise RuntimeError(
            "No Web source under "
            f"{EXPECTED_WEB_SOURCE_PREFIX!r} ending in "
            f"{EXPECTED_WEB_SOURCE_SUFFIX!r} was found for {model_name}."
        )

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    for reference in references:
        details = reference["connectionDetails"]
        connection = find_anonymous_web_connection(details)
        if connection is None:
            connection = create_anonymous_web_connection(details)
            print("Created connection:", connection["displayName"])
        else:
            print("Using connection:", connection["displayName"])

        response = requests.post(
            "https://api.fabric.microsoft.com/v1/workspaces/"
            f"{workspace_id}/semanticModels/{model_id}/bindConnection",
            headers=headers,
            json={
                "connectionBinding": {
                    "id": connection["id"],
                    "connectivityType": "ShareableCloud",
                    "connectionDetails": details,
                }
            },
            timeout=60,
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"Binding failed for {model_name}: "
                f"HTTP {response.status_code} {response.text}"
            )
    print(f"Bound Anonymous Web connection: {model_name}")


if CONFIGURE_ANONYMOUS_WEB_CONNECTIONS:
    for semantic_model in SEMANTIC_MODELS:
        bind_anonymous_web_connection(semantic_model)
else:
    print("Anonymous Web connection configuration skipped.")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## Step 3 - Refresh the semantic models

# CELL ********************

def refresh_semantic_model(model_name):
    print(f"Starting full refresh: {model_name}")
    request_id = fabric.refresh_dataset(
        dataset=model_name,
        workspace=workspace_id,
        refresh_type="full",
    )
    for _ in range(160):
        details = fabric.get_refresh_execution_details(
            dataset=model_name,
            refresh_request_id=request_id,
            workspace=workspace_id,
        )
        if details.status == "Completed":
            print(f"Refresh completed: {model_name}")
            return
        if details.status in {"Failed", "Cancelled"}:
            messages = ""
            if details.messages is not None and not details.messages.empty:
                messages = "\n".join(
                    details.messages["Message"].astype(str).tolist()
                )
            raise RuntimeError(
                f"Refresh {details.status.lower()} for {model_name}. {messages}"
            )
        time.sleep(15)
    raise TimeoutError(f"Refresh timed out for {model_name} after 40 minutes.")


if REFRESH_SEMANTIC_MODELS:
    for semantic_model in SEMANTIC_MODELS:
        refresh_semantic_model(semantic_model)
else:
    print("Semantic model refresh skipped.")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## What this notebook changed
#
# The executable cells only create or reuse and bind the anonymous public Web
# connection, then refresh `ManufacturingOps` and `ManufacturingOpsAIReady`.
# They do not create or configure a Fabric Data Agent.
#
# ## Troubleshooting
#
# - **Refresh says credentials are missing:** rerun the connection cell above.
# - **Connection creation returns 404:** confirm the configured source URL is
#   reachable and keep `skipTestConnection=True`.
# - **A notebook cannot find an item:** confirm all recommended Jumpstart
#   notebooks were installed into the same workspace and retain their item names.
