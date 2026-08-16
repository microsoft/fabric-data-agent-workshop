# Fabric Data Agent L400 Jumpstart

Generated from `data-agent-L400-workshop` commit `0efe648`.

## Direct pre-registration installation

```python
import fabric_jumpstart as jumpstart

jumpstart._install_from_github(
    logical_id="data-agent-l400",
    repo_url="https://github.com/pawarbi/fda-l400",
    repo_ref="v0.1.6-test",
    workspace_path=".",
    entry_point="DataAgentGettingStarted.Notebook",
    items_in_scope=["Notebook"],
)
```

`_install_from_github` is an underscore API for pre-registration testing.
`workspace_id` is intentionally omitted so installation targets the current
Fabric workspace. To target another workspace, pass its actual valid GUID.

## Registered installation (later)

```python
import fabric_jumpstart as jumpstart

jumpstart.install("data-agent-l400")
```

This command will work only after the Jumpstart is registered. Until then, use
the direct pre-registration installation shown above. Any future registry
configuration for this Jumpstart must scope deployment to `Notebook` items only.

The recommended install deploys seven notebooks only. It intentionally does not
deploy the Git/TMDL semantic model and report definitions.

After installation:

1. Open `DataAgentGettingStarted`.
2. Open and read the tagged `documentation/lab-instructions` links.
3. In the same workspace, open `InstallWorkshopAssets` and select **Run all**.
4. Wait for explicit success confirming both PBIX imports and that all returned
   reports and semantic models were moved into the same `data-agent-l400`
   folder as the notebooks.
5. Only then continue with report/model comparison and the workshop lab
   notebooks.

`InstallWorkshopAssets` is required once. It imports populated PBIX files using
`CreateOrOverwrite`, including replacement of same-named empty items from an
older `v0.1.3-test` installation. Cached imported data is immediately available
for the labs. `RefreshSemanticModel` is optional maintenance and is not required
for the lab; use it only for a future data update or connection repair/rebinding.

The folder move uses the Fabric Core `bulkMove` API and requires Contributor or
higher workspace role plus delegated `Workspace.ReadWrite.All`. If moving fails,
the imports may remain at workspace root; `InstallWorkshopAssets` reports the
API error and does not print final success.

## Repository layout

- `data-agent-l400/`: Fabric Git definitions; the recommended Jumpstart install
  deploys only the `.Notebook` items.
- `assets/pbix/`: canonical populated PBIX files imported by
  `InstallWorkshopAssets`.
- `documentation/`: GitHub-only workshop and lab documentation.
- `data/`: GitHub-only source data consumed by models and notebooks.
- `eval/`: GitHub-only evaluation and calibration workbooks.
- `tools/`: local rebuild tooling; not deployed to Fabric.

The semantic model/report Git folders remain for reproducibility and reference,
but the recommended `items_in_scope=["Notebook"]` install does not deploy them.
The source workshop repository remains unchanged. PBIX models are freshly
serialized with pbi-tools during rebuild; report and Copilot assets come
directly from the latest PBIX packages.
