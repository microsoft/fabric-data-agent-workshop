import argparse
import json
import os
import shutil
import stat
import subprocess
import uuid
import zipfile
from pathlib import Path


EXPECTED_SOURCE_HEAD = "0efe648"
LOGICAL_ID = "data-agent-l400"
REPO_OWNER = "pawarbi"
REPO_NAME = "fda-l400"
REPO_REF = "v0.1.2-test"
RAW_ROOT = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/{REPO_REF}"
NAMESPACE = uuid.UUID("6908bc73-6001-475c-8dd5-774509e183bf")

NOTEBOOKS = {
    "NB_OpsRefLakehouse_Build_and_Views_L400.ipynb": (
        "BuildOpsRefData.Notebook",
        "BuildOpsRefData",
    ),
    "NB_DataAgent_SDK_Setup_L400.ipynb": (
        "CreateMultiSourceDataAgent.Notebook",
        "CreateMultiSourceDataAgent",
    ),
    "NB_JudgeCalibration_L400.ipynb": (
        "JudgeCalibration.Notebook",
        "JudgeCalibration",
    ),
    "NB_DataAgentEval_L400.ipynb": (
        "EvaluateDataAgent.Notebook",
        "EvaluateDataAgent",
    ),
}

NAME_REPLACEMENTS = {
    "Manufacturing Ops AI Ready": "ManufacturingOpsAIReady",
    "Manufacturing Ops": "ManufacturingOps",
    "NB_OpsRefLakehouse_Build_and_Views_L400": "BuildOpsRefData",
    "NB_DataAgent_SDK_Setup_L400": "CreateMultiSourceDataAgent",
    "NB_JudgeCalibration_L400": "JudgeCalibration",
    "NB_DataAgentEval_L400": "EvaluateDataAgent",
}


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.lstrip("\ufeff"), encoding="utf-8", newline="\n")


def write_json(path: Path, value: object) -> None:
    write_text(path, json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def logical_id(name: str) -> str:
    return str(uuid.uuid5(NAMESPACE, name))


def platform(item_type: str, display_name: str) -> dict:
    return {
        "$schema": (
            "https://developer.microsoft.com/json-schemas/fabric/"
            "gitIntegration/platformProperties/2.0.0/schema.json"
        ),
        "metadata": {
            "type": item_type,
            "displayName": display_name,
            "description": "",
        },
        "config": {
            "version": "2.0",
            "logicalId": logical_id(f"{display_name}.{item_type}"),
        },
    }


def rewrite_source_references(text: str) -> str:
    old_repository = "data-agent-" + "L400-workshop"
    old_default_ref = "ma" + "in"
    text = text.replace(
        "https://raw.githubusercontent.com/pawarbi/"
        f"{old_repository}/{old_default_ref}",
        RAW_ROOT,
    )
    text = text.replace(
        "https://raw.githubusercontent.com/pawarbi/"
        f"{old_repository}/",
        f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/",
    )
    text = text.replace(
        'DATA_SOURCE_REF = "main"',
        f'DATA_SOURCE_REF = "{REPO_REF}"',
    )
    for old, new in NAME_REPLACEMENTS.items():
        text = text.replace(old, new)
    return text


def notebook_source(cells: list[dict]) -> str:
    lines = [
        "# Fabric notebook source",
        "",
        "# METADATA ********************",
        "",
        "# META {",
        '# META   "kernel_info": {',
        '# META     "name": "jupyter",',
        '# META     "jupyter_kernel_name": "python3.11"',
        "# META   },",
        '# META   "dependencies": {',
        '# META     "lakehouse": {',
        '# META       "default_lakehouse_name": "",',
        '# META       "default_lakehouse_workspace_id": ""',
        "# META     }",
        "# META   }",
        "# META }",
        "",
    ]
    for cell in cells:
        content = "".join(cell.get("source", []))
        content = rewrite_source_references(content).rstrip("\n")
        if cell["cell_type"] == "markdown":
            lines.extend(["# MARKDOWN ********************", ""])
            lines.extend(f"# {line}" if line else "#" for line in content.split("\n"))
            lines.append("")
        else:
            lines.extend(["# CELL ********************", "", content, ""])
            lines.extend(
                [
                    "# METADATA ********************",
                    "",
                    "# META {",
                    '# META   "language": "python",',
                    '# META   "language_group": "jupyter_python"',
                    "# META }",
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def convert_notebook(source: Path, destination: Path, display_name: str) -> None:
    payload = json.loads(source.read_text(encoding="utf-8-sig"))
    write_text(destination / "notebook-content.py", notebook_source(payload["cells"]))
    write_json(destination / ".platform", platform("Notebook", display_name))


def markdown_notebook(cells: list[str]) -> str:
    return notebook_source(
        [{"cell_type": "markdown", "source": cell} for cell in cells]
    )


def build_getting_started(destination: Path) -> None:
    cells = [
        """# DataAgentGettingStarted - Fabric Data Agent L400 Workshop

Welcome to the Fabric Data Agent L400 Jumpstart. This orientation notebook
explains what was installed, how the workshop components fit together, and
the order in which to complete the lab.

This notebook is documentation-only. It does not create connections, refresh
semantic models, create Fabric items, or otherwise change your environment.

## Learning objectives

1. Compare a baseline semantic model with an AI-ready semantic model.
2. Create and configure a governed Fabric Data Agent.
3. Extend the agent with a Lakehouse source for multi-source reasoning.
4. Define evaluation questions and live DAX ground truth.
5. Calibrate an LLM judge and track quality and failure modes with MLflow.""",
        """## Architecture

`GitHub data -> anonymous Web connection -> semantic models -> reports`

`ManufacturingOpsAIReady -> base Data Agent -> OpsRefData Lakehouse`

`Base Data Agent + OpsRefData -> multi-source Data Agent -> evaluation + MLflow`""",
        """## Prerequisites

- Install all Jumpstart items into the same Fabric workspace.
- Use a capacity and tenant with notebooks, semantic models, reports, Data
  Agents, Lakehouses, and MLflow available.
- Confirm you can create workspace items and Fabric connections.
- Confirm outbound access to public `raw.githubusercontent.com` content.
- Keep installed item names unchanged so notebook discovery succeeds.
- Have permission to create and publish a Fabric Data Agent.""",
        """## Exact installed item inventory

| Type | Installed item | Purpose |
| --- | --- | --- |
| Notebook | `DataAgentGettingStarted` | Orientation and navigation |
| Notebook | `DataAgentSetup` | Connection binding and model refresh |
| Notebook | `BuildOpsRefData` | Builds the `OpsRefData` Lakehouse assets |
| Notebook | `CreateMultiSourceDataAgent` | Adds the Lakehouse source and publishes the multi-source agent |
| Notebook | `JudgeCalibration` | Calibrates and registers the LLM judge |
| Notebook | `EvaluateDataAgent` | Runs the evaluation workflow |
| Semantic model | `ManufacturingOps` | Baseline model |
| Semantic model | `ManufacturingOpsAIReady` | AI-ready model |
| Report | `ManufacturingOps` | Baseline report |
| Report | `ManufacturingOpsAIReady` | AI-ready report |

Data Agents are intentionally not installed. Creating them is part of the lab.""",
        f"""## Documentation and lab order

- [Workshop documentation](https://github.com/{REPO_OWNER}/{REPO_NAME}/tree/{REPO_REF}/documentation)
- [Lab instructions](https://github.com/{REPO_OWNER}/{REPO_NAME}/tree/{REPO_REF}/documentation/lab-instructions)

Complete the workshop in this order:

1. Read `DataAgentGettingStarted`.
2. Run `DataAgentSetup`.
3. Compare the `ManufacturingOps` and `ManufacturingOpsAIReady` reports/models.
4. Create `MfgOps_DA_AIReady_SAP` over `ManufacturingOpsAIReady`.
5. Run `BuildOpsRefData`.
6. Run `CreateMultiSourceDataAgent`.
7. Run `JudgeCalibration`.
8. Run `EvaluateDataAgent`.""",
        """## Next step

Open `DataAgentSetup` and run every cell. Wait for both semantic-model
refreshes to complete before continuing with the lab.""",
    ]
    write_text(destination / "notebook-content.py", markdown_notebook(cells))
    write_json(destination / ".platform", platform("Notebook", "DataAgentGettingStarted"))


def build_setup(template: Path, destination: Path) -> None:
    text = template.read_text(encoding="utf-8-sig")
    text = text.replace("python3.12", "python3.11")
    write_text(destination / "notebook-content.py", text)
    write_json(destination / ".platform", platform("Notebook", "DataAgentSetup"))


def extract_zip_prefix(pbix: Path, prefix: str, destination: Path) -> None:
    with zipfile.ZipFile(pbix) as archive:
        for member in archive.infolist():
            if member.is_dir() or not member.filename.startswith(prefix):
                continue
            relative = Path(member.filename[len(prefix) :])
            output = destination / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            content = archive.read(member)
            if b"\x00" in content[:32]:
                write_text(output, content.decode("utf-16-le"))
            else:
                output.write_bytes(content)


def normalize_text_tree(root: Path) -> None:
    suffixes = {".json", ".tmdl", ".md", ".py", ".pbir", ".pbism", ".txt"}
    for path in root.rglob("*"):
        if path.is_file() and (path.name == ".platform" or path.suffix.lower() in suffixes):
            try:
                text = path.read_text(encoding="utf-8-sig")
            except UnicodeDecodeError:
                continue
            write_text(path, rewrite_source_references(text))


def build_semantic_model(
    destination: Path,
    display_name: str,
    extracted_model: Path,
    pbix: Path,
    qna_enabled: bool,
) -> None:
    shutil.copytree(extracted_model, destination / "definition")
    extract_zip_prefix(pbix, "Copilot/", destination / "Copilot")
    normalize_text_tree(destination)

    database = destination / "definition" / "database.tmdl"
    lines = database.read_text(encoding="utf-8").splitlines()
    lines[0] = f"database '{display_name}'"
    while lines and not lines[-1]:
        lines.pop()
    write_text(database, "\n".join(lines) + "\n")
    write_json(destination / ".platform", platform("SemanticModel", display_name))
    write_json(
        destination / "definition.pbism",
        {
            "$schema": (
                "https://developer.microsoft.com/json-schemas/fabric/item/"
                "semanticModel/definitionProperties/1.0.0/schema.json"
            ),
            "version": "6.0",
            "settings": {"qnaEnabled": qna_enabled},
        },
    )


def build_report(
    destination: Path,
    display_name: str,
    semantic_model_folder: str,
    pbix: Path,
) -> None:
    extract_zip_prefix(pbix, "Report/definition/", destination / "definition")
    extract_zip_prefix(pbix, "Report/StaticResources/", destination / "StaticResources")
    normalize_text_tree(destination)
    write_json(destination / ".platform", platform("Report", display_name))
    write_json(
        destination / "definition.pbir",
        {
            "$schema": (
                "https://developer.microsoft.com/json-schemas/fabric/item/"
                "report/definitionProperties/2.0.0/schema.json"
            ),
            "version": "4.0",
            "datasetReference": {"byPath": {"path": f"../{semantic_model_folder}"}},
        },
    )


def extract_pbix(pbi_tools: Path, pbix: Path, destination: Path) -> None:
    subprocess.run(
        [
            str(pbi_tools),
            "extract",
            str(pbix),
            "-extractFolder",
            str(destination),
            "-modelSerialization",
            "Tmdl",
        ],
        check=True,
    )


def replace_generated_path(path: Path) -> None:
    if path.is_dir():
        def remove_readonly(function, filename, _exc_info):
            os.chmod(filename, stat.S_IWRITE)
            function(filename)

        shutil.rmtree(path, onerror=remove_readonly)
    elif path.exists():
        path.unlink()


def build_readme(target: Path) -> None:
    write_text(
        target / "README.md",
        f"""# Fabric Data Agent L400 Jumpstart

Generated from `data-agent-L400-workshop` commit `{EXPECTED_SOURCE_HEAD}`.

## Direct pre-registration installation

```python
import fabric_jumpstart as jumpstart

jumpstart._install_from_github(
    logical_id="{LOGICAL_ID}",
    repo_url="https://github.com/{REPO_OWNER}/{REPO_NAME}",
    repo_ref="{REPO_REF}",
    workspace_path=".",
    entry_point="DataAgentGettingStarted.Notebook",
    items_in_scope=["Notebook", "SemanticModel", "Report"],
    workspace_id="<fabric-workspace-id>",
)
```

`_install_from_github` is an underscore API for pre-registration testing.

## Registered installation (later)

```python
import fabric_jumpstart as jumpstart

jumpstart.install("{LOGICAL_ID}")
```

This command will work only after the Jumpstart is registered. Until then, use
the direct pre-registration installation shown above.

After installation, open `DataAgentGettingStarted`, then run `DataAgentSetup`
when directed to bind the public Web source and refresh both semantic models.

## Repository layout

- `{LOGICAL_ID}/`: Fabric workspace items deployed by Jumpstart.
- `documentation/`: GitHub-only workshop and lab documentation.
- `data/`: GitHub-only source data consumed by models and notebooks.
- `eval/`: GitHub-only evaluation and calibration workbooks.
- `tools/`: local rebuild tooling; not deployed to Fabric.

The source workshop repository remains unchanged. PBIX models are freshly
serialized with pbi-tools during rebuild; report and Copilot assets come
directly from the latest PBIX packages.
""",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--pbi-tools", type=Path, required=True)
    args = parser.parse_args()

    source = args.source.resolve()
    target = args.target.resolve()
    if source == target:
        raise RuntimeError("Source and target must be different repositories.")
    if not (target / ".git").is_dir():
        raise RuntimeError("Target must be the existing Git repository.")
    head = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "--short", "HEAD"],
        text=True,
    ).strip()
    if head != EXPECTED_SOURCE_HEAD:
        raise RuntimeError(f"Expected source {EXPECTED_SOURCE_HEAD}, found {head}.")

    build_root = target / ".build-pbix"
    replace_generated_path(build_root)
    build_root.mkdir()
    try:
        baseline_pbix = source / "semantic-models" / "Manufacturing Ops.pbix"
        ai_pbix = source / "semantic-models" / "Manufacturing Ops AI Ready.pbix"
        extract_pbix(args.pbi_tools, baseline_pbix, build_root / "ManufacturingOps")
        extract_pbix(args.pbi_tools, ai_pbix, build_root / "ManufacturingOpsAIReady")

        for relative in [LOGICAL_ID, "data", "eval", "documentation", "lab-instructions"]:
            replace_generated_path(target / relative)

        shutil.copytree(source / "data", target / "data")
        shutil.copytree(source / "eval", target / "eval")
        shutil.copy2(source / "LICENSE", target / "LICENSE")

        docs = target / "documentation"
        shutil.copytree(source / "lab-instructions", docs / "lab-instructions")
        write_text(
            docs / "README.md",
            "# Documentation\n\n"
            "GitHub-hosted workshop documentation. This folder is not a Fabric "
            "workspace item.\n\n"
            "- [Lab instructions](lab-instructions/)\n",
        )
        write_text(
            docs / "lab-instructions" / "README.md",
            "# Lab instructions\n\n"
            "- [Fabric Data Agent Workshop Labs - August 2026]"
            "(Fabric%20Data%20Agent%20Workshop%20Labs%20-%20Aug%202026.pdf)\n",
        )

        workspace = target / LOGICAL_ID
        for source_name, (folder_name, display_name) in NOTEBOOKS.items():
            convert_notebook(
                source / "notebooks" / source_name,
                workspace / folder_name,
                display_name,
            )
        build_getting_started(workspace / "DataAgentGettingStarted.Notebook")
        build_setup(
            target / "tools" / "templates" / "DataAgentSetup.notebook-content.py",
            workspace / "DataAgentSetup.Notebook",
        )

        build_semantic_model(
            workspace / "ManufacturingOps.SemanticModel",
            "ManufacturingOps",
            build_root / "ManufacturingOps" / "Model",
            baseline_pbix,
            False,
        )
        build_report(
            workspace / "ManufacturingOps.Report",
            "ManufacturingOps",
            "ManufacturingOps.SemanticModel",
            baseline_pbix,
        )
        build_semantic_model(
            workspace / "ManufacturingOpsAIReady.SemanticModel",
            "ManufacturingOpsAIReady",
            build_root / "ManufacturingOpsAIReady" / "Model",
            ai_pbix,
            True,
        )
        build_report(
            workspace / "ManufacturingOpsAIReady.Report",
            "ManufacturingOpsAIReady",
            "ManufacturingOpsAIReady.SemanticModel",
            ai_pbix,
        )
        normalize_text_tree(workspace)
        build_readme(target)
    finally:
        replace_generated_path(build_root)


if __name__ == "__main__":
    main()
