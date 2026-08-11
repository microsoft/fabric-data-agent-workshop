# Fabric Data Agent L400 Jumpstart

Temporary source repository for testing the Fabric Data Agent L400 workshop as
a Fabric Community Jumpstart.

## Install from a test registry

```python
import fabric_jumpstart as jumpstart

jumpstart.install(
    "data-agent-l400",
    workspace_id="<fabric-workspace-id>",
)
```

Open `WorkshopStart` after installation and run it from top to bottom.

## Repository layout

- `data-agent-l400/` - Fabric Git item definitions deployed by Jumpstart
- `data/` - manufacturing source data used by both semantic models and notebooks
- `eval/` - evaluation and judge-calibration workbooks
- `lab-instructions/` - supporting workshop PDF

The serialized Fabric items are generated from the workshop PBIX and IPYNB
assets. The existing `data-agent-L400-workshop` repository remains unchanged.
