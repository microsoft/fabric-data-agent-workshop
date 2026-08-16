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

# # L400 - Create a multi-source Data Agent
#
# This notebook preserves the existing lab Data Agent and creates a new agent whose name ends in
# `_MultiSource`. It:
#
# 1. Confirms the base Data Agent, semantic model, and `OpsRefData` Lakehouse exist.
# 2. Creates or reuses `<base-agent-name>_MultiSource`.
# 3. Adds and configures the semantic model and Lakehouse.
# 4. Selects the operational model tables and curated `fda` objects.
# 5. Adds descriptions, query instructions, examples, and cross-source routing rules.
# 6. Optionally publishes the multi-source agent.
#
# Run `BuildOpsRefData` first.

# MARKDOWN ********************

# ## Step 0 - Install the supported SDK version

# CELL ********************

%pip install -q "fabric-data-agent-sdk==0.1.28a0" "mcp==1.23.3"

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## Step 1 - Parameters
#
# Lab users normally change only `BASE_DATA_AGENT_NAME`. The new agent name is derived automatically.
# All artifacts must be in the same workspace as this notebook.

# CELL ********************

BASE_DATA_AGENT_NAME = "MfgOps_DA_AIReady_SAP"
MULTI_SOURCE_AGENT_NAME = f"{BASE_DATA_AGENT_NAME}_MultiSource"
SEMANTIC_MODEL_NAME = "ManufacturingOpsAIReady"
LAKEHOUSE_NAME = "OpsRefData"
PUBLISH_CHANGES = True

SEMANTIC_MODEL_TABLES = [
    "Assets",
    "Business Measures",
    "Date",
    "Inventory",
    "Lines",
    "Plants",
    "ProductionLog",
    "Products",
]

LAKEHOUSE_OBJECTS = [
    "Downtime_Reasons",
    "Sales_Orders",
    "Downtime_By_Line_Type",
]

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## Step 2 - Confirm the required Fabric items

# CELL ********************

import time
import pandas as pd
import sempy.fabric as fabric
import notebookutils
from fabric.dataagent.client import create_data_agent

workspace_id = fabric.get_notebook_workspace_id()
items = fabric.list_items(workspace=workspace_id)


def require_item(display_name, item_types):
    match = items[
        (items["Display Name"] == display_name)
        & (items["Type"].isin(item_types))
    ]
    assert not match.empty, (
        f"Required item '{display_name}' was not found as {sorted(item_types)} "
        f"in the current workspace."
    )
    return str(match.iloc[0]["Id"])


base_data_agent_id = require_item(
    BASE_DATA_AGENT_NAME,
    {"DataAgent", "AISkill"},
)
require_item(SEMANTIC_MODEL_NAME, {"SemanticModel"})
require_item(LAKEHOUSE_NAME, {"Lakehouse"})

da = create_data_agent(
    MULTI_SOURCE_AGENT_NAME,
    workspace_id=workspace_id,
)
print(
    "Base Data Agent preserved:",
    BASE_DATA_AGENT_NAME,
    "->",
    base_data_agent_id,
)
print("Multi-source Data Agent:", MULTI_SOURCE_AGENT_NAME)
print("Semantic model:", SEMANTIC_MODEL_NAME)
print("Lakehouse:", LAKEHOUSE_NAME)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## Step 3 - Public staging API helpers

# CELL ********************

LEAF_HINTS = ("column", "measure", "parameter", "returnvalue")


def element_name(element):
    return element.get("displayName") or element.get("name")


def is_leaf(element):
    element_type = str(element.get("type", "")).lower()
    return any(hint in element_type for hint in LEAF_HINTS)


def datasource_name(datasource):
    configuration = datasource.get_configuration(stage="staging")
    return (
        configuration.get("displayName")
        or configuration.get("display_name")
    )


def resolve_datasource(name):
    for datasource in da.list_datasources(stage="staging"):
        if datasource_name(datasource) == name:
            return datasource
    return None


def ensure_datasource(name):
    datasource = resolve_datasource(name)
    if datasource is not None:
        return datasource

    da.add_staging_datasource(
        name,
        workspace_id_or_name=workspace_id,
    )
    for _ in range(30):
        time.sleep(3)
        datasource = resolve_datasource(name)
        if datasource is not None:
            return datasource
    raise RuntimeError(f"Datasource '{name}' did not appear in staging.")


def children(datasource, root_id):
    values = []
    token = None
    while True:
        response = datasource.get_elements(
            stage="staging",
            root_id=root_id,
            continuation_token=token,
        )
        values.extend(response.get("value", []))
        token = response.get("continuationToken")
        if not token:
            return values


def walk(datasource, root_id=None, prefix=()):
    for element in children(datasource, root_id):
        path = prefix + (element_name(element),)
        yield path, element
        if not is_leaf(element):
            yield from walk(datasource, element["id"], path)


def select_by_name(datasource, names):
    selected = set()
    for _, element in walk(datasource):
        name = element_name(element)
        if name in names and not is_leaf(element):
            datasource.update_element(
                element["id"],
                is_selected=True,
            )
            selected.add(name)
    missing = set(names) - selected
    assert not missing, f"Lakehouse objects not found: {sorted(missing)}"
    return sorted(selected)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## Step 4 - Add and configure the semantic-model datasource

# CELL ********************

semantic_model_source = ensure_datasource(SEMANTIC_MODEL_NAME)
selected_model_tables = select_by_name(
    semantic_model_source,
    SEMANTIC_MODEL_TABLES,
)
print("Selected semantic-model tables:", selected_model_tables)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## Step 5 - Add and configure the Lakehouse datasource

# CELL ********************

lakehouse_source = ensure_datasource(LAKEHOUSE_NAME)
selected = select_by_name(lakehouse_source, LAKEHOUSE_OBJECTS)
print("Selected Lakehouse objects:", selected)

LAKEHOUSE_DESCRIPTION = (
    "Curated manufacturing reference data for downtime root-cause analysis "
    "and product sales analysis. The fda views expose friendly, agent-ready "
    "columns and exclude future-dated records."
)

LAKEHOUSE_INSTRUCTIONS = '''
## Purpose
- Use this Lakehouse for downtime reasons/root causes and for sales analysis.
- Query only the fda schema objects selected for this Data Agent.

## Routing within this source
- Use fda.Downtime_Reasons when the question asks why downtime occurred, asks
  for reason categories, or requests a breakdown by reason, line, shift, plant,
  or line type.
- Use fda.Downtime_By_Line_Type when a question supplies one line type and asks
  for its downtime-reason breakdown across all available history.
- Use fda.Downtime_Reasons instead of the function whenever the answer requires
  a date filter, including the default latest-30-day period.
- Use fda.Sales_Orders for sales, units sold, revenue, cost, or margin by
  product, category, plant, region, or time period.

## Data dictionary
- fda.Downtime_Reasons contains one row per Date, Line Name, Shift, and Reason
  Category. Downtime Minutes is additive and represents minutes attributed to
  the root cause. Plant Name and Line Type support operational grouping.
- fda.Sales_Orders contains monthly product and plant sales facts. Order Date
  is the first day of the sales month. Units Sold, Revenue, Cost, and Margin
  are additive. Unit Price is a per-unit value and is not total revenue.
- Product Name and Category identify the sold product. Plant Name and Region
  identify where the sale is attributed.
- fda.Downtime_By_Line_Type returns an all-history aggregation of Reason
  Category and Downtime Minutes for one line type. It has no Date column.

## Query rules
- The views already exclude future dates.
- When no sales period is specified, use the latest 30 days ending on
  MAX([Order Date]) in fda.Sales_Orders and state both dates.
- When no downtime period is specified, use the latest 30 days ending on
  MAX([Date]) in fda.Downtime_Reasons and state both dates.
- For "this year", use January 1 of the year containing the source's maximum
  available date through that maximum date.
- For an explicit period, use the requested start and end dates.
- Aggregate Revenue with SUM([Revenue]), Units Sold with SUM([Units Sold]),
  Cost with SUM([Cost]), and Margin with SUM([Margin]).
- Calculate margin percentage as
  100.0 * SUM([Margin]) / NULLIF(SUM([Revenue]), 0).
- Never use Unit Price as revenue and never average row-level percentages to
  calculate an overall percentage.
- Use bracketed friendly column names exactly as exposed by the fda views.
- Return concise results and include the applied time period.

## Joining the two views
- Join fda.Downtime_Reasons and fda.Sales_Orders only when the question needs a
  plant-level relationship between downtime and sales.
- Never join the detail rows directly because their grains differ.
- First aggregate each view independently to the same grain: Plant Name and
  calendar month. Convert Date to the first day of its month and join it to
  Order Date.
- Apply the same start and end dates to both CTEs before joining.
- Use an INNER JOIN for direct comparisons and a FULL OUTER JOIN only when the
  user asks to retain plants/months missing from one source.

## SQL patterns

### Default sales period
```sql
  WITH d AS (SELECT MAX([Order Date]) AS max_date FROM fda.Sales_Orders)
  ... WHERE [Order Date] BETWEEN DATEADD(day,-29,d.max_date) AND d.max_date
```

### Default downtime period
```sql
  WITH d AS (SELECT MAX([Date]) AS max_date FROM fda.Downtime_Reasons)
  ... WHERE [Date] BETWEEN DATEADD(day,-29,d.max_date) AND d.max_date
```

### Downtime function
```sql
  SELECT [Reason Category], [Downtime Minutes]
  FROM fda.Downtime_By_Line_Type('Assembly')
  ORDER BY [Downtime Minutes] DESC
```

### Safe monthly join
```sql
  WITH downtime AS (
      SELECT [Plant Name],
             DATEFROMPARTS(YEAR([Date]),MONTH([Date]),1) AS month_start,
             SUM([Downtime Minutes]) AS downtime_minutes
      FROM fda.Downtime_Reasons
      WHERE [Date] BETWEEN @start_date AND @end_date
      GROUP BY [Plant Name], DATEFROMPARTS(YEAR([Date]),MONTH([Date]),1)
  ),
  sales AS (
      SELECT [Plant Name], [Order Date] AS month_start,
             SUM([Revenue]) AS revenue
      FROM fda.Sales_Orders
      WHERE [Order Date] BETWEEN @start_date AND @end_date
      GROUP BY [Plant Name], [Order Date]
  )
  SELECT ... FROM downtime d JOIN sales s
    ON d.[Plant Name]=s.[Plant Name] AND d.month_start=s.month_start
```
'''

lakehouse_source.update_configuration(
    description=LAKEHOUSE_DESCRIPTION,
    instructions=LAKEHOUSE_INSTRUCTIONS,
)
print("Updated Lakehouse description and instructions.")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## Step 6 - Review the Lakehouse datasource guidance

# CELL ********************

lakehouse_configuration = lakehouse_source.get_configuration(stage="staging")
print("Lakehouse description:")
print(lakehouse_configuration.get("description"))
print("\nLakehouse instructions:")
print(lakehouse_configuration.get("instructions"))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## Step 7 - Add idempotent example queries

# CELL ********************

EXAMPLE_QUERIES = {
    "Why was downtime highest for Assembly lines in the latest 30 days?":
        "WITH d AS (SELECT MAX([Date]) AS max_date FROM fda.Downtime_Reasons) "
        "SELECT [Reason Category], "
        "SUM([Downtime Minutes]) AS [Downtime Minutes] "
        "FROM fda.Downtime_Reasons CROSS JOIN d "
        "WHERE [Line Type] = 'Assembly' "
        "AND [Date] BETWEEN DATEADD(day,-29,d.max_date) AND d.max_date "
        "GROUP BY [Reason Category] ORDER BY [Downtime Minutes] DESC;",
    "Across all available history, what is the downtime-reason breakdown for Assembly lines?":
        "SELECT [Reason Category], [Downtime Minutes] "
        "FROM fda.Downtime_By_Line_Type('Assembly') "
        "ORDER BY [Downtime Minutes] DESC;",
    "Which product had the highest sales?":
        "WITH d AS (SELECT MAX([Order Date]) AS max_date FROM fda.Sales_Orders) "
        "SELECT TOP 1 [Product Name], SUM([Revenue]) AS [Revenue] "
        "FROM fda.Sales_Orders CROSS JOIN d "
        "WHERE [Order Date] BETWEEN DATEADD(day,-29,d.max_date) AND d.max_date "
        "GROUP BY [Product Name] ORDER BY [Revenue] DESC;",
    "What is revenue by product category this year?":
        "WITH d AS (SELECT MAX([Order Date]) AS max_date FROM fda.Sales_Orders) "
        "SELECT [Category], SUM([Revenue]) AS [Revenue] "
        "FROM fda.Sales_Orders CROSS JOIN d "
        "WHERE YEAR([Order Date]) = YEAR(d.max_date) "
        "GROUP BY [Category] ORDER BY [Revenue] DESC;",
    "Which plant has the highest sales margin this year?":
        "WITH d AS (SELECT MAX([Order Date]) AS max_date FROM fda.Sales_Orders) "
        "SELECT TOP 1 [Plant Name], SUM([Margin]) AS [Margin] "
        "FROM fda.Sales_Orders CROSS JOIN d "
        "WHERE YEAR([Order Date]) = YEAR(d.max_date) "
        "GROUP BY [Plant Name] ORDER BY [Margin] DESC;",
}

existing_fewshots = lakehouse_source.get_fewshots(stage="staging")
question_column = next(
    (
        column
        for column in existing_fewshots.columns
        if str(column).lower() == "question"
    ),
    None,
)
existing_questions = (
    set(existing_fewshots[question_column].astype(str))
    if question_column is not None
    else set()
)
missing_examples = {
    question: query
    for question, query in EXAMPLE_QUERIES.items()
    if question not in existing_questions
}

if missing_examples:
    lakehouse_source.add_fewshots(missing_examples)
    print("Added examples:", list(missing_examples))
else:
    print("All examples already exist; nothing added.")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## Step 8 - Replace the Data Agent instructions

# CELL ********************

AGENT_INSTRUCTIONS = '''
## Role and scope
You answer manufacturing operations and product sales questions using only the
configured semantic model and OpsRefData Lakehouse.

## Routing
1. Use the ManufacturingOpsAIReady semantic model for production quantity,
   OEE, scrap rate, production yield, downtime minutes, inventory, assets,
   plants, manufacturing lines, and operational product performance.
2. Use the OpsRefData Lakehouse for:
   - downtime reasons or root-cause questions asking why downtime occurred;
   - sales, units sold, revenue, cost, or margin questions.
3. If a question asks for downtime quantity and its causes, use the semantic
   model for downtime minutes and OpsRefData for the reason breakdown. Clearly
   distinguish the two results.
4. Do not use semantic-model product prices as sales revenue. Sales facts come
   only from OpsRefData.

## Time periods
- For manufacturing questions without a period, use the latest 30 days ending
  on the latest production date and state the period.
- For sales questions without a period, use the latest 30 days ending on the
  maximum Order Date in OpsRefData and state the period.
- Interpret "this year" as the year containing the latest available date in
  the selected source.

## Cross-source period alignment
- When one answer combines the semantic model and OpsRefData, do not independently
  use each source's default period.
- First determine the latest production date from the semantic model and the
  latest relevant Lakehouse date.
- Use the earlier of those dates as the common end date so both sources have
  data for the complete comparison period.
- If no period was requested, apply the same 30-day window ending on that common
  end date to both sources.
- If "this year" was requested, use January 1 of the common end-date year through
  the common end date for both sources.
- If an explicit period was requested, apply exactly that period to both sources
  and disclose any source that lacks complete coverage.
- State the shared period once in the final answer.

## Response rules
- Answer in concise text or a compact table unless the user explicitly asks
  for a visual.
- Use two decimal places for percentages and currency values.
- State the measure, applied filters, and time period.
- Preserve requested groupings and rankings; do not omit returned groups.
- If data is missing or ambiguous, explain the limitation or ask a clarifying
  question rather than fabricating an answer.

## Out of scope
- Customer-level data, vendors, purchasing, purchase orders, and employee data
  remain out of scope because those sources are not configured.
- For an out-of-scope request, respond: "This question is out of scope of this
  agent, please ask manufacturing Ops or product sales related questions."
'''

da.update_settings(ai_instructions=AGENT_INSTRUCTIONS)
print("Updated agent routing and response instructions.")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## Step 9 - Review and publish

# CELL ********************

print("Staging datasources:")
for datasource in da.list_datasources(stage="staging"):
    print("-", datasource_name(datasource))

settings = da.get_settings(stage="staging")
print("Staging instructions updated:", bool(settings.get("aiInstructions")))

if PUBLISH_CHANGES:
    da.publish_staging(
        description=(
            "Added OpsRefData for downtime root causes and product sales; "
            "updated routing, datasource guidance, examples, and period alignment."
        )
    )
    print("Published the updated Data Agent configuration.")
else:
    print("PUBLISH_CHANGES is False; review staging in the UI before publishing.")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## Step 10 - Query the published agent through MCP
#
# The MCP endpoint is available only after the agent is published. The client follows the official
# MCP flow: initialize, discover the advertised tool, determine its question argument, and call it.
# The notebook obtains a Fabric token through `notebookutils.credentials.getToken("pbi")`.

# CELL ********************

import asyncio
from concurrent.futures import ThreadPoolExecutor

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

data_agent_id = fabric.get_item(MULTI_SOURCE_AGENT_NAME)["Id"].max()
mcp_url = (
    f"https://api.fabric.microsoft.com/v1/mcp/workspaces/{workspace_id}"
    f"/dataagents/{data_agent_id}/agent"
)

print("Published Data Agent ID:", data_agent_id)
print("MCP endpoint:", mcp_url)


def get_mcp_headers():
    token = notebookutils.credentials.getToken("pbi")
    return {"Authorization": f"Bearer {token}"}


async def query_agent_questions(questions):
    rows = []
    async with streamablehttp_client(
        mcp_url,
        headers=get_mcp_headers(),
    ) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert tools.tools, "The MCP server advertised no tools."
            tool = tools.tools[0]
            question_arg = next(
                iter(tool.inputSchema["properties"])
            )

            for test_name, question in questions:
                result = await session.call_tool(
                    tool.name,
                    {question_arg: question},
                )
                answer = "\n".join(
                    block.text
                    for block in result.content
                    if getattr(block, "type", None) == "text"
                )
                rows.append(
                    {
                        "test": test_name,
                        "question": question,
                        "answer": answer,
                        "is_error": bool(result.isError),
                    }
                )
    return rows


MCP_TEST_QUESTIONS = [
    (
        "semantic_model",
        "What was the scrap rate in the latest 30 days?",
    ),
    (
        "lakehouse",
        "Which product had the highest sales?",
    ),
    (
        "combined_sources",
        "Which line had the most downtime minutes, and what were its leading "
        "downtime reasons, using the same latest 30-day period?",
    ),
    (
        "table_valued_function",
        "Across all available history, what is the downtime-reason breakdown "
        "for Assembly lines?",
    ),
]


def run_mcp_tests():
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(
            lambda: asyncio.run(
                query_agent_questions(MCP_TEST_QUESTIONS)
            )
        ).result()


mcp_results = pd.DataFrame(run_mcp_tests())
display(mcp_results)
assert not mcp_results["is_error"].any(), (
    "One or more MCP tool calls returned an error."
)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

display(mcp_results)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

notebookutils.session.stop()

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }
