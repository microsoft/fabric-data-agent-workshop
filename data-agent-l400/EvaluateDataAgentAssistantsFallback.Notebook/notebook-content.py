# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "jupyter",
# META     "jupyter_kernel_name": "python3.12"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse_name": "",
# META       "default_lakehouse_workspace_id": ""
# META     }
# META   }
# META }

# MARKDOWN ********************

# # Data Agent Evaluation - L400 - Assistants API Temporary Fix
#
# **Author:** Sandeep Pawar  
# **Date:** 2026-08-08  
# **Version:** 1.1-temporary
#
# `[Fixed eval set] -> [Live DAX ground truth or expected behavior] -> [Isolated Assistants calls] -> [Registered champion judge] -> [Grade responses] -> [Human review] -> [Log and compare in MLflow]`
#
# Use this notebook until the SDK evaluation attachment parser is fixed. It bypasses the
# high-level `evaluate_data_agent` helper but preserves the same evaluation questions, live
# ground truth, registered judge, scoring rules, result artifacts, and MLflow contract.
#
# The temporary runner creates a fresh thread per question, verifies the user message, filters
# the answer to the current run, safely handles non-tabular JSON attachments, retries transient
# Fabric token-service failures, and deletes threads after diagnostics are captured.

# MARKDOWN ********************

# ## Setup
#
# MLflow is the system of record for results. Attach a default lakehouse so evaluation artifacts
# have persistent storage. The SDK is pinned to `0.1.28a0`; downgrading does not fix the
# Assistants evaluation parser because the same `columns` assumption exists in `0.1.27a0`.

# CELL ********************

%pip install -q "synapseml-mlflow[online-notebook]>=2.0.3" "mlflow-skinny==3.1.0" "opentelemetry-api<=1.40.0" openpyxl "fabric-data-agent-sdk==0.1.28a0"

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

import json
import time
from io import BytesIO
from pathlib import Path

import requests
import warnings
import hashlib
from datetime import datetime, timezone

import pandas as pd
import matplotlib.pyplot as plt
import mlflow
import sempy.fabric as fabric
from fabric.dataagent.client import FabricDataAgentManagement, FabricOpenAI
from synapse.ml.fabric.credentials import get_openai_httpx_sync_client
import openai

# The SDK still calls a few of its own deprecated APIs internally -- hide that noise.
warnings.filterwarnings("ignore", category=FutureWarning)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## Configuration
#
# `GT_MODEL` is the trusted model we treat as the answer key. `AGENT` is the one Data
# Agent this run evaluates. `STAGE` is a free-form label for the run.
#
# **Experiment vs run:** use **one experiment per agent** and add **one run each time**
# you evaluate. For daily drift monitoring, keep the same `EXPERIMENT` and tag runs
# `stage=monitor` - the over-time view reads every run back. For an optimization loop,
# point `EXPERIMENT` at a separate name (for example `...-optimize`) so experimental
# variants do not clutter the monitoring trend, then promote the winning config back as
# a `baseline` run in the main experiment. The logged `config_hash` tells you whether a
# score moved because of a config change (different hash) or data drift (same hash).

# CELL ********************

EVAL_XLSX_URL = "https://raw.githubusercontent.com/pawarbi/fda-l400/v0.1.1-test/eval/eval_set_L400.xlsx"
EVAL_LH_NAME = "mfgops_da_eval"
EVAL_FILE_NAME = "eval_set_L400.xlsx"

# Use the workspace where this notebook is running
CURRENT_WORKSPACE_ID = fabric.get_notebook_workspace_id()
GT_WORKSPACE = CURRENT_WORKSPACE_ID
GT_MODEL = "ManufacturingOpsAIReady"

# Set to "Yes" only when this run must refresh the semantic model first.
REFRESH = "No"
REFRESH_POLL_SECONDS = 15
REFRESH_TIMEOUT_SECONDS = 1800

# The agent under evaluation. Change this (and STAGE) to evaluate a different agent.
AGENT = {
    "label":     "MfgOps Data Agent - AI Ready SAP",
    "name":      "MfgOps_DA_AIReady_SAP",
    "workspace": CURRENT_WORKSPACE_ID,
    "table":     "eval_results_l400_assistants",
    "data_agent_stage": "sandbox",
}
STAGE = "after"   # free-form RUN label: baseline / monitor / before / after / optimize ...

EXPERIMENT  = "mfg-ops-data-agent-eval"
REPEATS = 1             # independent evaluation attempts per question
AGENT_MODEL = "gpt-5.1"   # same Assistants model used by SDK 0.1.28a0
REFERENCE_MODEL = "gpt-5.1"
TEST_MODE = True
TEST_CASE_IDS = [
    "highest_scrap_rate_line",
    "avg_day_production_yield_this_year",
    "highest_sales_product_this_year",
]
RUN_PREFLIGHT = True       # first verify one factual and one refusal question
DELETE_THREADS = True      # delete only after answer and run steps are captured
RETRY_ATTEMPTS = 4

RUN_TS = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
mlflow.set_experiment(EXPERIMENT)
print(f"Experiment: {EXPERIMENT} | stage: {STAGE} | agent: {AGENT['label']} | {RUN_TS} UTC")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## Step 1 - Load the eval set
#
# The workbook has two sheets: `eval_set` (the questions) and `judge_calibration`
# (labelled answers used to validate the judge). Each eval row carries the `question`,
# its `goal`, an `answer_type` (`numeric`, `list`, or `behavioral`), the `dax` used to
# derive ground truth, and an `expected_behavior` for behavioral questions.

# MARKDOWN ********************

# ## Prepare the evaluation workbook
#
# Create or reuse the schema-enabled evaluation Lakehouse, download the versioned workbook from
# GitHub, and persist it under `Files/eval_set`. Pandas reads the same downloaded binary content,
# so this works in a Python 3.12 notebook without a Spark session.

# CELL ********************

lakehouses = notebookutils.lakehouse.list()
lakehouse_names = {
    getattr(item, "displayName", None) or getattr(item, "name", None)
    for item in lakehouses
}

if EVAL_LH_NAME not in lakehouse_names:
    notebookutils.lakehouse.create(
        name=EVAL_LH_NAME,
        definition={"enableSchemas": True},
    )

evaluation_lakehouse = notebookutils.lakehouse.getWithProperties(EVAL_LH_NAME)
files_path = evaluation_lakehouse.properties["abfsPath"] + "/Files"
eval_set_path = files_path + "/eval_set"
notebookutils.fs.mkdirs(eval_set_path)

EVAL_FILE_PATH = eval_set_path + "/" + EVAL_FILE_NAME
local_download_path = "/tmp/" + EVAL_FILE_NAME

response = requests.get(EVAL_XLSX_URL, timeout=60)
response.raise_for_status()
Path(local_download_path).write_bytes(response.content)

if notebookutils.fs.exists(EVAL_FILE_PATH):
    notebookutils.fs.rm(EVAL_FILE_PATH)

copied = notebookutils.fs.cp(
    "file:" + local_download_path,
    EVAL_FILE_PATH,
)
assert copied, f"Could not copy the evaluation workbook to {EVAL_FILE_PATH}"

eval_workbook_bytes = response.content
print(f"Evaluation workbook: {EVAL_FILE_PATH}")
print(f"Persisted and loaded {len(eval_workbook_bytes):,} bytes.")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

cases = pd.read_excel(
    BytesIO(eval_workbook_bytes),
    sheet_name="eval_set",
).fillna("")

required = {
    "id", "goal", "question", "answer_type", "dax", "expected_behavior",
    "expected_measure", "expected_period", "policy_area",
}
missing = required - set(cases.columns)
assert not missing, f"Evaluation set is missing columns: {sorted(missing)}"
assert cases["id"].is_unique, "Evaluation IDs must be unique."
assert cases["question"].is_unique, "Evaluation questions must be unique."

if TEST_MODE:
    missing_test_ids = set(TEST_CASE_IDS) - set(cases["id"])
    assert not missing_test_ids, (
        f"Test cases are missing from the workbook: {sorted(missing_test_ids)}"
    )
    cases = cases.set_index("id").loc[TEST_CASE_IDS].reset_index()
    print(f"TEST_MODE: running {len(cases)} cases: {TEST_CASE_IDS}")

cases[[
    "id", "answer_type", "question", "expected_measure",
    "expected_period", "policy_area",
]]

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## Step 2 - Ground truth from the model
#
# Optionally refresh the trusted semantic model, then execute each factual question's DAX with
# `fabric.evaluate_dax`. Raw canonical JSON is retained as evidence. GPT-5.1 later converts the
# trusted result into a concise reference summary using the applicable response instructions.
#
# Behavioral questions use their authored `expected_behavior` and do not use DAX reference
# generation.

# CELL ********************

refresh_option = str(REFRESH).strip().lower()
assert refresh_option in {"yes", "no"}, 'REFRESH must be "Yes" or "No".'

if refresh_option == "yes":
    print(f"Starting refresh: {GT_MODEL}")
    refresh_request_id = fabric.refresh_dataset(
        GT_MODEL,
        workspace=GT_WORKSPACE,
    )
    print("Refresh request ID:", refresh_request_id)

    terminal_statuses = {
        "completed",
        "failed",
        "cancelled",
        "timedout",
        "disabled",
    }
    successful_statuses = {"completed"}
    started = time.monotonic()
    previous_status = None

    while True:
        details = fabric.get_refresh_execution_details(
            GT_MODEL,
            refresh_request_id,
            workspace=GT_WORKSPACE,
        )
        status = getattr(details, "status", None)
        if status is None and isinstance(details, dict):
            status = details.get("status")
        status = str(status or "unknown").lower()

        if status != previous_status:
            print("Refresh status:", status)
            previous_status = status

        if status in terminal_statuses:
            if status not in successful_statuses:
                raise RuntimeError(
                    f"Semantic model refresh ended with status: {status}"
                )
            print("Semantic model refresh completed.")
            break

        if time.monotonic() - started > REFRESH_TIMEOUT_SECONDS:
            raise TimeoutError(
                f"Semantic model refresh exceeded {REFRESH_TIMEOUT_SECONDS} seconds."
            )

        time.sleep(REFRESH_POLL_SECONDS)
else:
    print("Semantic model refresh skipped because REFRESH is No.")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

def canonical_gt(df):
    # Pandas emits nulls and ISO timestamps while preserving numeric precision.
    payload = json.loads(
        df.to_json(
            orient="split",
            date_format="iso",
            double_precision=15,
            default_handler=str,
        )
    )
    payload.pop("index", None)
    return json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
    )


def display_gt(df):
    if df.empty:
        return "(no rows)"
    return df.to_markdown(index=False)


def ground_truth(row):
    if row["answer_type"] == "behavioral":
        expected = str(row["expected_behavior"])
        return "", expected, expected, 1
    df = fabric.evaluate_dax(
        GT_MODEL,
        row["dax"],
        workspace=GT_WORKSPACE,
    )
    return canonical_gt(df), display_gt(df), "", len(df)


ground_truth_results = []
for _, row in cases.iterrows():
    print(f"Computing ground truth: {row['id']}")
    ground_truth_results.append(ground_truth(row))

(
    cases["ground_truth_json"],
    cases["expected_display"],
    cases["expected_answer"],
    cases["gt_rows"],
) = zip(*ground_truth_results)

empty = cases[
    (cases.answer_type != "behavioral")
    & (cases.gt_rows == 0)
]
assert empty.empty, (
    f"Factual questions returned no ground truth: {list(empty.id)}"
)

cases[[
    "id",
    "answer_type",
    "gt_rows",
    "ground_truth_json",
    "expected_display",
]]

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## Step 3 - Load the calibrated champion judge
#
# The evaluation notebook does not calibrate or tune the judge. It retrieves the latest MLflow
# run tagged `judge_status=champion` and uses the exact registered rubric, model, API version,
# and seed. The evaluation stops if no champion exists.
#
# This separation prevents evaluation results from changing because of an inline or unvalidated
# judge prompt.

# CELL ********************

mlflow.openai.autolog()
JUDGE_REGISTRY_EXPERIMENT = "mfg-ops-judge-registry"


def load_champion_judge(experiment_name):
    experiment = mlflow.get_experiment_by_name(experiment_name)
    assert experiment is not None, f"Judge registry not found: {experiment_name}"

    runs = mlflow.search_runs(
        experiment_ids=[experiment.experiment_id],
        filter_string=(
            "tags.artifact_type = 'judge' "
            "and tags.judge_status = 'champion'"
        ),
        order_by=["start_time DESC"],
        max_results=1,
    )
    assert not runs.empty, f"No champion judge found in {experiment_name}"

    run_id = runs.iloc[0]["run_id"]
    path = mlflow.artifacts.download_artifacts(
        artifact_uri=f"runs:/{run_id}/judge.json"
    )
    with open(path, encoding="utf-8") as artifact:
        specification = json.load(artifact)
    specification["source_run_id"] = run_id
    return specification


judge_spec = load_champion_judge(JUDGE_REGISTRY_EXPERIMENT)
RUBRIC = judge_spec["rubric"]
JUDGE_MODEL = judge_spec["model"]
JUDGE_SEED = judge_spec["seed"]
JUDGE_API_VERSION = judge_spec["api_version"]
RUBRIC_HASH = judge_spec["rubric_hash"]
JUDGE_RUN_ID = judge_spec["source_run_id"]

holdout_metrics = judge_spec.get("holdout_metrics", {})
print(
    "Judge:",
    f"champion {RUBRIC_HASH}",
    f"run {JUDGE_RUN_ID}",
    f"holdout raw={holdout_metrics.get('raw')}",
    f"kappa={holdout_metrics.get('kappa')}",
    f"recall_fail={holdout_metrics.get('recall_fail')}",
)

judge_client = openai.AzureOpenAI(
    api_version=JUDGE_API_VERSION,
    http_client=get_openai_httpx_sync_client(),
)
JUDGE_FINGERPRINTS = set()


def token_service_retry(operation, label, attempts=4):
    retryable_text = (
        "connection refused",
        "max retries exceeded",
        "tokenservice",
        "temporarily unavailable",
        "timed out",
        "timeout",
    )
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except Exception as error:
            retryable = isinstance(
                error,
                (
                    openai.APIConnectionError,
                    openai.APITimeoutError,
                    requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout,
                ),
            ) or any(token in str(error).lower() for token in retryable_text)
            if not retryable or attempt == attempts:
                raise
            delay = min(30, 2 ** attempt)
            print(
                f"{label}: Fabric token service unavailable; "
                f"retrying in {delay}s ({attempt}/{attempts})"
            )
            time.sleep(delay)


def judge(question, expected, actual):
    request = {
        "model": JUDGE_MODEL,
        "seed": JUDGE_SEED,
        "messages": [
            {"role": "system", "content": RUBRIC},
            {
                "role": "user",
                "content": (
                    f"Question:\n{question}\n\n"
                    f"Expected answer or behavior:\n{expected}\n\n"
                    f"Candidate answer:\n{actual}"
                ),
            },
        ],
        "response_format": {"type": "json_object"},
    }
    if not JUDGE_MODEL.lower().startswith("gpt-5"):
        request["temperature"] = 0

    response = token_service_retry(
        lambda: judge_client.chat.completions.create(**request),
        label="judge request",
    )
    if response.system_fingerprint:
        JUDGE_FINGERPRINTS.add(response.system_fingerprint)
    result = json.loads(response.choices[0].message.content)
    verdict = str(result["verdict"]).strip().upper()
    assert verdict in {"PASS", "FAIL"}, f"Unexpected judge verdict: {verdict}"
    return verdict == "PASS", result.get("reason", "")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# The evaluation requires a registered champion. It does not recalibrate the judge or use an
# inline fallback. This ensures every result is tied to the exact rubric and holdout evidence
# that approved the judge.

# MARKDOWN ********************

# ## Step 4 - Snapshot the agent configuration
#
# Before running, capture the agent's configuration so the run is self-describing: the
# agent AI instructions plus, for every datasource, its instructions, description,
# selected tables, and few-shot examples. We hash it into a short `config_hash`. Two
# runs with the same hash used identical config, so any score change is data drift; a
# different hash means a config change you can attribute a lift (or regression) to.

# CELL ********************

mgmt = FabricDataAgentManagement(AGENT["name"], AGENT["workspace"])

# get_configuration()/get_datasources() are present in every SDK version, so we
# read the config the same way everywhere. getattr handles the instructions
# attribute being named either "instructions" or "ai_instructions".
cfg = mgmt.get_configuration()
ai_instructions = str(getattr(cfg, "instructions", None) or getattr(cfg, "ai_instructions", None) or "")

agent_config = {"aiInstructions": ai_instructions, "datasources": []}
for d in mgmt.get_datasources():
    fs = d.get_fewshots()
    agent_config["datasources"].append({
        "configuration": d.get_configuration(),
        "fewshots": fs.to_dict("records") if hasattr(fs, "to_dict") else (fs or []),
    })

config_json = json.dumps(agent_config, indent=2, default=str)
config_hash = hashlib.sha256(config_json.encode()).hexdigest()[:12]
n_fewshots = sum(len(d["fewshots"]) for d in agent_config["datasources"])

config_params = {
    "config_hash": config_hash,
    "agent_instructions_len": len(ai_instructions),
    "n_datasources": len(agent_config["datasources"]),
    "n_fewshots": n_fewshots,
}
print(config_params)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## Step 4.1 - Generate grounded reference summaries
#
# For factual cases, GPT-5.1 converts the trusted DAX result into a concise expected answer. It
# receives the Data Agent instructions so presentation requirements such as two decimal places
# are represented. It is prohibited from adding, recalculating, or changing facts.
#
# The raw DAX JSON remains the source-of-truth artifact. Behavioral cases continue using their
# authored expected behavior.

# CELL ********************

REFERENCE_PROMPT = """
Create a concise reference answer from trusted query results.

Rules:
- Use only facts present in TRUSTED DATA.
- Do not infer, calculate, add, omit, or change data values.
- Include every row when the result is grouped or is a list.
- Follow applicable response presentation instructions, including decimal places,
  percentages, units, dates, and the requested period.
- Ignore instructions about tools, query generation, routing, or retrieval.
- Do not mention DAX, JSON, trusted data, or evaluation.
- Return JSON with one string field named reference_answer.
"""


def generate_reference_answer(row):
    if row["answer_type"] == "behavioral":
        return str(row["expected_behavior"]), "authored_behavior"

    context = {
        "question": row["question"],
        "goal": row["goal"],
        "answer_type": row["answer_type"],
        "expected_measure": row["expected_measure"],
        "expected_period": row["expected_period"],
        "applicable_agent_instructions": ai_instructions,
        "trusted_data": json.loads(row["ground_truth_json"]),
    }
    response = token_service_retry(
        lambda: judge_client.chat.completions.create(
            model=REFERENCE_MODEL,
            seed=JUDGE_SEED,
            messages=[
                {"role": "system", "content": REFERENCE_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        context,
                        ensure_ascii=True,
                        separators=(",", ":"),
                    ),
                },
            ],
            response_format={"type": "json_object"},
        ),
        label=f"{row['id']} reference generation",
    )
    result = json.loads(response.choices[0].message.content)
    reference_answer = str(result["reference_answer"]).strip()
    assert reference_answer, f"Empty reference answer for {row['id']}"
    return reference_answer, "gpt_grounded"


reference_results = cases.apply(generate_reference_answer, axis=1).tolist()
cases["expected_answer"] = [result[0] for result in reference_results]
cases["reference_source"] = [result[1] for result in reference_results]

reference_review = cases[[
    "id",
    "question",
    "answer_type",
    "expected_display",
    "expected_answer",
    "reference_source",
]]
display(reference_review)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## Step 5 - Run the agent with isolated Assistants API calls
#
# The SDK helper currently assumes every JSON attachment has `columns` and `rows`. This temporary
# runner does not make that assumption. It reads text plus supported attachments, retaining raw
# JSON when the payload is not tabular.
#
# Before all questions run, a two-question preflight compares the scrap-rate answer with the sales
# refusal answer. The notebook stops before scoring if message isolation is not proven.

# CELL ********************

import time
import uuid

TERMINAL_RUN_STATUSES = {
    "completed",
    "failed",
    "cancelled",
    "expired",
    "incomplete",
}
RETRYABLE_TYPES = (
    openai.APIConnectionError,
    openai.APITimeoutError,
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
)
RETRYABLE_TEXT = (
    "connection refused",
    "max retries exceeded",
    "temporarily unavailable",
    "tokenservice",
    "timed out",
    "timeout",
)
TEXT_FILE_EXTENSIONS = {".txt", ".md", ".log"}
MAX_ATTACHMENT_CHARS = 16000
TEXT_ONLY_SUFFIX = (
    "Return the answer as text only. Do not create or return a chart, graph, "
    "image, or other visual."
)


def is_retryable(error):
    message = str(error).lower()
    return isinstance(error, RETRYABLE_TYPES) or any(
        token in message for token in RETRYABLE_TEXT
    )


def retry_call(operation, label, attempts=RETRY_ATTEMPTS):
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except Exception as error:
            if not is_retryable(error) or attempt == attempts:
                raise
            delay = min(30, 2 ** attempt)
            print(
                f"{label}: transient connection failure; "
                f"retrying in {delay}s ({attempt}/{attempts})"
            )
            time.sleep(delay)


def wait_for_run(client, thread_id, run, timeout_seconds=600, poll_seconds=2):
    started = time.monotonic()
    while str(run.status).lower() not in TERMINAL_RUN_STATUSES:
        if time.monotonic() - started > timeout_seconds:
            raise TimeoutError(f"Timed out waiting for run {run.id}")
        time.sleep(poll_seconds)
        run = retry_call(
            lambda: client.beta.threads.runs.retrieve(
                thread_id=thread_id,
                run_id=run.id,
            ),
            label=f"retrieve run {run.id}",
        )
    return run


def sdk_object_dict(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    return {"value": str(value)}


def response_bytes(response):
    payload = response.read()
    if isinstance(payload, str):
        return payload.encode("utf-8")
    return payload


def tabular_payload(data):
    candidates = [data]
    if isinstance(data, dict):
        candidates.extend(
            data.get(key) for key in ("result", "data", "value") if key in data
        )
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        columns = candidate.get("columns")
        rows = candidate.get("rows")
        if not isinstance(columns, list) or not isinstance(rows, list):
            continue
        names = [
            str(column.get("name", column))
            if isinstance(column, dict)
            else str(column)
            for column in columns
        ]
        if names:
            return pd.DataFrame(rows, columns=names)
    return None


def attachment_text(client, file_id):
    file_info = retry_call(
        lambda: client.files.retrieve(file_id),
        label=f"retrieve file metadata {file_id}",
    )
    filename = str(getattr(file_info, "filename", file_id))
    suffix = Path(filename).suffix.lower()
    content = retry_call(
        lambda: client.files.content(file_id),
        label=f"retrieve file content {file_id}",
    )
    payload = response_bytes(content)

    if suffix == ".json":
        data = json.loads(payload.decode("utf-8"))
        table = tabular_payload(data)
        rendered = (
            table.head(25).to_markdown(index=False)
            if table is not None
            else json.dumps(data, indent=2, default=str)
        )
    elif suffix == ".csv":
        from io import BytesIO

        rendered = pd.read_csv(BytesIO(payload)).head(25).to_markdown(index=False)
    elif suffix in TEXT_FILE_EXTENSIONS:
        rendered = payload.decode("utf-8", errors="replace")
    else:
        rendered = f"[Attachment {filename} is not a supported text format]"

    return f"Attachment: {filename}\n{rendered[:MAX_ATTACHMENT_CHARS]}"


def message_text(client, message):
    parts = []
    attachment_ids = []
    for content in getattr(message, "content", []):
        if getattr(content, "type", None) != "text":
            parts.append(json.dumps(sdk_object_dict(content), default=str))
            continue
        text = getattr(content, "text", None)
        value = getattr(text, "value", None)
        if value:
            parts.append(str(value))
        for annotation in getattr(text, "annotations", []) or []:
            file_path = getattr(annotation, "file_path", None)
            file_id = getattr(file_path, "file_id", None)
            if file_id and file_id not in attachment_ids:
                attachment_ids.append(file_id)

    for file_id in attachment_ids:
        parts.append(attachment_text(client, file_id))
    return "\n\n".join(part for part in parts if part).strip()


def run_one_case(client, assistant_id, case, repeat_number, evaluation_id):
    started = time.perf_counter()
    thread = None
    user_message = None
    run = None
    steps = []
    submitted_prompt = (
        f"{str(case['question']).strip()}\n\n{TEXT_ONLY_SUFFIX}"
    )
    try:
        thread = retry_call(
            lambda: client.beta.threads.create(),
            label=f"{case['id']} create thread",
        )
        user_message = retry_call(
            lambda: client.beta.threads.messages.create(
                thread_id=thread.id,
                role="user",
                content=submitted_prompt,
            ),
            label=f"{case['id']} create user message",
        )
        run = retry_call(
            lambda: client.beta.threads.runs.create(
                thread_id=thread.id,
                assistant_id=assistant_id,
            ),
            label=f"{case['id']} create run",
        )
        run = wait_for_run(client, thread.id, run)
        run_status = str(run.status).lower()
        if run_status != "completed":
            raise RuntimeError(
                f"Assistant run {run.id} ended with {run_status}: "
                f"{getattr(run, 'last_error', None)}"
            )

        messages = retry_call(
            lambda: client.beta.threads.messages.list(
                thread_id=thread.id,
                order="desc",
                limit=100,
            ),
            label=f"{case['id']} retrieve messages",
        )
        retrieved_user = next(
            (message for message in messages.data if message.id == user_message.id),
            None,
        )
        if retrieved_user is None:
            raise RuntimeError(f"User message {user_message.id} was not retrieved")
        retrieved_question = message_text(client, retrieved_user)
        if retrieved_question.strip() != submitted_prompt:
            raise RuntimeError(
                "Thread question mismatch. "
                f"Expected {submitted_prompt!r}, retrieved {retrieved_question!r}"
            )

        current_run_messages = [
            message
            for message in messages.data
            if str(message.role).lower() == "assistant"
            and getattr(message, "run_id", None) == run.id
        ]
        if not current_run_messages:
            raise RuntimeError(
                f"No assistant message was associated with run {run.id}"
            )
        latest_assistant = max(
            current_run_messages,
            key=lambda message: (message.created_at, message.id),
        )
        actual_answer = message_text(client, latest_assistant)
        if not actual_answer:
            raise RuntimeError(
                f"Assistant message {latest_assistant.id} contained no usable answer"
            )

        run_steps = retry_call(
            lambda: client.beta.threads.runs.steps.list(
                thread_id=thread.id,
                run_id=run.id,
                order="asc",
            ),
            label=f"{case['id']} retrieve run steps",
        )
        for step_number, step in enumerate(run_steps.data, start=1):
            steps.append(
                {
                    "eval_id": evaluation_id,
                    "id": case["id"],
                    "question": case["question"],
                    "repeat": repeat_number,
                    "thread_id": thread.id,
                    "run_id": run.id,
                    "assistant_message_id": latest_assistant.id,
                    "step_number": step_number,
                    "type": getattr(step, "type", None),
                    "payload": json.dumps(sdk_object_dict(step), default=str),
                }
            )

        result = {
            "eval_id": evaluation_id,
            "id": case["id"],
            "question": case["question"],
            "submitted_prompt": submitted_prompt,
            "expected_answer": case["expected_answer"],
            "actual_answer": actual_answer,
            "response_status": "completed",
            "thread_id": thread.id,
            "run_id": run.id,
            "user_message_id": user_message.id,
            "assistant_message_id": latest_assistant.id,
            "repeat": repeat_number,
            "duration_seconds": round(time.perf_counter() - started, 3),
        }
        return result, steps
    finally:
        if DELETE_THREADS and thread is not None:
            try:
                retry_call(
                    lambda: client.beta.threads.delete(thread.id),
                    label=f"{case['id']} delete thread",
                )
            except Exception as cleanup_error:
                print(
                    f"{case['id']}: thread cleanup failed after capture: "
                    f"{cleanup_error}"
                )


def safe_run_one_case(client, assistant_id, case, repeat_number, evaluation_id):
    started = time.perf_counter()
    try:
        return run_one_case(
            client,
            assistant_id,
            case,
            repeat_number,
            evaluation_id,
        )
    except Exception as error:
        return (
            {
                "eval_id": evaluation_id,
                "id": case["id"],
                "question": case["question"],
                "submitted_prompt": (
                    f"{str(case['question']).strip()}\n\n{TEXT_ONLY_SUFFIX}"
                ),
                "expected_answer": case["expected_answer"],
                "actual_answer": f"ERROR ({type(error).__name__}): {error}",
                "response_status": "failed",
                "thread_id": None,
                "run_id": None,
                "user_message_id": None,
                "assistant_message_id": None,
                "repeat": repeat_number,
                "duration_seconds": round(time.perf_counter() - started, 3),
            },
            [],
        )


fabric_client = FabricOpenAI(artifact_name=AGENT["name"])
assistant = retry_call(
    lambda: fabric_client.beta.assistants.create(model=AGENT_MODEL),
    label="create assistant",
)
print("Assistant ID:", assistant.id, "| model:", AGENT_MODEL)

if RUN_PREFLIGHT:
    preflight_ids = [
        "highest_scrap_rate_line",
        "highest_sales_product_this_year",
    ]
    preflight_cases = cases[cases["id"].isin(preflight_ids)]
    assert len(preflight_cases) == 2, (
        f"Preflight cases missing. Expected {preflight_ids}"
    )
    preflight_rows = []
    for _, preflight_case in preflight_cases.iterrows():
        result, _ = safe_run_one_case(
            fabric_client,
            assistant.id,
            preflight_case,
            1,
            "preflight-" + str(uuid.uuid4()),
        )
        preflight_rows.append(result)
        print(
            f"Preflight {result['id']}: {result['response_status']} | "
            f"{result['actual_answer'][:120]!r}"
        )
    preflight = pd.DataFrame(preflight_rows)
    assert (preflight["response_status"] == "completed").all(), (
        "Preflight failed. Resolve the displayed infrastructure error before "
        "running the full evaluation."
    )
    assert preflight["actual_answer"].nunique() == 2, (
        "Response-isolation preflight failed: the factual and refusal questions "
        "received identical answers. Do not score this run."
    )
    print("Preflight passed: factual and refusal responses are isolated.")

eval_id = str(uuid.uuid4())
answer_rows = []
step_rows = []
seen_thread_ids = set()

for _, case in cases.iterrows():
    for repeat_number in range(1, REPEATS + 1):
        result, steps = safe_run_one_case(
            fabric_client,
            assistant.id,
            case,
            repeat_number,
            eval_id,
        )
        if result["thread_id"] is not None:
            if result["thread_id"] in seen_thread_ids:
                raise RuntimeError(
                    f"Thread ID was reused: {result['thread_id']}"
                )
            seen_thread_ids.add(result["thread_id"])
        answer_rows.append(result)
        step_rows.extend(steps)
        print(
            f"{result['id']} repeat {repeat_number}: "
            f"{result['response_status']} | "
            f"thread={result['thread_id']} | "
            f"{result['duration_seconds']}s"
        )

runs = pd.DataFrame(answer_rows)
response_steps = pd.DataFrame(step_rows)


def result_type(answer):
    value = str(answer).strip()
    if value == "" or value.lower() == "nan":
        return "NO_ANSWER"
    if value.startswith("ERROR ("):
        return "INFRA_ERROR"
    return "SCORED"


runs["result_type"] = runs["actual_answer"].map(result_type)
scored_answers = runs.loc[
    runs["result_type"] == "SCORED",
    ["question", "actual_answer"],
].drop_duplicates()
if len(scored_answers) > 1 and scored_answers["actual_answer"].nunique() == 1:
    display(scored_answers)
    raise RuntimeError(
        "Response-isolation check failed: every distinct question received the "
        "same answer. Do not score this run."
    )

print(f"eval_id={eval_id}")
print(runs["result_type"].value_counts().to_dict())
infra_errors = runs[runs["result_type"] == "INFRA_ERROR"]
if not infra_errors.empty:
    display(infra_errors[["id", "question", "actual_answer"]])
display(response_steps)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## Step 6 - Score and log to MLflow
#
# The calibrated judge grades every `SCORED` answer. We split accuracy into **factual**
# (numeric and list questions) and **behavioral** (refusal and clarification), so a
# fragile behavioral case never distorts the factual quality number. Infra errors are
# reported separately as reliability. The agent config, metrics, per-question results,
# and judge traces are all logged to one MLflow run.

# CELL ********************

scored = runs[runs["result_type"] == "SCORED"].copy()
n_infra = int((runs["result_type"] == "INFRA_ERROR").sum())
n_noans = int((runs["result_type"] == "NO_ANSWER").sum())

if scored.empty:
    display(runs[["id", "question", "result_type", "actual_answer"]])
    raise RuntimeError(
        "No scoreable Data Agent responses were returned. "
        f"INFRA_ERROR={n_infra}, NO_ANSWER={n_noans}. "
        "Resolve the agent or Assistants API configuration before grading."
    )

with mlflow.start_run(run_name=f"{STAGE}-{RUN_TS}") as run:
    run_id = run.info.run_id
    mlflow.set_tags({
        "stage": STAGE,
        "agent": AGENT["label"],
        "config_hash": config_hash,
        "agent_api": "assistants-temporary-fix",
    })
    mlflow.log_params({
        "agent_label": AGENT["label"],
        "agent_name": AGENT["name"],
        "agent_workspace": AGENT["workspace"],
        "agent_data_stage": AGENT["data_agent_stage"],
        "agent_api": "assistants-temporary-fix",
        "gt_model": GT_MODEL,
        "agent_runtime_model": AGENT_MODEL,
        "reference_model": REFERENCE_MODEL,
        "sdk_version": "0.1.28a0",
        "temporary_parser_workaround": True,
        "eval_set_url": EVAL_XLSX_URL,
        "judge_model": JUDGE_MODEL,
        "judge_api_version": JUDGE_API_VERSION,
        "judge_seed": JUDGE_SEED,
        "rubric_hash": RUBRIC_HASH,
        "judge_response_format": "json_object",
        "judge_run_id": JUDGE_RUN_ID,
        "judge_from_registry": True,
        "judge_holdout_raw": holdout_metrics.get("raw"),
        "judge_holdout_kappa": holdout_metrics.get("kappa"),
        "judge_holdout_recall_fail": holdout_metrics.get("recall_fail"),
        "response_steps_artifact": "response_steps.csv",
        "repeats": REPEATS,
        "stage": STAGE,
        "eval_id": eval_id,
        "run_ts": RUN_TS,
        **config_params,
    })
    mlflow.log_text(RUBRIC, "judge_rubric.txt")
    with open("agent_config.json", "w", encoding="utf-8") as config_file:
        config_file.write(config_json)
    mlflow.log_artifact("agent_config.json")

    judge_results = scored.apply(
        lambda row: judge(
            row.question,
            row.expected_answer,
            row.actual_answer,
        ),
        axis=1,
    ).tolist()
    scored["pass"] = [result[0] for result in judge_results]
    scored["reason"] = [result[1] for result in judge_results]

    per_q = (
        scored.groupby("question")
        .agg(
            pass_rate=("pass", "mean"),
            sample_answer=("actual_answer", "first"),
            reason=("reason", "first"),
        )
        .reset_index()
    )
    per_q = cases[[
        "id",
        "goal",
        "question",
        "answer_type",
        "expected_measure",
        "expected_period",
        "policy_area",
        "dax",
        "ground_truth_json",
        "expected_display",
        "expected_answer",
        "reference_source",
    ]].merge(per_q, on="question", how="left")
    per_q["correct"] = per_q["pass_rate"] >= 0.5
    per_q["scored"] = per_q["pass_rate"].notna()

    factual = per_q[per_q["answer_type"] != "behavioral"]
    behavioral = per_q[per_q["answer_type"] == "behavioral"]
    metrics = {
        "overall_accuracy": per_q.loc[per_q["scored"], "correct"].mean(),
        "factual_accuracy": factual.loc[factual["scored"], "correct"].mean(),
        "behavioral_accuracy": behavioral.loc[
            behavioral["scored"], "correct"
        ].mean(),
        "n_questions": len(per_q),
        "n_scored": int(per_q["scored"].sum()),
        "infra_error_count": n_infra,
        "no_answer_count": n_noans,
    }
    mlflow.log_metrics({
        key: float(value)
        for key, value in metrics.items()
        if pd.notna(value)
    })

    for goal, subset in per_q.groupby("goal"):
        if subset["scored"].any():
            key = "acc__" + "".join(
                character if character.isalnum() else "_"
                for character in goal
            )[:40]
            mlflow.log_metric(
                key,
                float(subset.loc[subset["scored"], "correct"].mean()),
            )

    per_q.to_csv("per_question.csv", index=False)
    mlflow.log_artifact("per_question.csv")
    reference_review.to_csv("reference_answers.csv", index=False)
    mlflow.log_artifact("reference_answers.csv")
    runs.to_csv("agent_responses.csv", index=False)
    mlflow.log_artifact("agent_responses.csv")
    response_steps.to_csv("response_steps.csv", index=False)
    mlflow.log_artifact("response_steps.csv")

    # MLflow renders log_table JSON artifacts as searchable tables.
    mlflow.log_table(
        data=per_q,
        artifact_file="tables/per_question.json",
    )
    mlflow.log_table(
        data=runs,
        artifact_file="tables/agent_responses.json",
    )
    mlflow.log_table(
        data=reference_review,
        artifact_file="tables/reference_answers.json",
    )
    if not response_steps.empty:
        mlflow.log_table(
            data=response_steps,
            artifact_file="tables/response_steps.json",
        )

    # Each question also gets an expandable detail artifact.
    for _, detail in per_q.iterrows():
        question_id = str(detail["id"])
        detail_payload = json.loads(
            detail.to_json(date_format="iso")
        )
        detail_payload["responses"] = json.loads(
            runs.loc[runs["id"] == question_id].to_json(
                orient="records",
                date_format="iso",
            )
        )
        detail_payload["agent_run_steps"] = (
            json.loads(
                response_steps.loc[
                    response_steps["id"] == question_id
                ].to_json(
                    orient="records",
                    date_format="iso",
                )
            )
            if not response_steps.empty
            else []
        )
        mlflow.log_dict(
            detail_payload,
            f"questions/{question_id}.json",
        )

    if JUDGE_FINGERPRINTS:
        mlflow.set_tag(
            "judge_system_fingerprint",
            ",".join(sorted(JUDGE_FINGERPRINTS)),
        )

print(f"Logged run {run_id}")
pd.Series(metrics).to_frame("value")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## Per-question review
#
# Review every judge failure and every prohibited-domain case. `agent_responses.csv` preserves
# the isolated thread, run, user-message, and assistant-message IDs. `response_steps.csv`
# preserves the serialized run steps captured before thread cleanup.

# CELL ********************

detail_columns = [
    column for column in [
        "id", "goal", "answer_type", "expected_measure", "expected_period",
        "policy_area", "correct", "expected_answer", "sample_answer", "reason",
    ]
    if column in per_q.columns
]
display(per_q[detail_columns])

failed_questions = set(per_q.loc[per_q["correct"] == False, "question"])
diagnostic_view = runs[runs["question"].isin(failed_questions)].copy()
display(diagnostic_view)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## Step 7 - Visualise this run
#
# Two views: accuracy by goal (where the agent is strong or weak) and a per-question
# result strip. Both are also saved to the MLflow run as artifacts.

# CELL ********************

def log_fig(fig, name):
    fig.savefig(name, bbox_inches="tight", dpi=120)
    with mlflow.start_run(run_id=run_id):
        mlflow.log_artifact(name)

by_goal = per_q.loc[per_q.scored].groupby("goal")["correct"].mean().mul(100).sort_values()
fig, ax = plt.subplots(figsize=(8, 0.5 * len(by_goal) + 1))
ax.barh(by_goal.index.str.slice(0, 50), by_goal.values, color="#4C78A8")
ax.set_xlim(0, 100)
ax.set_xlabel("accuracy %")
ax.set_title(f"Accuracy by goal - {AGENT['label']} ({STAGE})")
for i, v in enumerate(by_goal.values):
    ax.text(v + 1, i, f"{v:.0f}%", va="center")
log_fig(fig, "accuracy_by_goal.png")
plt.show()

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

status = per_q.set_index("id").apply(
    lambda r: "PASS" if r.correct else ("INFRA" if not r.scored else "FAIL"), axis=1)
colors = {"PASS": "#2E7D32", "FAIL": "#C62828", "INFRA": "#9E9E9E"}

fig, ax = plt.subplots(figsize=(6, 0.4 * len(status) + 1))
ax.barh(range(len(status)), [1] * len(status), color=[colors[s] for s in status])
ax.set_yticks(range(len(status)))
ax.set_yticklabels(status.index)
ax.set_xticks([])
ax.invert_yaxis()
ax.set_title(f"Per-question result - {AGENT['label']} ({STAGE})")
for i, s in enumerate(status):
    ax.text(0.5, i, s, ha="center", va="center", color="white", fontweight="bold")
log_fig(fig, "per_question_result.png")
plt.show()

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## Step 8 - Quality over time (drift)
#
# Read every run of this experiment from MLflow and plot accuracy over time. On a daily
# schedule this is your drift monitor; across a dev / optimize loop it shows whether a
# change helped. It needs at least two runs, so it is empty on the very first run.

# CELL ********************

history = mlflow.search_runs(experiment_names=[EXPERIMENT], order_by=["start_time"])

if len(history) < 2:
    print("Only one run so far - the trend appears once you have run this notebook again.")
else:
    h = history.dropna(subset=["metrics.overall_accuracy"]).copy()
    h["when"] = pd.to_datetime(h["start_time"])
    fig, ax = plt.subplots(figsize=(9, 4))
    for stage, sub in h.groupby("tags.stage"):
        ax.plot(sub["when"], sub["metrics.overall_accuracy"] * 100, marker="o", label=stage)
    ax.set_ylim(0, 100)
    ax.set_ylabel("overall accuracy %")
    ax.set_title("Data Agent accuracy over time")
    ax.legend(title="stage")
    fig.autofmt_xdate()
    plt.show()
    h[["when", "tags.stage", "tags.agent", "tags.config_hash", "metrics.overall_accuracy",
       "metrics.factual_accuracy", "metrics.behavioral_accuracy", "metrics.infra_error_count"]]

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## Step 9 - Compare two stages (before vs after)
#
# To show a before/after story, run this notebook twice - once with `STAGE = \"before\"`
# against the messy agent, once with `STAGE = \"after\"` against the cleaned agent.
# This cell reads the latest run of each stage from MLflow and compares them. It is
# empty until both stages exist.

# CELL ********************

runs_all = mlflow.search_runs(experiment_names=[EXPERIMENT], order_by=["start_time DESC"])
latest = runs_all.dropna(subset=["tags.stage"]).groupby("tags.stage").first()

want = ["before", "after"]
have = [s for s in want if s in latest.index]
if len(have) < 2:
    print(f"Need both stages to compare. Found: {list(latest.index)}.")
else:
    cmp = latest.loc[have, ["metrics.overall_accuracy",
                            "metrics.factual_accuracy",
                            "metrics.behavioral_accuracy"]].mul(100)
    cmp.columns = ["overall", "factual", "behavioral"]

    fig, ax = plt.subplots(figsize=(8, 4))
    x = range(len(cmp.columns))
    width = 0.35
    for i, stage in enumerate(have):
        ax.bar([p + i * width for p in x], cmp.loc[stage], width, label=stage)
    ax.set_xticks([p + width / 2 for p in x])
    ax.set_xticklabels(cmp.columns)
    ax.set_ylim(0, 100)
    ax.set_ylabel("accuracy %")
    ax.set_title("Before vs after")
    ax.legend(title="stage")
    for i, stage in enumerate(have):
        for j, v in enumerate(cmp.loc[stage]):
            ax.text(j + i * width, v + 1, f"{v:.0f}%", ha="center")
    plt.show()
    display(cmp.round(1))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }
