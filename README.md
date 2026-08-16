# Fabric Data Agent L400 Jumpstart

Generated from `data-agent-L400-workshop` commit `0efe648`.

## Direct pre-registration installation

```python
import fabric_jumpstart as jumpstart

jumpstart._install_from_github(
    logical_id="data-agent-l400",
    repo_url="https://github.com/pawarbi/fda-l400",
    repo_ref="v0.1.4-test",
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

jumpstart.install("data-agent-l400")
```

This command will work only after the Jumpstart is registered. Until then, use
the direct pre-registration installation shown above.

After installation, read `DataAgentGettingStarted` and open the linked lab
instructions. On a fresh Jumpstart installation, run all cells in
`RefreshSemanticModel` once and wait for both semantic model refreshes to
complete before opening or comparing reports or creating the Data Agent.

Jumpstart deploys Git/TMDL definitions, which do not contain imported VertiPaq
data. The required first run binds or reuses the anonymous public Web connection
and hydrates both semantic models. After a successful first refresh, rerunning
is optional and is used only to update data or repair/rebind the connection.
`RefreshSemanticModel` does not create or configure a Data Agent.

## Repository layout

- `data-agent-l400/`: Fabric workspace items deployed by Jumpstart.
- `documentation/`: GitHub-only workshop and lab documentation.
- `data/`: GitHub-only source data consumed by models and notebooks.
- `eval/`: GitHub-only evaluation and calibration workbooks.
- `tools/`: local rebuild tooling; not deployed to Fabric.

The source workshop repository remains unchanged. PBIX models are freshly
serialized with pbi-tools during rebuild; report and Copilot assets come
directly from the latest PBIX packages.
