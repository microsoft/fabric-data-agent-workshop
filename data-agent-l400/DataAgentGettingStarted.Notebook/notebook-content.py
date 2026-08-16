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
# - Install all Jumpstart items into the same Fabric workspace.
# - Use a capacity and tenant with notebooks, semantic models, reports, Data
#   Agents, Lakehouses, and MLflow available.
# - Confirm you can create workspace items and Fabric connections.
# - Confirm outbound access to public `raw.githubusercontent.com` content.
# - Keep installed item names unchanged so notebook discovery succeeds.
# - Have permission to create and publish a Fabric Data Agent.

# MARKDOWN ********************

# ## Exact installed item inventory
#
# | Type | Installed item | Purpose |
# | --- | --- | --- |
# | Notebook | `DataAgentGettingStarted` | Orientation and navigation |
# | Notebook | `DataAgentSetup` | Connection binding and model refresh |
# | Notebook | `BuildOpsRefData` | Builds the `OpsRefData` Lakehouse assets |
# | Notebook | `CreateMultiSourceDataAgent` | Adds the Lakehouse source and publishes the multi-source agent |
# | Notebook | `JudgeCalibration` | Calibrates and registers the LLM judge |
# | Notebook | `EvaluateDataAgent` | Runs the evaluation workflow |
# | Semantic model | `ManufacturingOps` | Baseline model |
# | Semantic model | `ManufacturingOpsAIReady` | AI-ready model |
# | Report | `ManufacturingOps` | Baseline report |
# | Report | `ManufacturingOpsAIReady` | AI-ready report |
#
# Data Agents are intentionally not installed. Creating them is part of the lab.

# MARKDOWN ********************

# ## Documentation and lab order
#
# - [Workshop documentation](https://github.com/pawarbi/fda-l400/tree/v0.1.2-test/documentation)
# - [Lab instructions](https://github.com/pawarbi/fda-l400/tree/v0.1.2-test/documentation/lab-instructions)
#
# Complete the workshop in this order:
#
# 1. Read `DataAgentGettingStarted`.
# 2. Run `DataAgentSetup`.
# 3. Compare the `ManufacturingOps` and `ManufacturingOpsAIReady` reports/models.
# 4. Create `MfgOps_DA_AIReady_SAP` over `ManufacturingOpsAIReady`.
# 5. Run `BuildOpsRefData`.
# 6. Run `CreateMultiSourceDataAgent`.
# 7. Run `JudgeCalibration`.
# 8. Run `EvaluateDataAgent`.

# MARKDOWN ********************

# ## Next step
#
# Open `DataAgentSetup` and run every cell. Wait for both semantic-model
# refreshes to complete before continuing with the lab.
