# Getting Started with Data Agents

## Install from GitHub

```python
import fabric_jumpstart as jumpstart

jumpstart._install_from_github(
    logical_id="getting-started-data-agents",
    repo_url="https://github.com/pawarbi/fda-l400",
    repo_ref="v1.0.2",
    workspace_path="getting-started-data-agents",
    entry_point="SetupDataAgentJumpstart.Notebook",
    items_in_scope=["Notebook"],
)
```

`workspace_id` is intentionally omitted so installation targets the current
Fabric workspace. To target another workspace, pass its actual valid GUID.

The recommended install deploys six notebooks only. It intentionally does not
deploy the Git/TMDL semantic model and report definitions.

After installation:

1. Open the `SetupDataAgentJumpstart` entry notebook.
2. Review its parameter cell, keep the tested defaults unless using another
   immutable source release, and select **Run all**.
3. Wait for explicit success confirming both PBIX imports, that all returned
   reports and semantic models were moved into the same `getting-started-data-agents`
   folder as the notebooks, and that both semantic models returned exactly two
   rows for the populated-data DAX validation.
4. Only then continue with report/model comparison and the workshop lab
   notebooks.

`SetupDataAgentJumpstart` is required once. It imports populated PBIX files using
`CreateOrOverwrite`, so rerunning it safely replaces the same-named items.
Cached imported data is immediately available for the labs.
`RefreshSemanticModel` is optional maintenance and is not required for the lab;
use it only for a future data update or connection repair/rebinding.

The folder move uses the Fabric Core `bulkMove` API and requires Contributor or
higher workspace role plus delegated `Workspace.ReadWrite.All`. If moving fails,
the imports may remain at workspace root; `SetupDataAgentJumpstart` reports the
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

- `getting-started-data-agents/`: Fabric Git definitions; the recommended Jumpstart install
  deploys only the `.Notebook` items.
- `assets/pbix/`: canonical populated PBIX files imported by
  `SetupDataAgentJumpstart`.
- `documentation/`: GitHub-only workshop and lab documentation.
- `data/`: GitHub-only source data consumed by models and notebooks.
- `eval/`: GitHub-only evaluation and calibration workbooks.

The semantic model/report Git folders remain for reference, but the recommended
`items_in_scope=["Notebook"]` install does not deploy them.
