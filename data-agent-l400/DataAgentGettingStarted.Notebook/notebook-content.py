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
# **[Open the Fabric Data Agent Workshop lab instructions (PDF)](https://raw.githubusercontent.com/pawarbi/fda-l400/v0.1.5-test/documentation/lab-instructions/Fabric%20Data%20Agent%20Workshop%20Labs%20-%20Aug%202026.pdf)**
#
# [Browse the lab-instructions folder](https://github.com/pawarbi/fda-l400/tree/v0.1.5-test/documentation/lab-instructions)
#
# The lab instructions remain the primary workshop guide.

# MARKDOWN ********************

# ## Required setup after installation
#
# Complete this exact sequence:
#
# 1. Open `DataAgentGettingStarted`.
# 2. Open and read `documentation/lab-instructions` using the tagged GitHub links
#    above.
# 3. In the same workspace, open `InstallWorkshopAssets` and select **Run all**.
# 4. Wait for the explicit success message confirming both PBIX imports before
#    opening reports or creating the Data Agent.
# 5. Continue with the `ManufacturingOps` and `ManufacturingOpsAIReady`
#    report/model comparison.
# 6. Create the base Data Agent and continue through the workshop lab notebooks
#    in the order specified by the lab instructions.
#
# `InstallWorkshopAssets` is **required once after installation**. It uses
# `CreateOrOverwrite`, so it can also replace same-named empty Git-deployed
# reports and semantic models from an older `v0.1.3-test` installation. The
# imported PBIX files contain cached data and do not require a refresh for the
# labs.

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
