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

# # Data Agent Evaluation - L400
#
# `[Fixed eval set] -> [Live DAX ground truth or expected behavior] -> [Run Data Agent] -> [Load registered champion judge] -> [Grade responses] -> [Human review] -> [Log and compare in MLflow]`
#
# This notebook evaluates manufacturing operations questions against live semantic-model ground
# truth and evaluates policy questions against human-authored expected behavior. Questions with
# no explicit time period use the 30 days ending on the latest production date.

# MARKDOWN ********************

# ## Setup
#
# MLflow is the system of record for results. The first line upgrades the notebook to MLflow 3 and installs required libraries.

# CELL ********************

%pip install -q "synapseml-mlflow[online-notebook]>=2.0.3" "mlflow-skinny==3.1.0" "opentelemetry-api<=1.40.0" openpyxl -U fabric-data-agent-sdk

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
from fabric.dataagent.evaluation import evaluate_data_agent, get_evaluation_details
from fabric.dataagent.client import FabricDataAgentManagement, FabricOpenAIResponses
from synapse.ml.fabric.credentials import get_openai_httpx_sync_client
import openai

# Suppress known FutureWarning messages from installed libraries.
warnings.filterwarnings("ignore", category=FutureWarning)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## Select the Data Agent
#
# Change only `DATA_AGENT_NAME` to the display name of the Data Agent you want to evaluate. The notebook confirms that the agent exists in the current workspace before continuing.

# CELL ********************

# Change only this value to evaluate a different Data Agent.
DATA_AGENT_NAME = "MfgOps_DA_AIReady_SAP"

CURRENT_WORKSPACE_ID = fabric.get_notebook_workspace_id()
available_data_agents = fabric.list_items("DataAgent")["Display Name"]
available_data_agent_names = set(
    available_data_agents.dropna().astype(str)
)

if DATA_AGENT_NAME not in available_data_agent_names:
    raise ValueError(
        f"Data Agent {DATA_AGENT_NAME!r} was not found in the current workspace. "
        f"Available Data Agents: {sorted(available_data_agent_names)}"
    )

print(f"Data Agent found: {DATA_AGENT_NAME}")

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

GT_WORKSPACE = CURRENT_WORKSPACE_ID
GT_MODEL = "ManufacturingOpsAIReady"

# Set to "Yes" only when this run must refresh the semantic model first.
REFRESH = "No"
REFRESH_POLL_SECONDS = 15
REFRESH_TIMEOUT_SECONDS = 1800

AGENT = {
    "label": DATA_AGENT_NAME,
    "name": DATA_AGENT_NAME,
    "workspace": CURRENT_WORKSPACE_ID,
    "table": "eval_results_l400",
    "data_agent_stage": "sandbox",
}
STAGE = "after"  # RUN label: baseline / monitor / before / after / optimize

EXPERIMENT = "mfg-ops-data-agent-eval"
REPEATS = 1  # Independent evaluation attempts per question
TEST_MODE = True
TEST_CASE_IDS = [
    "highest_scrap_rate_line",
    "avg_day_production_yield_this_year",
    "highest_sales_product_this_year",
]

RUN_TS = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
mlflow.set_experiment(EXPERIMENT)
print(
    f"Experiment: {EXPERIMENT} | stage: {STAGE} | "
    f"agent: {AGENT['label']} | {RUN_TS} UTC"
)

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

DATA_SOURCE_REF = "v1.0.3"  # Use an immutable release tag or commit for reproducible runs.
EVAL_XLSX_URL = (
    "https://raw.githubusercontent.com/microsoft/fabric-data-agent-workshop/"
    f"{DATA_SOURCE_REF}/eval/eval_set_L400.xlsx"
)
EVAL_LH_NAME = "mfgops_da_eval"
EVAL_FILE_NAME = "eval_set_L400.xlsx"

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
# Refresh the trusted model, then run each question's DAX with `fabric.evaluate_dax`.
# `format_gt` serialises every row of the result, so list and group-by answers keep all
# their rows. Behavioral questions use their `expected_behavior` text as the reference.
# We assert no factual question came back empty, then show the ground truth for review.

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

def is_percentage_measure(expected_measure, column_name):
    text = f"{expected_measure} {column_name}".lower()
    return "%" in text or " pct" in text or "percent" in text


def format_gt(df, expected_measure=""):
    rows = []
    for _, r in df.iterrows():
        parts = []
        for col, val in r.items():
            name = col.strip("[]").split("[")[-1].rstrip("]")
            if isinstance(val, (int, float)) and is_percentage_measure(
                expected_measure,
                col,
            ):
                percentage = val * 100 if abs(val) <= 1.5 else val
                parts.append(f"{name}: {percentage:.2f}%")
            elif isinstance(val, float) and val == int(val):
                parts.append(f"{name}: {int(val):,}")
            elif isinstance(val, (int, float)):
                parts.append(f"{name}: {val:,.2f}")
            else:
                parts.append(f"{name}: {val}")
        rows.append(", ".join(parts))
    return " | ".join(rows)


def ground_truth(row):
    if row["answer_type"] == "behavioral":
        return row["expected_behavior"], 1
    df = fabric.evaluate_dax(GT_MODEL, row["dax"], workspace=GT_WORKSPACE)
    return format_gt(df, row["expected_measure"]), len(df)


ground_truth_results = []
for _, row in cases.iterrows():
    print(f"Computing ground truth: {row['id']}")
    ground_truth_results.append(ground_truth(row))

cases["expected_answer"], cases["gt_rows"] = zip(*ground_truth_results)

# A factual question with zero ground-truth rows means the DAX or the data is wrong.
empty = cases[(cases.answer_type != "behavioral") & (cases.gt_rows == 0)]
assert empty.empty, f"Factual questions returned no ground truth: {list(empty.id)}"

cases[["id", "answer_type", "gt_rows", "expected_answer"]]

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

    response = judge_client.chat.completions.create(**request)
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

# Read the published configuration and support either instruction attribute name.
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

# ## Step 5 - Run the agent with the Responses API
#
# The SDK evaluation helper currently creates a Responses API conversation for every row.
# Some Fabric environments do not have the `/conversations` feature enabled and return
# `404 Feature is not enabled`.
#
# This runner sends each evaluation question as an independent `responses.create()` request.
# It still uses `FabricOpenAIResponses`, but it does not require conversations or threads.
# Response output items are captured for diagnostics.

# CELL ********************

import time
import uuid

TERMINAL_STATUSES = {"completed", "failed", "incomplete", "cancelled"}


def get_field(value, name, default=None):
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def response_status(response):
    status = get_field(response, "status", "")
    return str(status).lower()


def response_output_items(response):
    return list(get_field(response, "output", []) or [])


def wait_for_response(client, response, timeout_seconds=600, poll_seconds=2):
    started = time.monotonic()
    while response_status(response) not in TERMINAL_STATUSES:
        if time.monotonic() - started > timeout_seconds:
            raise TimeoutError(
                f"Timed out waiting for response {get_field(response, 'id', '')}"
            )
        response_id = get_field(response, "id")
        assert response_id, f"Response has no ID: {response!r}"
        time.sleep(poll_seconds)
        response = client.responses.retrieve(response_id)
    return response


def extract_response_text(response):
    parts = []
    for item in response_output_items(response):
        if get_field(item, "type") != "message":
            continue
        for content in get_field(item, "content", []) or []:
            text = get_field(content, "text")
            if text:
                parts.append(str(text))
    return "\n\n".join(parts) or str(
        get_field(response, "output_text", "") or ""
    )


def extract_response_steps(response):
    steps = []
    for item in response_output_items(response):
        item_type = get_field(item, "type")
        if item_type == "function_call":
            steps.append({
                "type": item_type,
                "name": get_field(item, "name"),
                "arguments": get_field(item, "arguments"),
                "output": None,
            })
        elif item_type == "function_call_output":
            steps.append({
                "type": item_type,
                "name": get_field(item, "name"),
                "arguments": None,
                "output": get_field(item, "output"),
            })
        elif item_type == "code_interpreter_call":
            steps.append({
                "type": item_type,
                "name": item_type,
                "arguments": (
                    get_field(item, "code")
                    or get_field(item, "input")
                ),
                "output": get_field(item, "output"),
            })
    return steps


agent_client = FabricOpenAIResponses(
    artifact_name=AGENT["name"],
    workspace_name=AGENT["workspace"],
    ai_skill_stage=AGENT["data_agent_stage"],
)

print(
    "Agent target:",
    AGENT["name"],
    "| workspace:",
    AGENT["workspace"],
    "| stage:",
    AGENT["data_agent_stage"],
    "| API:",
    getattr(agent_client, "api_type", "unknown"),
)

# Fail fast with the exact service error before starting the full evaluation.
preflight_question = cases.iloc[0]["question"]
try:
    preflight_response = agent_client.responses.create(input=preflight_question)
    preflight_response = wait_for_response(agent_client, preflight_response)
except openai.APIError as error:
    raise RuntimeError(
        "Responses API preflight failed. Confirm that the Responses API is enabled "
        "for this tenant/capacity and that AGENT['data_agent_stage'] targets the "
        "available agent stage. Service error: "
        f"{error}"
    ) from error

print(
    "Responses API preflight:",
    response_status(preflight_response),
    "| response_id:",
    get_field(preflight_response, "id"),
)

eval_id = str(uuid.uuid4())
answer_rows = []
step_rows = []

for _, case in cases.iterrows():
    for repeat_number in range(1, REPEATS + 1):
        started = time.perf_counter()
        try:
            response = agent_client.responses.create(input=case["question"])
            response = wait_for_response(agent_client, response)
            actual_answer = extract_response_text(response)
            status = response_status(response)
            response_id = get_field(response, "id")

            for step_number, step in enumerate(
                extract_response_steps(response),
                start=1,
            ):
                step_rows.append({
                    "eval_id": eval_id,
                    "id": case["id"],
                    "question": case["question"],
                    "repeat": repeat_number,
                    "response_id": response_id,
                    "step_number": step_number,
                    **step,
                })
        except (openai.APIError, TimeoutError, AssertionError) as error:
            actual_answer = f"ERROR ({type(error).__name__}): {error}"
            status = "failed"
            response_id = None

        answer_rows.append({
            "eval_id": eval_id,
            "id": case["id"],
            "question": case["question"],
            "expected_answer": case["expected_answer"],
            "actual_answer": actual_answer,
            "response_status": status,
            "response_id": response_id,
            "repeat": repeat_number,
            "duration_seconds": round(time.perf_counter() - started, 3),
        })
        print(
            f"{case['id']} repeat {repeat_number}: "
            f"{status} ({answer_rows[-1]['duration_seconds']}s)"
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
        "agent_api": "responses",
        "responses_conversations": False,
    })
    mlflow.log_params({
        "agent_label": AGENT["label"],
        "agent_name": AGENT["name"],
        "agent_workspace": AGENT["workspace"],
        "agent_data_stage": AGENT["data_agent_stage"],
        "agent_api": "responses",
        "responses_conversations": False,
        "gt_model": GT_MODEL,
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
        "expected_answer",
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
    runs.to_csv("agent_responses.csv", index=False)
    mlflow.log_artifact("agent_responses.csv")
    response_steps.to_csv("response_steps.csv", index=False)
    mlflow.log_artifact("response_steps.csv")

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
# Review every failure, policy case, and unstable result. Responses API tool details are captured in `response_steps` and logged as `response_steps.csv`. Inspect function-call arguments and outputs to confirm that
# the expected measure and time window were used. This is especially important for
# `Day Yield Pct`, OEE, RQX, TP, and default 30-day behavior.

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

# CELL ********************

notebookutils.session.stop()

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }
