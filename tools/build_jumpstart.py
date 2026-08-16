import argparse
import hashlib
import json
import os
import re
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
WORKSHOP_VERSION = "v0.1.8-test"
RAW_ROOT = (
    f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/{WORKSHOP_VERSION}"
)
LAB_PDF_NAME = "Fabric Data Agent Workshop L400.pdf"
LAB_PDF_RELATIVE_PATH = f"documentation/lab-instructions/{LAB_PDF_NAME}"
NAMESPACE = uuid.UUID("6908bc73-6001-475c-8dd5-774509e183bf")
PBIX_FILES = {
    "ManufacturingOps.pbix": (
        "Manufacturing Ops.pbix",
        "BFC0F3EA44F51EE5A3BE0739BDF268EE298336066CC734306594B4C6B1428F09"
    ),
    "ManufacturingOpsAIReady.pbix": (
        "Manufacturing Ops AI Ready.pbix",
        "95C9F8D395AD3197EB7EB835BB542521C9DBF8C31077C3218842E8B931A9F8EE"
    ),
}

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
GENERATED_WORKSPACE_ITEMS = {
    *(folder_name for folder_name, _display_name in NOTEBOOKS.values()),
    "DataAgentGettingStarted.Notebook",
    "InstallWorkshopAssets.Notebook",
    "RefreshSemanticModel.Notebook",
    "ManufacturingOps.SemanticModel",
    "ManufacturingOps.Report",
    "ManufacturingOpsAIReady.SemanticModel",
    "ManufacturingOpsAIReady.Report",
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
        f'DATA_SOURCE_REF = "{WORKSHOP_VERSION}"',
    )
    for old, new in NAME_REPLACEMENTS.items():
        text = text.replace(old, new)
    return text


def clean_participant_content(
    content: str,
    source_name: str,
    cell_type: str,
) -> str:
    if cell_type == "markdown":
        content = re.sub(
            r"\n?\*\*(?:Author|Date|Version):\*\*[^\n]*\n?",
            "\n",
            content,
        )
        content = re.sub(r"\n{3,}", "\n\n", content)
        if (
            source_name == "NB_JudgeCalibration_L400.ipynb"
            and content.strip() == "## Configuration"
        ):
            content += (
                "\n\nThis workshop uses `REPEATS = 1` for a faster calibration run. "
                "Production evaluation scenarios should generally use `REPEATS = 3` "
                "for more stable results."
            )
        content = content.replace(
            "A new judge version is being considered for a release.",
            "A materially different judge configuration is being considered.",
        )
    else:
        if source_name == "NB_JudgeCalibration_L400.ipynb":
            content = content.replace(
                "REPEATS = 3",
                "REPEATS = 1  # Use 3 for more stable results in production evaluation scenarios.",
            )
            content = content.replace(
                '    "author": "Sandeep Pawar",\n'
                '    "version": "1.0",\n',
                "",
            )
            content = content.replace(
                '        "calibration_version": "1.0",\n',
                "",
            )
        content = content.replace(
            "# The SDK still calls a few of its own deprecated APIs internally -- hide that noise.",
            "# Suppress known FutureWarning messages from installed libraries.",
        )
        content = content.replace(
            "# get_configuration()/get_datasources() are present in every SDK version, so we\n"
            "# read the config the same way everywhere. getattr handles the instructions\n"
            "# attribute being named either \"instructions\" or \"ai_instructions\".",
            "# Read the published configuration and support either instruction attribute name.",
        )
    return content


def notebook_source(cells: list[dict], source_name: str = "") -> str:
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
        content = clean_participant_content(
            content,
            source_name,
            cell["cell_type"],
        )
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
    write_text(
        destination / "notebook-content.py",
        notebook_source(payload["cells"], source.name),
    )
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

- Install all recommended Jumpstart notebook items into the same Fabric workspace.
- Use a capacity and tenant with notebooks, semantic models, reports, Data
  Agents, Lakehouses, and MLflow available.
- Confirm you can create workspace items and Fabric connections.
- Confirm outbound access to public `raw.githubusercontent.com` content.
- Keep installed item names unchanged so notebook discovery succeeds.
- Have permission to create and publish a Fabric Data Agent.""",
        """## Notebook-only Jumpstart inventory

The recommended Jumpstart installation deploys these seven notebook items only:

| Installed notebook | Purpose |
| --- | --- |
| `DataAgentGettingStarted` | Orientation, setup sequence, and navigation |
| `InstallWorkshopAssets` | **Required once after installation:** imports both populated workshop PBIX files |
| `RefreshSemanticModel` | **Optional maintenance; not required for the lab** |
| `BuildOpsRefData` | Builds the `OpsRefData` Lakehouse assets |
| `CreateMultiSourceDataAgent` | Adds the Lakehouse source and publishes the multi-source agent |
| `JudgeCalibration` | Calibrates and registers the LLM judge |
| `EvaluateDataAgent` | Runs the evaluation workflow |

`InstallWorkshopAssets` creates or overwrites these populated Power BI items:

| Type | Created item | Purpose |
| --- | --- | --- |
| Semantic model | `ManufacturingOps` | Baseline model |
| Semantic model | `ManufacturingOpsAIReady` | AI-ready model |
| Report | `ManufacturingOps` | Baseline report |
| Report | `ManufacturingOpsAIReady` | AI-ready report |

Data Agents are intentionally not installed. Creating them is part of the lab.""",
        f"""## Start with the lab instructions

**[Open the Fabric Data Agent Workshop lab instructions (PDF)](https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/{WORKSHOP_VERSION}/documentation/lab-instructions/Fabric%20Data%20Agent%20Workshop%20L400.pdf)**

[Browse the lab-instructions folder](https://github.com/{REPO_OWNER}/{REPO_NAME}/tree/{WORKSHOP_VERSION}/documentation/lab-instructions)

The lab instructions remain the primary workshop guide.""",
        """## Required setup after installation

Complete this exact sequence:

1. Open `DataAgentGettingStarted`.
2. Open and read the lab instructions using the immutable workshop-version
   links above.
3. In the same workspace, open `InstallWorkshopAssets` and select **Run all**.
4. Wait for the explicit success message confirming both PBIX imports, that
   every returned report and semantic model was moved into the same
   `data-agent-l400` folder as the notebooks, and that both semantic models
   returned exactly two rows for the populated-data DAX validation.
5. Only then continue with the `ManufacturingOps` and
   `ManufacturingOpsAIReady`
   report/model comparison.
6. Create the base Data Agent and continue through the workshop lab notebooks
   in the order specified by the lab instructions.

`InstallWorkshopAssets` is **required once after installation**. It uses
`CreateOrOverwrite`, so rerunning it safely replaces the same-named reports and
semantic models. The imported PBIX files contain cached data and do not require
a refresh for the labs. The folder move requires Contributor or higher
workspace role and delegated `Workspace.ReadWrite.All`.""",
        """## Populated-data acceptance gate

After import and folder placement, `InstallWorkshopAssets` runs this exact query
against both `ManufacturingOps` and `ManufacturingOpsAIReady`:

```dax
EVALUATE
    TOPN(2, 'Customers')
```

The notebook uses a bounded, logged retry for brief post-import availability
delays. Each model must return exactly two rows. A query failure or different
row count names the affected model and stops without final success.""",
        """## Optional maintenance

`RefreshSemanticModel` can bind or rebind the anonymous public Web connection
and refresh both semantic models with the latest source data. It is **optional
maintenance and is not required for the lab** because `InstallWorkshopAssets`
imports populated PBIX files with cached data.

Use it only for a future data update or to repair/rebind the Web connection.
It does not create or configure a Fabric Data Agent.""",
    ]
    write_text(destination / "notebook-content.py", markdown_notebook(cells))
    write_json(destination / ".platform", platform("Notebook", "DataAgentGettingStarted"))


def build_refresh_semantic_model(template: Path, destination: Path) -> None:
    text = template.read_text(encoding="utf-8-sig")
    text = text.replace("python3.12", "python3.11")
    text = text.replace("__WORKSHOP_VERSION__", WORKSHOP_VERSION)
    write_text(destination / "notebook-content.py", text)
    write_json(destination / ".platform", platform("Notebook", "RefreshSemanticModel"))


def build_install_workshop_assets(template: Path, destination: Path) -> None:
    text = template.read_text(encoding="utf-8-sig")
    text = text.replace("python3.12", "python3.11")
    text = text.replace("__WORKSHOP_VERSION__", WORKSHOP_VERSION)
    write_text(destination / "notebook-content.py", text)
    write_json(destination / ".platform", platform("Notebook", "InstallWorkshopAssets"))


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

## Install from GitHub

```python
import fabric_jumpstart as jumpstart

jumpstart._install_from_github(
    logical_id="{LOGICAL_ID}",
    repo_url="https://github.com/{REPO_OWNER}/{REPO_NAME}",
    repo_ref="{WORKSHOP_VERSION}",
    workspace_path="{LOGICAL_ID}",
    entry_point="DataAgentGettingStarted.Notebook",
    items_in_scope=["Notebook"],
)
```

`workspace_id` is intentionally omitted so installation targets the current
Fabric workspace. To target another workspace, pass its actual valid GUID.

The recommended install deploys seven notebooks only. It intentionally does not
deploy the Git/TMDL semantic model and report definitions.

After installation:

1. Open `DataAgentGettingStarted`.
2. Open the immutable workshop-version PDF:
   [Fabric Data Agent Workshop L400](https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/{WORKSHOP_VERSION}/documentation/lab-instructions/Fabric%20Data%20Agent%20Workshop%20L400.pdf).
3. In the same workspace, open `InstallWorkshopAssets` and select **Run all**.
4. Wait for explicit success confirming both PBIX imports, that all returned
   reports and semantic models were moved into the same `data-agent-l400`
   folder as the notebooks, and that both semantic models returned exactly two
   rows for the populated-data DAX validation.
5. Only then continue with report/model comparison and the workshop lab
   notebooks.

`InstallWorkshopAssets` is required once. It imports populated PBIX files using
`CreateOrOverwrite`, so rerunning it safely replaces the same-named items.
Cached imported data is immediately available for the labs.
`RefreshSemanticModel` is optional maintenance and is not required for the lab;
use it only for a future data update or connection repair/rebinding.

The folder move uses the Fabric Core `bulkMove` API and requires Contributor or
higher workspace role plus delegated `Workspace.ReadWrite.All`. If moving fails,
the imports may remain at workspace root; `InstallWorkshopAssets` reports the
API error and does not print final success.

The final acceptance gate runs this exact DAX query against both
`ManufacturingOps` and `ManufacturingOpsAIReady`:

```dax
EVALUATE
    TOPN(2, 'Customers')
```

SemPy retries only brief post-import model availability/query failures for a
bounded period. Each semantic model must return exactly two rows. Permanent
query failures or unexpected row counts are reported with the model name and
prevent final success.

## Repository layout

- `{LOGICAL_ID}/`: Fabric Git definitions; the recommended Jumpstart install
  deploys only the `.Notebook` items.
- `assets/pbix/`: canonical populated PBIX files imported by
  `InstallWorkshopAssets`.
- `documentation/`: GitHub-only workshop and lab documentation.
- `data/`: GitHub-only source data consumed by models and notebooks.
- `eval/`: GitHub-only evaluation and calibration workbooks.

The semantic model/report Git folders remain for reference, but the recommended
`items_in_scope=["Notebook"]` install does not deploy them.
""",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--pbi-tools", type=Path, required=True)
    parser.add_argument(
        "--workshop-pdf",
        type=Path,
        help=(
            "Authoritative workshop PDF. Defaults to the canonical PDF already "
            "present in the target repository."
        ),
    )
    args = parser.parse_args()

    source = args.source.resolve()
    target = args.target.resolve()
    canonical_pdf = target / LAB_PDF_RELATIVE_PATH
    workshop_pdf = (
        args.workshop_pdf.resolve()
        if args.workshop_pdf
        else canonical_pdf
    )
    if not workshop_pdf.is_file():
        raise RuntimeError(
            "Workshop PDF not found. Pass --workshop-pdf with the authoritative PDF."
        )
    workshop_pdf_bytes = workshop_pdf.read_bytes()
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

        for relative in ["assets", "data", "eval", "documentation", "lab-instructions"]:
            replace_generated_path(target / relative)
        workspace = target / LOGICAL_ID
        workspace.mkdir(exist_ok=True)
        for item_name in GENERATED_WORKSPACE_ITEMS:
            replace_generated_path(workspace / item_name)

        shutil.copytree(source / "data", target / "data")
        shutil.copytree(source / "eval", target / "eval")
        shutil.copy2(source / "LICENSE", target / "LICENSE")

        pbix_assets = target / "assets" / "pbix"
        pbix_assets.mkdir(parents=True)
        asset_lines = [
            "# Populated workshop PBIX assets",
            "",
            "Canonical PBIX files imported by `InstallWorkshopAssets`.",
            "",
            "| File | Immutable raw URL | SHA-256 |",
            "| --- | --- | --- |",
        ]
        for file_name, (source_file_name, expected_hash) in PBIX_FILES.items():
            source_pbix = source / "semantic-models" / source_file_name
            actual_hash = hashlib.sha256(source_pbix.read_bytes()).hexdigest().upper()
            if actual_hash != expected_hash:
                raise RuntimeError(
                    f"Unexpected hash for {file_name}: "
                    f"expected {expected_hash}, found {actual_hash}."
                )
            shutil.copy2(source_pbix, pbix_assets / file_name)
            raw_url = f"{RAW_ROOT}/assets/pbix/{file_name}"
            asset_lines.append(
                f"| `{file_name}` | [Download]({raw_url}) | `{actual_hash}` |"
            )
        write_text(pbix_assets / "README.md", "\n".join(asset_lines) + "\n")

        docs = target / "documentation"
        canonical_pdf.parent.mkdir(parents=True)
        canonical_pdf.write_bytes(workshop_pdf_bytes)
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
            f"- [Fabric Data Agent Workshop L400]"
            f"({LAB_PDF_NAME.replace(' ', '%20')})\n",
        )

        for source_name, (folder_name, display_name) in NOTEBOOKS.items():
            convert_notebook(
                source / "notebooks" / source_name,
                workspace / folder_name,
                display_name,
            )
        build_getting_started(workspace / "DataAgentGettingStarted.Notebook")
        build_install_workshop_assets(
            target / "tools" / "templates" / "InstallWorkshopAssets.notebook-content.py",
            workspace / "InstallWorkshopAssets.Notebook",
        )
        build_refresh_semantic_model(
            target / "tools" / "templates" / "RefreshSemanticModel.notebook-content.py",
            workspace / "RefreshSemanticModel.Notebook",
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
