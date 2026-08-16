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

# # DataAgentGettingStarted - Fabric Data Agent L400 Workshop
#
# Welcome to the Fabric Data Agent L400 Jumpstart. This orientation notebook
# explains what was installed, how the workshop components fit together, and
# the order in which to complete the lab.
#
# This notebook is documentation-only. It does not create connections, refresh
# semantic models, create Fabric items, or otherwise change your environment.
#
# ## Learning objectives
#
# 1. Compare a baseline semantic model with an AI-ready semantic model.
# 2. Create and configure a governed Fabric Data Agent.
# 3. Extend the agent with a Lakehouse source for multi-source reasoning.
# 4. Define evaluation questions and live DAX ground truth.
# 5. Calibrate an LLM judge and track quality and failure modes with MLflow.

# MARKDOWN ********************

# ## Architecture
#
# `GitHub data -> anonymous Web connection -> semantic models -> reports`
#
# `ManufacturingOpsAIReady -> base Data Agent -> OpsRefData Lakehouse`
#
# `Base Data Agent + OpsRefData -> multi-source Data Agent -> evaluation + MLflow`

# MARKDOWN ********************

# ## Prerequisites
#
# - Install all recommended Jumpstart notebook items into the same Fabric workspace.
# - Use a capacity and tenant with notebooks, semantic models, reports, Data
#   Agents, Lakehouses, and MLflow available.
# - Confirm you can create workspace items and Fabric connections.
# - Confirm outbound access to public `raw.githubusercontent.com` content.
# - Keep installed item names unchanged so notebook discovery succeeds.
# - Have permission to create and publish a Fabric Data Agent.

# MARKDOWN ********************

# ## Notebook-only Jumpstart inventory
#
# The recommended Jumpstart installation deploys these seven notebook items only:
#
# | Installed notebook | Purpose |
# | --- | --- |
# | `DataAgentGettingStarted` | Orientation, setup sequence, and navigation |
# | `InstallWorkshopAssets` | **Required once after installation:** imports both populated workshop PBIX files |
# | `RefreshSemanticModel` | **Optional maintenance; not required for the lab** |
# | `BuildOpsRefData` | Builds the `OpsRefData` Lakehouse assets |
# | `CreateMultiSourceDataAgent` | Adds the Lakehouse source and publishes the multi-source agent |
# | `JudgeCalibration` | Calibrates and registers the LLM judge |
# | `EvaluateDataAgent` | Runs the evaluation workflow |
#
# `InstallWorkshopAssets` creates or overwrites these populated Power BI items:
#
# | Type | Created item | Purpose |
# | --- | --- | --- |
# | Semantic model | `ManufacturingOps` | Baseline model |
# | Semantic model | `ManufacturingOpsAIReady` | AI-ready model |
# | Report | `ManufacturingOps` | Baseline report |
# | Report | `ManufacturingOpsAIReady` | AI-ready report |
#
# Data Agents are intentionally not installed. Creating them is part of the lab.

# MARKDOWN ********************

# ## Start with the lab instructions
#
# **Authoritative instructions:** [Open the Fabric Data Agent Workshop lab instructions (PDF)](https://raw.githubusercontent.com/pawarbi/fda-l400/v1.0.1/documentation/lab-instructions/Fabric%20Data%20Agent%20Workshop%20L400.pdf)
#
# **Optional Markdown quick-reference companion:** [Read the Markdown on GitHub](https://github.com/pawarbi/fda-l400/blob/v1.0.1/documentation/lab-instructions/data-agent-lab-instructions.md)
#
# The PDF is the authoritative workshop guide and source of truth. The optional
# Markdown quick-reference companion is not a replacement for the PDF.

# MARKDOWN ********************

# ## Required setup after installation
#
# Complete this exact sequence:
#
# 1. Open `DataAgentGettingStarted`.
# 2. Open and read the lab instructions using the immutable workshop-version
#    links above.
# 3. In the same workspace, open `InstallWorkshopAssets` and select **Run all**.
# 4. Wait for the explicit success message confirming both PBIX imports, that
#    every returned report and semantic model was moved into the same
#    `data-agent-l400` folder as the notebooks, and that both semantic models
#    returned exactly two rows for the populated-data DAX validation.
# 5. Only then continue with the `ManufacturingOps` and
#    `ManufacturingOpsAIReady`
#    report/model comparison.
# 6. Create the base Data Agent and continue through the workshop lab notebooks
#    in the order specified by the lab instructions.
#
# `InstallWorkshopAssets` is **required once after installation**. It uses
# `CreateOrOverwrite`, so rerunning it safely replaces the same-named reports and
# semantic models. The imported PBIX files contain cached data and do not require
# a refresh for the labs. The folder move requires Contributor or higher
# workspace role and delegated `Workspace.ReadWrite.All`.

# MARKDOWN ********************

# ## Populated-data acceptance gate
#
# After import and folder placement, `InstallWorkshopAssets` runs this exact query
# against both `ManufacturingOps` and `ManufacturingOpsAIReady`:
#
# ```dax
# EVALUATE
#     TOPN(2, 'Customers')
# ```
#
# The notebook uses a bounded, logged retry for brief post-import availability
# delays. Each model must return exactly two rows. A query failure or different
# row count names the affected model and stops without final success.

# MARKDOWN ********************

# ## Optional maintenance
#
# `RefreshSemanticModel` can bind or rebind the anonymous public Web connection
# and refresh both semantic models with the latest source data. It is **optional
# maintenance and is not required for the lab** because `InstallWorkshopAssets`
# imports populated PBIX files with cached data.
#
# Use it only for a future data update or to repair/rebind the Web connection.
# It does not create or configure a Fabric Data Agent.
