# Fabric Data Agent L400 Jumpstart

## Fabric Data Agent resources

| Resource | Description |
| --- | --- |
| [Instructions Please](https://pawarbi.github.io/instructions-please/) | Interactive game for learning where Fabric Data Agent instructions belong. |
| [Data Agent Inspector](https://data-agent-inspector.streamlit.app/) | Inspect and understand Fabric data agent behavior. |
| [Fabric Data Agent Hub](https://fabricdatagent.com/) | Central hub for Fabric data agent resources. |
| [RANCH](https://data-agent-ranch.streamlit.app/) | Migrate implementations from the Assistants API to the Responses API. |
| [HALO](https://github.com/pawarbi/data-agent-halo) | Fabric data agent tooling and resources. |
| [AXIS](https://pawarbi-axis-fabric-data-agent.hf.space/) | Fabric data agent experience hosted on Hugging Face Spaces. |

## Install from GitHub

```python
import fabric_jumpstart as jumpstart

jumpstart._install_from_github(
    logical_id="data-agent-l400",
    repo_url="https://github.com/pawarbi/fda-l400",
    repo_ref="v1.0.1",
    workspace_path="data-agent-l400",
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
2. Open the immutable workshop-version authoritative PDF:
   [Fabric Data Agent Workshop L400](https://raw.githubusercontent.com/pawarbi/fda-l400/v1.0.1/documentation/lab-instructions/Fabric%20Data%20Agent%20Workshop%20L400.pdf).
   An [optional Markdown quick-reference companion](https://github.com/pawarbi/fda-l400/blob/v1.0.1/documentation/lab-instructions/data-agent-lab-instructions.md)
   is available on GitHub; it is not a replacement for the PDF.
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

- `data-agent-l400/`: Fabric Git definitions; the recommended Jumpstart install
  deploys only the `.Notebook` items.
- `assets/pbix/`: canonical populated PBIX files imported by
  `InstallWorkshopAssets`.
- `documentation/`: GitHub-only workshop and lab documentation.
- `data/`: GitHub-only source data consumed by models and notebooks.
- `eval/`: GitHub-only evaluation and calibration workbooks.

The semantic model/report Git folders remain for reference, but the recommended
`items_in_scope=["Notebook"]` install does not deploy them.
