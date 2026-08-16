# Fabric Data Agent L400 Jumpstart

Generated from `data-agent-L400-workshop` commit `0efe648`.

## Direct pre-registration installation

```python
import fabric_jumpstart as jumpstart

jumpstart._install_from_github(
    logical_id="data-agent-l400",
    repo_url="https://github.com/pawarbi/fda-l400",
    repo_ref="v0.1.2-test",
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

After installation, open `DataAgentGettingStarted`, then run `DataAgentSetup`
when directed to bind the public Web source and refresh both semantic models.

## Repository layout

- `data-agent-l400/`: Fabric workspace items deployed by Jumpstart.
- `documentation/`: GitHub-only workshop and lab documentation.
- `data/`: GitHub-only source data consumed by models and notebooks.
- `eval/`: GitHub-only evaluation and calibration workbooks.
- `tools/`: local rebuild tooling; not deployed to Fabric.

The source workshop repository remains unchanged. PBIX models are freshly
serialized with pbi-tools during rebuild; report and Copilot assets come
directly from the latest PBIX packages.
