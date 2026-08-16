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

# # L400 - Build the **OpsRefData** Lakehouse with Python and DuckDB
#
# This notebook creates or reuses a schema-enabled Lakehouse, downloads the workshop source data,
# uses DuckDB and Python to build two deterministic Delta tables without starting Spark, and creates
# curated views and a function for the Data Agent.
#
# | Object | Type | Purpose |
# |---|---|---|
# | `dbo.downtime_reasons` | Delta table | Downtime root causes by date, line, shift, plant, and reason |
# | `dbo.sales_orders` | Delta table | Monthly product sales with units, revenue, cost, and margin |
# | `fda.Downtime_Reasons` | View | Agent-facing downtime root-cause data through today |
# | `fda.Sales_Orders` | View | Agent-facing sales data through today |
# | `fda.Downtime_By_Line_Type` | Function | Parameterized downtime-reason breakdown |
#
# The `fda` objects are the supported Data Agent interface. The underlying `dbo` tables remain the
# complete Delta sources.

# MARKDOWN ********************

# ## Setup

# CELL ********************

%pip install -q duckdb pyarrow "deltalake>=1.0.0"

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

# PARAMETERS
DATA_SOURCE_REF = "v1.0.0"  # Use an immutable release tag or commit for reproducible runs.
github_base = (
    "https://raw.githubusercontent.com/pawarbi/fda-l400/"
    f"{DATA_SOURCE_REF}/data/mfg-ops-data"
)
lakehouse_name = "OpsRefData"
schema_name = "dbo"
view_schema = "fda"
downtime_table = "downtime_reasons"
sales_table = "sales_orders"

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

import time
import notebookutils
import sempy.fabric as fabric

workspace_id = fabric.get_notebook_workspace_id()


def item_name(item):
    return (
        getattr(item, "displayName", None)
        or getattr(item, "name", None)
        or (item.get("displayName") if isinstance(item, dict) else None)
        or (item.get("name") if isinstance(item, dict) else None)
    )


existing_lakehouses = {
    item_name(item)
    for item in notebookutils.lakehouse.list()
}
created_lakehouse = lakehouse_name not in existing_lakehouses

if created_lakehouse:
    print(f"Creating schema-enabled Lakehouse: {lakehouse_name}")
    notebookutils.lakehouse.create(
        name=lakehouse_name,
        definition={"enableSchemas": True},
    )

for attempt in range(1, 31):
    try:
        lakehouse = notebookutils.lakehouse.getWithProperties(lakehouse_name)
        break
    except Exception:
        if attempt == 30:
            raise
        time.sleep(5)

properties = lakehouse.properties
lakehouse_id = (
    getattr(lakehouse, "id", None)
    or properties.get("id")
    or properties.get("lakehouseId")
)
abfss = properties["abfsPath"]

if created_lakehouse:
    print("Waiting for the SQL analytics endpoint to initialize...")
    time.sleep(30)

print("Workspace:", workspace_id)
print("Lakehouse:", lakehouse_name, "->", lakehouse_id)
print("OneLake path:", abfss)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## Step 1 - Load the source CSVs with DuckDB
#
# DuckDB reads the versioned workshop files directly from GitHub into pandas DataFrames. No Spark
# session or default Lakehouse attachment is required.

# CELL ********************

import duckdb
import pandas as pd

con = duckdb.connect()
con.execute("INSTALL httpfs")
con.execute("LOAD httpfs")


def read_github_csv(name):
    url = f"{github_base}/{name}"
    escaped_url = url.replace("'", "''")
    return con.execute(
        f"SELECT * FROM read_csv_auto('{escaped_url}', header=true)"
    ).df()


production = read_github_csv("ProductionLog.csv")
lines = read_github_csv("lines.csv")
plants = read_github_csv("Plants.csv")
products = read_github_csv("PRODUCTS.csv")

production["Date"] = production["Date"].astype(str)
production["Down"] = pd.to_numeric(
    production["Down"],
    errors="raise",
).astype(int)

print(
    "ProductionLog rows:",
    len(production),
    "| total Down minutes:",
    int(production["Down"].sum()),
)
print(
    "lines:",
    len(lines),
    "| plants:",
    len(plants),
    "| products:",
    len(products),
)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## Step 2 - Generate `downtime_reasons` (deterministic, reconciles to model downtime)
#
# Each Date/line/shift's `Down` minutes are split across five reason categories using fixed per-line-type
# weights (Assembly is Equipment-Failure dominant ~45%). The split is integer-exact, so
# `SUM(downtime_minutes)` ties back to `ProductionLog.Down`.

# CELL ********************

REASON_ORDER = ["Equipment Failure", "Changeover", "Material Shortage", "Operator Error", "Planned Maintenance"]
WEIGHTS = {
    "Assembly":    {"Equipment Failure":0.45,"Changeover":0.20,"Material Shortage":0.12,"Operator Error":0.10,"Planned Maintenance":0.13},
    "Machining":   {"Changeover":0.35,"Equipment Failure":0.25,"Material Shortage":0.15,"Operator Error":0.12,"Planned Maintenance":0.13},
    "Winding":     {"Material Shortage":0.30,"Equipment Failure":0.25,"Changeover":0.20,"Operator Error":0.12,"Planned Maintenance":0.13},
    "Calibration": {"Operator Error":0.30,"Planned Maintenance":0.25,"Equipment Failure":0.20,"Changeover":0.15,"Material Shortage":0.10},
    "Test":        {"Planned Maintenance":0.35,"Equipment Failure":0.25,"Operator Error":0.15,"Changeover":0.15,"Material Shortage":0.10},
}
FALLBACK_PLANTS = {1:"Riverside Plant", 2:"Rheinland Plant"}

def _nk(v):
    if pd.isna(v): return v
    if isinstance(v, float) and v.is_integer(): return int(v)
    return v

plant_names = {_nk(r["ID"]): r["Name"] for _, r in plants.iterrows()}
plant_names.update({k: v for k, v in FALLBACK_PLANTS.items() if k not in plant_names})
line_lookup = {}
for _, r in lines.iterrows():
    pid = _nk(r["PlantID"])
    line_lookup[r["line_name"]] = {
        "line_type": r["Type"], "plant_id": pid,
        "plant_name": plant_names.get(pid, FALLBACK_PLANTS.get(pid, "Unknown Plant")),
    }

def allocate(total_down, line_type):
    w = WEIGHTS[line_type]
    m = {x: int(round(total_down * w[x])) for x in REASON_ORDER}
    rem = int(total_down - sum(m.values()))
    if rem:
        big = max(REASON_ORDER, key=lambda x: (w[x], m[x]))
        m[big] += rem
    assert sum(m.values()) == total_down
    return m

grouped = (production.groupby(["Date","line_name","Shift"], as_index=False, dropna=False)["Down"]
           .sum().rename(columns={"Down":"total_down"}))
grouped = grouped[grouped["total_down"] != 0]

rows = []
for _, g in grouped.iterrows():
    md_ = line_lookup[g["line_name"]]
    for reason, mins in allocate(int(g["total_down"]), md_["line_type"]).items():
        if mins <= 0: continue
        rows.append({"Date":g["Date"], "line_name":g["line_name"], "Shift":g["Shift"],
                     "plant_id":md_["plant_id"], "plant_name":md_["plant_name"],
                     "line_type":md_["line_type"], "reason_category":reason, "downtime_minutes":mins})

downtime_df = pd.DataFrame(rows, columns=["Date","line_name","Shift","plant_id","plant_name",
                                          "line_type","reason_category","downtime_minutes"])
downtime_df["downtime_minutes"] = downtime_df["downtime_minutes"].astype(int)
assert int(downtime_df["downtime_minutes"].sum()) == int(production["Down"].sum()), "downtime reconciliation FAILED"
print("downtime_reasons rows:", len(downtime_df), "| total minutes:", int(downtime_df["downtime_minutes"].sum()), "-> reconciles OK")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## Step 3 - Generate `sales_orders` (deterministic per product/plant/month)

# CELL ********************

import hashlib, random

CAT_RANGE = {"Pumps":(5,40),"Turbines":(2,20),"Valves":(20,120),"Motors":(15,90),"Sensors":(80,400),"Spare Parts":(50,300)}
def units(code, pid, y, m, cat):
    lo, hi = CAT_RANGE.get(cat, (10,100))
    seed = int.from_bytes(hashlib.sha256(f"{code}|{pid}|{y}|{m}".encode()).digest()[:8], "big")
    return random.Random(seed).randint(lo, hi)
def money(v): return round(float(v), 2)

pdates = pd.to_datetime(production["Date"])
months = pd.date_range(pdates.min().to_period("M").to_timestamp(),
                       pdates.max().to_period("M").to_timestamp(), freq="MS")
srows = []
for ms in months:
    y, m = int(ms.year), int(ms.month)
    for _, p in products.iterrows():
        cat = str(p["Cat"]); up = money(p["Price"]); uc = money(p["Cost"])
        for _, pl in plants.iterrows():
            pid = int(pl["ID"]); u = units(str(p["Code"]), pid, y, m, cat)
            rev = money(u*up); cst = money(u*uc)
            srows.append({"order_date":ms.strftime("%Y-%m-%d"), "product_code":str(p["Code"]),
                          "product_name":str(p["Name"]), "category":cat, "subcategory":str(p["SubCat"]),
                          "plant_id":pid, "plant_name":str(pl["Name"]), "region":str(pl["Region"]),
                          "units_sold":u, "unit_price":up, "revenue":rev, "unit_cost":uc,
                          "cost":cst, "margin":money(rev-cst)})
sales_df = pd.DataFrame(srows, columns=["order_date","product_code","product_name","category","subcategory",
                                        "plant_id","plant_name","region","units_sold","unit_price",
                                        "revenue","unit_cost","cost","margin"])
print("sales_orders rows:", len(sales_df), "| total revenue: ${:,.0f}".format(sales_df["revenue"].sum()))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## Step 4 - Write both DataFrames as Delta tables
#
# `delta-rs` writes directly to OneLake using the Fabric storage token. This keeps the notebook on
# the lightweight Python runtime while producing standard Delta tables under the Lakehouse `Tables`
# folder.

# CELL ********************

import pyarrow as pa
from deltalake import write_deltalake

down_path = f"{abfss}/Tables/{schema_name}/{downtime_table}"
sales_path = f"{abfss}/Tables/{schema_name}/{sales_table}"

storage_options = {
    "bearer_token": notebookutils.credentials.getToken("storage"),
    "use_fabric_endpoint": "true",
}

down_to_write = downtime_df.copy()
down_to_write["Date"] = pd.to_datetime(
    down_to_write["Date"],
).dt.date

sales_to_write = sales_df.copy()
sales_to_write["order_date"] = pd.to_datetime(
    sales_to_write["order_date"],
).dt.date

write_deltalake(
    down_path,
    pa.Table.from_pandas(
        down_to_write,
        preserve_index=False,
    ),
    mode="overwrite",
    schema_mode="overwrite",
    storage_options=storage_options,
)
write_deltalake(
    sales_path,
    pa.Table.from_pandas(
        sales_to_write,
        preserve_index=False,
    ),
    mode="overwrite",
    schema_mode="overwrite",
    storage_options=storage_options,
)

print("Wrote:", down_path)
print("Wrote:", sales_path)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## Step 5 - Validate the Delta tables with DuckDB
#
# Read the newly written Delta tables through `delta-rs`, register their Arrow data in DuckDB, and
# run the reconciliation and business checks before exposing the data to the agent.

# CELL ********************

from deltalake import DeltaTable

down_arrow = DeltaTable(
    down_path,
    storage_options=storage_options,
).to_pyarrow_table()
sales_arrow = DeltaTable(
    sales_path,
    storage_options=storage_options,
).to_pyarrow_table()

con.register("downtime_reasons", down_arrow)
con.register("sales_orders", sales_arrow)

validation = con.execute(
    '''
    SELECT
        (SELECT COUNT(*) FROM downtime_reasons) AS downtime_rows,
        (SELECT COUNT(*) FROM sales_orders) AS sales_rows,
        (SELECT SUM(downtime_minutes) FROM downtime_reasons) AS downtime_minutes,
        (SELECT ROUND(SUM(revenue), 2) FROM sales_orders) AS total_revenue
    '''
).df()
display(validation)

assert int(validation.loc[0, "downtime_minutes"]) == int(
    production["Down"].sum()
), "Downtime minutes do not reconcile to ProductionLog."

print("Top Assembly downtime reasons:")
display(
    con.execute(
        '''
        SELECT
            reason_category,
            SUM(downtime_minutes) AS downtime_minutes,
            ROUND(
                100.0 * SUM(downtime_minutes)
                / SUM(SUM(downtime_minutes)) OVER (),
                2
            ) AS reason_share_pct
        FROM downtime_reasons
        WHERE line_type = 'Assembly'
        GROUP BY reason_category
        ORDER BY downtime_minutes DESC
        '''
    ).df()
)

print("Top product category by revenue:")
display(
    con.execute(
        '''
        SELECT category, ROUND(SUM(revenue), 2) AS revenue
        FROM sales_orders
        GROUP BY category
        ORDER BY revenue DESC
        LIMIT 1
        '''
    ).df()
)

print("Waiting for the SQL analytics endpoint to discover the Delta tables...")
time.sleep(5)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

## Refresh SQL EP


import sempy.fabric as fabric

sqlEndpointId = notebookutils.lakehouse.getWithProperties(lakehouse_name)['properties']['sqlEndpointProperties']['id']
client = fabric.FabricRestClient()
client.post(f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/sqlEndpoints/{sqlEndpointId}/refreshMetadata")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ## Step 6 - Create the agent-facing views and function
#
# These cells run against the Lakehouse SQL analytics endpoint. The `fda` schema gives the Data
# Agent a stable, friendly interface and prevents it from querying future-dated records.
#
# `OpsRefData` is created automatically above, so no manual Lakehouse attachment is required.

# CELL ********************

%%tsql -artifact OpsRefData -type Lakehouse

IF SCHEMA_ID('fda') IS NULL EXEC('CREATE SCHEMA fda');

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

%%tsql -artifact OpsRefData -type Lakehouse

-- Drop existing objects so the notebook is re-runnable
DROP VIEW IF EXISTS [fda].[Sales_Orders];
DROP VIEW IF EXISTS [fda].[Downtime_Reasons];

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

%%tsql -artifact OpsRefData -type Lakehouse

-- =====================================================
-- VIEW: Downtime_Reasons  (root-cause; trimmed to <= today)
-- =====================================================
CREATE VIEW [fda].[Downtime_Reasons]
AS
SELECT
    [Date]            AS [Date],
    line_name         AS [Line Name],
    Shift             AS [Shift],
    plant_id          AS [Plant ID],
    plant_name        AS [Plant Name],
    line_type         AS [Line Type],
    reason_category   AS [Reason Category],
    downtime_minutes  AS [Downtime Minutes]
FROM [OpsRefData].[dbo].[downtime_reasons]
WHERE [Date] <= CAST(GETDATE() AS DATE);   -- align with the ops model's AsOfDate <= today

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

%%tsql -artifact OpsRefData -type Lakehouse

-- =====================================================
-- VIEW: Sales_Orders  (sales augmentation; trimmed to <= today)
-- =====================================================
CREATE VIEW [fda].[Sales_Orders]
AS
SELECT
    order_date    AS [Order Date],
    product_code  AS [Product Code],
    product_name  AS [Product Name],
    category      AS [Category],
    subcategory   AS [Subcategory],
    plant_id      AS [Plant ID],
    plant_name    AS [Plant Name],
    region        AS [Region],
    units_sold    AS [Units Sold],
    unit_price    AS [Unit Price],
    revenue       AS [Revenue],
    unit_cost     AS [Unit Cost],
    cost          AS [Cost],
    margin        AS [Margin]
FROM [OpsRefData].[dbo].[sales_orders]
WHERE order_date <= CAST(GETDATE() AS DATE);   -- never expose future-dated months to the agent

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

%%tsql -artifact OpsRefData -type Lakehouse

-- Drop the function first (separate batch; no GO separator in %%tsql)
DROP FUNCTION IF EXISTS [fda].[Downtime_By_Line_Type];

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

%%tsql -artifact OpsRefData -type Lakehouse

-- =====================================================
-- FUNCTION (inline TVF): reason breakdown for a given line type.
-- CREATE FUNCTION must be the FIRST statement in its batch -> its own cell.
-- =====================================================
CREATE FUNCTION [fda].[Downtime_By_Line_Type] (@line_type VARCHAR(50))
RETURNS TABLE
AS
RETURN
(
    SELECT reason_category AS [Reason Category],
           SUM(downtime_minutes) AS [Downtime Minutes]
    FROM [OpsRefData].[dbo].[downtime_reasons]
    WHERE line_type = @line_type
      AND [Date] <= CAST(GETDATE() AS DATE)
    GROUP BY reason_category
);

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

%%tsql -artifact OpsRefData -type Lakehouse

-- Validation: row counts through the views + a function call
SELECT 'Downtime_Reasons' AS [Object], COUNT(*) AS [Rows] FROM [fda].[Downtime_Reasons]
UNION ALL
SELECT 'Sales_Orders', COUNT(*) FROM [fda].[Sales_Orders];

SELECT * FROM [fda].[Downtime_By_Line_Type]('Assembly') ORDER BY [Downtime Minutes] DESC;

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

sqlEndpointId = notebookutils.lakehouse.getWithProperties(lakehouse_name)['properties']['sqlEndpointProperties']['id']
client = fabric.FabricRestClient()
client.post(f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/sqlEndpoints/{sqlEndpointId}/refreshMetadata")

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
