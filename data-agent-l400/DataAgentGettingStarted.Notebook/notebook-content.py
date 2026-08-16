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
# | Notebook | `RefreshSemanticModel` | Optional Web connection binding/rebinding and model refresh |
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

# ## Start with the lab instructions
#
# **[Open the Fabric Data Agent Workshop lab instructions (PDF)](https://raw.githubusercontent.com/pawarbi/fda-l400/v0.1.3-test/documentation/lab-instructions/Fabric%20Data%20Agent%20Workshop%20Labs%20-%20Aug%202026.pdf)**
#
# [Browse the lab-instructions folder](https://github.com/pawarbi/fda-l400/tree/v0.1.3-test/documentation/lab-instructions)
#
# Complete the workshop in this order:
#
# 1. Read `DataAgentGettingStarted`.
# 2. Open and follow the lab instructions linked above.
# 3. Compare the `ManufacturingOps` and `ManufacturingOpsAIReady` reports/models.
# 4. Create the base Data Agent as directed by the lab.
# 5. Run the lab notebooks in the order specified by the instructions.

# MARKDOWN ********************

# ## Optional maintenance
#
# `RefreshSemanticModel` can bind or rebind the anonymous public Web connection
# and refresh both semantic models with the latest source data. Skip it when
# `ManufacturingOps` and `ManufacturingOpsAIReady` already open and query
# successfully. It does not create or configure a Fabric Data Agent.
