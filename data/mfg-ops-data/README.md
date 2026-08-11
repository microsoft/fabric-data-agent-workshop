# mfg-ops-data — Manufacturing Ops source CSVs

The **single source of truth** for the workshop data. These 11 CSVs build the
**Manufacturing Ops** semantic model, and a subset is reused to build the Lab 3
**Lakehouse** tables (`downtime_reasons`, `sales_orders`) — so there is no separate
lakehouse dataset to maintain.

> The messy column/file names (`Sheet1.csv`, `sales_data_FINAL.csv`, `Down`, `Qty`, `Mfr`,
> `loc`, `DeviceID`) are **intentional teaching traps** for the Lab 1 modeling/debugging
> exercises.

---

## What each table contains

### Dimensions

**`Plants.csv`** → **Plants** — Plant master (one row per manufacturing plant).
`ID`, `Name`, `Region`, `Country`, `City`, `Year` (year opened).

**`lines.csv`** → **Lines** — Production-line master (one row per line).
`LineID`, `line_name`, `PlantID`, `loc` (floor location), `DeviceID`, `Type`
(line type: Assembly / Machining / Winding / Calibration / Test), `asset`, `Mfr` (manufacturer).
*Trap: lines join to other tables by `line_name`, and `DeviceID` is the bridge to Assets.*

**`Assets.csv`** → **Assets** — Equipment/device master (one row per asset).
`ID`, `Device_Id`, `Name`, `type` (e.g. IndustrialPump), `Mfr`, `PlantID`, `Location`.
*Trap: `Device_Id` here vs `DeviceID` elsewhere — a deliberate name mismatch.*

**`PRODUCTS.csv`** → **Products** — Product catalog (one row per product).
`ID`, `Code`, `Name`, `Cat` (category: Pumps, Turbines, Valves, Motors, Sensors, Spare Parts),
`SubCat`, `Price` (list price), `Cost` (unit cost).

**`Customers_Master.csv`** → **Customers** — Customer master (one row per customer).
`ID`, `custName`, `segment` (e.g. Utility, Mining), `Region`, `country`.

**`vendor list.csv`** → **Vendors** — Supplier master (one row per vendor).
`id`, `vendor_name`, `type` (e.g. OEM Components), `country`, `rating`.

### Facts

**`ProductionLog.csv`** → **ProductionLog** — Daily production & downtime, grain = **Date × line × shift**.
`Date`, `Timestamp`, `Year`, `line_name`, `DeviceID`, `product_name`, `Shift` (Day/Swing/Night),
`Planned` (planned units), `Qty` (units produced), `Good`, `Scrap`, `Runtime` (minutes),
`Down` (downtime minutes). *Drives OEE, scrap rate, schedule attainment, downtime.*

**`sales_data_FINAL.csv`** → **Sales** — Sales order lines, grain = **order line**.
`OrderNo`, `Date`, `Year`, `custName`, `region`, `Prod` (product name), `Cat`, `Qty`,
`Price`, `Disc` (discount), `Amount` (revenue), `Cost`, `Profit`.

**`Sheet1.csv`** → **SalesSummary** — Pre-aggregated daily sales, grain = **Date × customer**.
`Date`, `custName`, `Amount`. *A redundant rollup of Sales — a teaching trap for duplicate facts.*

**`inventory.csv`** → **Inventory** — Daily inventory position, grain = **Date × product × plant**.
`Date`, `Product`, `Plant`, `Qty` (on hand), `Reorder` (reorder point), `InTransit`.

**`PO_Data.csv`** → **PurchaseOrders** — Purchase orders to vendors, grain = **PO line**.
`PO_Number`, `Date`, `VendorName`, `Plant`, `Qty`, `UnitCost`, `Amount`,
`PromisedDays`, `ActualDays`, `OnTime` (delivery on time). *Supplier on-time / lead-time analysis.*

---

## Built-in entity-name collision (disambiguation lab)

The token **"AquaFlow"** is intentionally reused across **four different entity types** so
the Data Agent must disambiguate which one a question refers to:

| Entity type | Where it lives | Value(s) |
|-------------|----------------|----------|
| **Product** (what we *make/sell*) | `PRODUCTS.csv` → Products[Name]; `ProductionLog.csv`[product_name]; `sales_data_FINAL.csv`[Prod] | AquaFlow 100 / 200 / 350 / 500 …Pump |
| **Customer / company** (who we *sell to*) | `Customers_Master.csv`[custName]; `sales_data_FINAL.csv`[custName] | AquaFlow Industries |
| **Vendor / supplier** (who we *buy from*) | `vendor list.csv`[vendor_name]; `PO_Data.csv`[VendorName] | AquaFlow Components |
| **Asset / equipment** (a *device* on the floor) | `Assets.csv`[Name] | AquaFlow Transfer Pump (`pump-aqua-01`) |

Each entity has **real backing rows** (AquaFlow Industries has sales orders; AquaFlow
Components has purchase orders), so correctly-routed questions return data and
wrongly-routed ones return none. The lab teaches the agent to pick the entity from the
question's verb/preposition (*uses/makes* → product, *bought from/supplier* → vendor,
*sold to/customer* → customer, *machine/equipment/device* → asset) and to **ask for
clarification** when the phrasing is ambiguous (e.g. "show me AquaFlow").

## Used by the Lab 3 Lakehouse build

`NB_Build_OpsRefLakehouse` derives both lakehouse tables **deterministically** from a
subset of the files above (no extra raw data):

- **`downtime_reasons`** ← `ProductionLog.csv` + `lines.csv` + `Plants.csv`
  (splits `Down` minutes across reason categories; reconciles exactly to model downtime).
- **`sales_orders`** ← `PRODUCTS.csv` + `Plants.csv`
  (deterministic revenue/units/margin per product × plant × month).

## Regenerating / re-anchoring dates

These CSVs are produced by `generate_workshop_data.py` (date self-correcting via the
`AsOfDate` Power Query parameter). The fact tables are generated far into the future and
trimmed to "as of today" at refresh, so the model never goes stale. See the semantic-model
README for details.
