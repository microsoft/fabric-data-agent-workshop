# Fabric Data Agent Workshop Labs

> Quick-reference companion to the workshop PDF. Organized by Lab → Section so
> you can jump straight to what you need. Questions, prompts, and instructions
> that you need to enter appear in shaded code blocks with a copy button in
> supported Markdown viewers.

## Prerequisites

- A paid F2 or higher Fabric capacity, or a Power BI Premium per capacity (P1 or
  higher) capacity with Microsoft Fabric enabled.
- Fabric tenant settings:
- Enable cross-geo processing and cross-geo storing for AI based on requirements
  explained in Fabric data agent tenant settings. (Data agent tenant settings)
- Enable "Users can use Copilot and other features powered by Azure OpenAI"
  setting
- Power BI Pro license
- At least a Contributor role in a workspace
- Familiarity with Power BI, DAX, Python, SQL

## Optional

- Power BI Desktop
- PDF Viewer

## Lab 1: Creating and optimizing data agents

Lab goal: This lab focuses on creating data agents in Fabric using a semantic
model as a data source. Participants will learn how to create a data agent, how
a data agent works, and how to configure and optimize it using best practices.

### Resources required

- A Fabric paid capacity with data agent tenant settings enabled
- A Power BI Pro license
- A workspace with at least workspace Contributor role

### Step 1: Creating your first data agent

- In your lab workspace, confirm you have the following items: two semantic
  models, two Power BI reports and six notebooks in data-agent-l400 folder
- In the data-agent-l400 folder, click New item > Data agent to create a data
  agent. You can also search for "data agent" in the search box.
- Name the data agent `MfgOps_DA_<YourInitials>`
- Familiarize yourself with the user interface
- In the Explorer pane, select Add Data > Data source
- In the OneLake catalog, select the ManufacturingOps semantic model from your
  workspace, then click Add to complete the selection.
- Select all the tables. The data agent will reason over these tables and
  objects to answer your questions.
- Ask your first question:

**Copy/paste:** Question

```text
I am new to this agent and the data. Tell me more about it and how to use it.
```

You will receive a response with a brief explanation and suggestions with sample
questions you can ask. Test the agent by asking some of the example questions
returned. You can also ask the following questions.

**Copy/paste one at a time:** Questions

```text
Show me the production quantity for the last month.
```

```text
List the top 5 products by total sales.
```

```text
Give me a pivot table with product, total sales, quantity, and inventory.
```

- Click **Clear chat** (top-right corner) to clear the conversation history
  before proceeding. It is recommended to clear the chat between tests during
  development so you can evaluate each configuration change in isolation.
- Ask the following questions in sequence and observe the responses. Your
  responses may differ from the screenshots shown in this lab.

**Copy/paste:** Multi-part question

```text
Which products have inventory below the reorder quantity? How often does that happen?
```

The data agent may break down a question into multiple sub-questions or generate
a single query to answer it. It may generate a visual answer as well.

**Copy/paste:** Context carry-over question

```text
For the top three products by frequency, show me the monthly trend as a bar chart.
```

This question specifically asked about the top three products, which the data
agent identified from the previous response. For those three products, the data
agent generated a bar chart. Notice that the data agent executed three separate
queries and combined the results to produce the final visual.

> **Tip:** The data agent keeps conversation context by default: phrases like
> "the top three" or "those products" refer back to your previous question. Use
> **Clear chat** whenever you want to test a question in complete isolation.

**Copy/paste:** Domain-specific KPI question

```text
For the bottom 20% of products by revenue, do we run into inventory issues? Why?
```

Click "1 step completed" to see how the data agent arrived at the answer.
Inspect the DAX query the data agent generated. Notice that, without any
additional instructions, the data agent interpreted the vague "inventory issues"
question using the schema and context of the data source, reusing existing
inventory-related measures and creating new ones to answer the question and
generate the response.

### Step 2: Improving and optimizing data agent responses

As we saw in the previous step, the data agent was able to generate
natural-language responses grounded in the semantic model data. To improve those
responses further, we need to understand how the data agent works, how to spot
common issues, and how to fix them, increasing accuracy and trust in the
results.

For each question below, ask it, then review these three outputs the data agent
returns:

- Paraphrased question
- DAX query
- Final response

Clear the chat history before proceeding. Ask each specified question, expand
the run step, and observe the response.

#### Q1

**Copy/paste:** Question

```text
What is our scrap %?
```

**Observation:** Inspect the DAX by expanding the run step. The data agent uses
the existing `[Scrap Rate %]` measure but has to guess the time window,
defaulting to either the latest date or the entire time period. The answer isn't
wrong, but the assumed period isn't guaranteed to match what the user meant. In
the next lab, we will remove this ambiguity by instructing the data agent to use
a default time window, such as the last 30 days. Agent instructions can be used
to steer the agent's behavior and responses.

#### Q2

**Copy/paste:** Question

```text
What is our OEE?
```

**Observation:** OEE isn't defined anywhere in the model or the agent
configuration, although it is a manufacturing industry term. Even so, the data
agent infers from the schema context that OEE means Overall Equipment
Effectiveness and returns the KPI by creating an ad hoc measure. Because this
measure isn't defined in the model, the data agent may calculate it differently
the next time the same question is asked, leading to inconsistent answers over
time. This is why it is best practice to define governed measures with
business-friendly names directly in the semantic model, so the data agent always
uses the same definition. We'll configure this in the next lab.

> **Tip:** Rule of thumb: any KPI users will ask about by name (OEE, scrap rate,
> yield) should be a governed measure in the semantic model, not something the
> data agent has to infer on the fly.

#### Q3

**Copy/paste:** Question

```text
What is our day production yield for the last six months?
```

**Observation:** Inspect the DAX. The data agent should ideally use the
`[prd_yld_day]` measure, but results may vary by user. Some may see the data
agent correctly use `[prd_yld_day]`, while others may see it calculate day
production yield using the `[Production Yield %]` measure, applied per day over
the last six months. This semantic model also has a poorly named measure,
`[prd_yld_day]`, with a code comment noting that it calculates day production
yield by excluding the night shift; in other words, yield for day shifts only.
This is the measure the data agent should have used.

> **Tip:** The data agent relies on the schema, schema descriptions, **Prep data
> for AI** configuration, and agent instructions to answer questions about the
> semantic model; it does not read DAX code or comments. This can be fixed by
> adding an instruction such as "For day production yield, use the
> `[prd_yld_day]` measure" to **Prep data for AI**. We'll configure this in the
> next lab.

#### Q4

**Copy/paste:** Question

```text
What were the TP sales last week?
```

**Observation:** This semantic model has no column, column value, or measure
that defines what "TP" means. At this company, "TP" is an acronym for
Turbine-Pump sales, calculated by a cryptically named measure, `[sls_amt_x]`.
This is a common pattern in many organizations, where a KPI or value has aliases
or acronyms an agent has no way of knowing. We can add a description to the
`[sls_amt_x]` measure so the data agent can use it. After adding the
description, the data agent correctly maps "TP" to the measure and returns the
right answer. We will test it in the next lab.

> **Tip:** Business-friendly names and descriptions are the primary context the
> data agent uses to resolve acronyms, internal codes, and ambiguous terms like
> "TP" or "OEE." You can also instruct the agent to ask a clarifying question if
> a term or acronym is not defined anywhere.

#### Q5

**Copy/paste:** Question

```text
Show me the distribution of scrap rate by machine.
```

**Observation:** The data agent assumes Machine maps to the `Lines[asset]`
column and produces the visual. This looks correct, but at this company, any
machine-related question should use the `Lines[Manufacturing]` column instead.
This is company-specific context the agent will not know. A column name may mean
one thing in the schema but something else to the business: a "Customer" column
might really be a "user," or a "Product ID" might be a "SKU." To get reliable
results, surface the right business context in the right configuration.

### Step 3: Configuring and optimizing the semantic model and data agent

Creating a trusted data agent requires analyzing its responses and configuring
it correctly. In this step, we will use the available optimization controls to
create a robust data agent based on a defined scope and context.

A data agent can include multiple data sources. First identify its scope: a
specific topic, such as inventory management; a domain, such as manufacturing
operations; or an area, such as a single plant or product line. Configure and
optimize the agent based on that scope.

#### Scope

In our previous example, we selected all the tables and measures in the semantic
model. In this exercise, we will limit the scope to questions related to
manufacturing operations. Leave any unnecessary tables, columns, measures, and
objects out of the data agent's scope.

#### Preparing the semantic model for AI

How a human consumes and uses data is fundamentally different from how AI
retrieves and uses it. AI needs human-provided context to retrieve and use data
with the correct guardrails. There are four primary controls:

- **Semantic model foundation:** star schema, RLS/CLS, and schema names
- **Business logic:** measures and columns
- **Semantic metadata:** descriptions, synonyms, and hierarchies
- **AI readiness and context:** Prep data for AI and data agent configuration

#### Semantic model configuration

Open the **ManufacturingOpsAIReady** semantic model in your workspace. This
model includes the following changes based on the tests we performed:

- All tables, columns, and measures have business-friendly names.
- All objects have clear, concise descriptions that define the business context
  and when to use them. These descriptions are prioritized for AI retrieval.
- The `Customer[Customer Name]` column uses a descriptive name instead of
  `[Name]`. Its description includes an example value and usage guidance,
  helping disambiguate entities such as Asset Name and Customer Name.
- The `[sls_amt_x]` measure has a description. Ideally, this measure would be
  renamed, but descriptions can provide context when downstream dependencies
  prevent renaming.

#### Prep data for AI

Prep data for AI helps optimize a semantic model for Copilot and data agents,
improving the accuracy, context, and relevance of AI-driven insights.

1. Switch to **Editing** mode in the model view.
2. Select **Prep data for AI**.
3. Configure the **AI data schema**. An AI data schema defines a focused subset
   of the model for Copilot and data agents to prioritize. Limit this agent to
   manufacturing operations topics.
4. Configure **Verified answers**. These are human-approved visual responses
   with predefined trigger phrases and optional filters. Define prompts for
   machine-related questions and select the Manufacturer column. Verified
   answers improve accuracy and consistency and reduce latency.
5. Configure **AI instructions**. These provide context, business logic, and
   guidance directly on the semantic model. Based on our previous tests, add
   instructions that incorporate organizational terminology and analytical
   priorities. AI instructions in Prep data for AI influence DAX generation.

> **Tip:** Two instruction layers exist. Semantic model AI instructions in
> **Prep data for AI** shape the DAX the agent generates, while data agent
> instructions shape orchestration, tone, and response formatting. Use
> model-level instructions for "always calculate this way" rules and agent-level
> instructions for "always respond this way" rules.

1. Select **Close**.

### Step 4: Testing the optimized semantic model

- Create a new data agent named `MfgOps_DA_AIReady_<Your_Initials>`.
- Add the AI-ready semantic model to the data agent.
- Select the limited schema configured in Prep data for AI.
- Add the following agent instructions. These Markdown-formatted orchestrator
  instructions control tone, formatting, and data-source routing.

**Copy/paste:** Instructions for the data agent's **Instructions** box

```markdown
# Scope

Answer questions about manufacturing operations using Assets, Business Measures,
Date, Inventory, Lines, Plants, ProductionLog, and Products. Focus on production
performance, asset utilization, inventory, plant/line comparisons, trends, and
operational KPIs. Do not answer customer, sales, purchasing, or vendor
questions.

# Audience

Plant managers, operations leaders, production supervisors, inventory planners,
manufacturing analysts, and executives seeking operational insights.

# Tone

Clear, concise, professional, and action-oriented. Use plain business language,
explain technical manufacturing terms when needed, and avoid unsupported
conclusions.

# Guidelines

- DO NOT answer any questions or explain anything related to sales, customers,
  vendors, purchase orders (PO). Decline with the response "This question is out
  of scope for this agent. Please ask a manufacturing operations-related
  question."
- Unless the user specifies otherwise, always default to the 30 days preceding
  the latest production date for all questions and KPIs. If a different period
  is used, state it clearly in the response.
- Confirm the plant, line, product, and date range when a request is ambiguous.
- State units, periods, filters, and assumptions clearly.
- Provide direct answers first, followed by key drivers or comparisons.
- Highlight operational exceptions, trends, and potential bottlenecks.
- Redirect out-of-scope questions involving Customers, PurchaseOrders, Sales,
  SalesSummary, or Vendors.
- Location: use plant location unless the user specifies otherwise.

# Common Abbreviations

- RQX: Scrap rate
- OEE: Overall Equipment Effectiveness, also reliability
- DPMP: Defects per million parts
- YoY/YOY: Year over year
- MTD: Month to date
- MOM: Month over month
- TP: Turbine + Pumps
- DPY: Day Production Yield
```

Close the agent instruction tab to save the instructions. Ask the same questions
from the last section and inspect the responses:

**Copy/paste:** Question 1

```text
What is our scrap rate?
```

Expected: Uses the default 30-day period.

**Copy/paste:** Question 2

```text
What is the OEE this year?
```

Expected: Resolves OEE using the predefined measure and overrides the default
period.

**Copy/paste:** Question 3

```text
What is our day production yield for the last six weeks? Break it down by lines.
```

Expected: Uses the Day Yield Pct measure.

**Copy/paste:** Question 4

```text
What were the TP sales last week?
```

Expected: Declines the question as out of scope.

**Copy/paste:** Question 5

```text
What's the YOY TP reliability?
```

Expected: Resolves YOY, TP, and reliability according to the instructions.

**Copy/paste:** Question 6

```text
Show me the distribution of scrap rate by machine.
```

Expected: Uses `Assets[Manufacturer]`.

#### Data agent runtime

Every Fabric data agent runs on a runtime. The runtime determines the agent's
core components: the orchestration, planning, and routing logic, along with the
built-in query-generation tools that translate natural-language questions into
queries against your data sources.

Fabric offers two runtimes:

- **Standard runtime:** The generally available (GA) runtime, optimized for
  stable, predictable behavior. This is the default runtime.
- **Preview runtime:** A runtime with the latest improvements to core components
  before those changes graduate to GA.

The runtime you choose determines how and when changes to the agent's core
components reach your agent. It doesn't determine which data sources or preview
features you can add.

For semantic models, the Preview runtime includes advanced DAX generation
features which can result in more accurate, consistent and faster queries. Let's
try one complex question.

1. Clear the chat. In the Standard runtime, ask the following question. Inspect
   the result, DAX, and latency.

   **Copy/paste:** Question

   ```text
   For each plant, return the smallest ordered set of line-and-shift combinations
   that reaches at least 80% of that plant's downtime. Include the first
   combination that crosses 80%. Show plant, line, shift, downtime minutes, rank
   within plant, share of plant downtime, cumulative share, and cumulative share
   before the row. Show the result as a table.
   ```

2. Switch the runtime to Preview. Clear the chat and ask the same question.
3. Compare the results and latency. Over 10 runs per runtime, Preview should
   complete this query approximately 45% faster by median latency while
   returning complete and consistent results.

#### AI-assisted modeling changes

As we saw in the previous sections, preparing the data and semantic model are
critical for AI driven insights. Users can add their domain knowledge and
context at various levels of the configurations. For large models, this process
can be daunting. However, with AI tools, we can accelerate the development and
make changes to the model.

1. Open the **ManufacturingOps** semantic model, not the
   **ManufacturingOpsAIReady** model.
2. Switch to **Editing** mode.
3. Open Copilot.

   Modeling Copilot can rename schema objects, add measures and columns, and add
   descriptions.

4. This model has several columns called "names." In the Copilot pane, ask the
   following prompt to propose self-descriptive names:

   **Copy/paste:** Prompt

   ```text
   Identify all the name columns in this model. Using the table context and
   sample values, propose more descriptive names that clearly reflect the
   business meaning. Return a table with: Current Name, Proposed Name.
   ```

   Select **Allow**.

5. Copilot should return a table with proposed changes.

   > **Important:** Before making modeling changes, always verify whether they
   > will affect dependent objects and data products.

6. Ask Copilot to make the changes, then confirm that they were made.

   **Copy/paste:** Response

   ```text
   Approved, make the changes.
   ```

   > **Optional:** Skip the following description exercise if short on time.

7. Add descriptions using the following prompt:

   **Copy/paste:** Prompt

   ```text
   This semantic model will be used by a Fabric data agent to answer
   manufacturing operations questions. Add descriptions based on the following
   guidelines.

   DO: Add a description to every visible table, column, and measure. Keep
   descriptions concise because only the first 200 characters are read by the
   data agent. Front-load preferred usage, disambiguation, and units. Make
   implicit knowledge explicit. Do not restate the field name or add DAX logic.
   Sample values if necessary to learn the domain and context. Include expected
   grain where useful. For calculation groups, use the calculation group column
   description to enumerate items and explain their use, for example: "Use with
   measures and date table for: Current, MTD, QTD, YTD, PY, YOY, YOY%." The same
   200-character limit applies.

   DON'T: Generate descriptions purely from AI without business context. AI-only
   descriptions tend to restate what the model structure already shows. Always
   validate descriptions with the user or a domain expert. Do not contradict
   descriptions across related fields.
   ```

   After reviewing the proposed descriptions, ask Copilot to update them.

   **Copy/paste:** Response

   ```text
   Update the descriptions.
   ```

8. Use this checklist to prepare the model for AI:

   - Business-friendly names for all visible tables, columns, and measures
   - Concise, front-loaded descriptions on every visible object
   - Synonyms for terms and abbreviations business users type
   - Hierarchies where users naturally drill, such as Plant > Line > Machine
   - A star schema with one-directional relationships where possible
   - RLS/CLS applied and tested for restricted data
   - An AI data schema scoped to the agent's intended topic or domain
   - Verified answers for recurring, high-value questions
   - AI instructions for calculations the data agent would otherwise have to
     guess

#### Code Interpreter

The code interpreter tool gives your data agent a secure, sandboxed Python
environment for analyzing the data it retrieves. With the tool enabled, your
data agent can go beyond querying your data sources and answer natural language
questions that require data analysis, mathematical computations, or
visualizations. For example, you can ask your data agent to chart trends over
time, detect correlations across columns, or combine results from multiple
sources. The agent generates and runs the Python code on your behalf, and you
can review the generated code, outputs, and Python visualizations directly in
the run steps.

1. In the data agent that uses the AI-ready semantic model, select **Tools** >
   **Add tools** > **Code interpreter**.
2. Clear the chat and ask:

   **Copy/paste:** Question

   ```text
   Show me a pivot table of products vs. the last six months by reliability. Put
   products on rows and months in columns.
   ```

3. Ask:

   **Copy/paste:** Question

   ```text
   Show me a heatmap.
   ```

4. Inspect the Python code. Code Interpreter should write Python in a sandbox
   and return a heatmap that makes it easy to explore the data and find
   insights.

   > **Optional:** Skip the following statistical analysis if short on time.

5. Ask:

   **Copy/paste:** Question

   ```text
   Detrend the daily scrap rate for Pump Impeller for the last two months, run
   FFT on it, and identify any dominant modes.
   ```

This type of analysis is common in manufacturing operations to analyze time
series data to find insights. Here we are asking the data agent to first get the
scrap rate for a product for the last 2 months, remove the trend component from
it and perform a Fast Fourier Transform to analyze the signal in the frequency
domain. This can help identify latent signals and patterns which otherwise may
be missed.

## Lab 2: Programmatic evaluation of data agents

Fabric data agents have an accompanying Python SDK that can be used to evaluate
data agents in a Fabric notebook. Our goals for this lab:

- Learn about the evaluation process
- Set up and calibrate LLM-as-Judge
- Evaluate a data agent using the Python SDK

### LLM-as-Judge calibration

1. Open or download the judge calibration set Excel workbook for review.

2. Review its two sheets:

   - `calibration_development`: Labeled by the data agent creator to develop,
     test, and refine the judge rubric
   - `calibration_holdout`: Kept sealed and labeled independently to validate
     the final judge before approval

   The responses are already labeled for this lab. Take a few minutes to review
   them. In practice, complete the labeling exercise with other developers and
   end users.

3. In your Fabric workspace, open and execute the **JudgeCalibration** notebook.
4. The notebook creates an evaluation lakehouse, downloads the calibration
   workbook, evaluates the candidate judge against human-labeled development and
   holdout sets, and registers the approved champion judge in MLflow.
5. In Step 7 of the notebook, select the MLflow run shown inline.
6. In the MLflow experiment, review the logged run details, including the judge
   rubric and model used, for reproducibility and traceability.

### Data agent evaluation using the Python SDK

The Fabric data agent Python SDK provides programmatic access to Fabric data
agent artifacts. It's designed for code-first users who want to create,
configure, update, and publish data agents without using the Fabric portal. You
can run the SDK inside a Microsoft Fabric notebook, or from your own environment
after you authenticate to Fabric. Evaluation methods using the Responses API
only work in Fabric notebook.

> **Important:** If you run the SDK outside a Fabric notebook, you can still
> create, configure, and publish data agents, but Responses API evaluation calls
> will fail. Run the **JudgeCalibration** and **EvaluateDataAgent** evaluation
> notebooks inside Fabric.

1. Download or review `eval_set_L400_test.xlsx`. It contains three test
   questions and the following fields:

   - Goal of evaluation
   - Question
   - Ground truth
   - Expected behavior
   - Policy area

   The SDK asks these questions of the data agent, and the calibrated judge
   rates the responses. The run steps, agent configuration, responses, and
   evaluation results are logged to an MLflow experiment in your workspace.

2. Open the **EvaluateDataAgent** notebook and change the data agent name in the
   **Select the Data Agent** cell.
3. Execute the notebook. The evaluation takes approximately five minutes.
4. In Step 6 of the notebook, review the overall evaluation results and select
   the MLflow run to see its details.
5. If overall accuracy is less than 100%, investigate the cause by reviewing the
   DataFrame in the **Per-question review** cell under Step 6.
6. Open the MLflow run to review the data agent configuration, questions,
   responses, DAX run steps, judge reasoning, and other evaluation details.

## Lab 3: Adding multiple data sources

So far, we created data agents using a semantic model as a data source. A data
agent supports multiple OneLake data sources, including:

- Lakehouse
- Warehouse
- SQL database
- KQL database
- AI Search
- Ontologies

Refer to the Fabric data agent data sources documentation for the complete list
of supported data sources.

In this lab, we will use the Python SDK to add a Lakehouse to the existing data
agent and update its configuration.

### Adding a Lakehouse data source with the Python SDK

1. In your workspace, open the **BuildOpsRefData** notebook.
2. Confirm that you are using the Python 3.11 or 3.12 runtime.
3. Select **Run all**. Execution takes approximately five minutes.
4. After the notebook runs successfully, confirm that the **OpsRefData**
   lakehouse exists.
5. Open the **OpsRefData** SQL endpoint and verify that the `fda` schema
   contains the `Downtime_Reasons` and `Sales_Orders` views.
6. Open the **CreateMultiSourceDataAgent** notebook.
7. In the **Parameters** cell, set `BASE_DATA_AGENT_NAME` to the AI-ready data
   agent you created earlier.
8. Execute the notebook. It will:

   - Copy the configuration from the specified base data agent
   - Add the Lakehouse as another source
   - Select views from the SQL endpoint
   - Update the agent instructions for the new data source
   - Add a data source description, instructions, and few-shot examples
   - Publish the data agent
   - Test the published data agent using the MCP server endpoint

9. Open the newly created data agent whose name ends in `_MultiSource`.
10. Inspect its sources, instructions, and few-shot examples. Ask questions to
    confirm the changes.
11. Select the **Setup** tab to inspect the Lakehouse instructions and example
    queries.

### Creator Assistant: Build agent with AI

Build agent with AI mode is a specialized AI assistant that helps you quickly
build and refine the configurations that determine how a data agent behaves when
answering questions over your data. Build agent with AI guides you through
generating and improving the core configurations: Agent Instructions, Data
Source Instructions, Data Source Descriptions, and Example Queries. Currently it
supports SQL and KQL data sources with support for other data sources coming
soon.

1. Select **Build agent with AI**.
2. Enter the following prompt:

   **Copy/paste:** Prompt

   ```text
   Can you update the agent instructions and the OpsRefData data source
   instructions, and add a few-shot example so that when a user asks about the
   turbomachinery category, the query filters for Pumps and Turbines, but not
   Motors? Please sample the values first to confirm.
   ```

3. The Creator Assistant will query the Lakehouse, confirm that the values
   exist, and propose updated instructions for your review.
4. Review the updated instructions and direct the assistant to make the changes.

   **Copy/paste:** Response

   ```text
   Apply these changes.
   ```

5. Ask the assistant to test the change and verify that it works as expected.

   **Copy/paste:** Prompt

   ```text
   Test this change and verify that it works as expected.
   ```

6. Before publishing the data agent, ask the assistant to generate a
   description:

   **Copy/paste:** Prompt

   ```text
   Generate a concise description of what this data agent does. Focus on the
   specific business domain and the questions it answers. Avoid generic,
   reusable descriptions. Make it specific to this data agent's unique purpose
   and capabilities. Do not use bullet points and do not mention table names,
   column names, datasets, schemas, or other technical implementation details.
   Use clear language that accurately describes its value.
   ```

7. Review the description and copy it when you are satisfied.
8. Select **Publish**.
9. In the description box, add the generated description followed by:

   **Copy/paste:** Description text

   ```text
   The output from the data agent should be delivered as-is, without summarizing,
   rephrasing, or adding extra interpretation or insight.
   ```

   Turn on **Also publish to the Agent Store in Microsoft 365 Copilot** so this
   data agent is available in Microsoft 365 Copilot. A description is required
   for Microsoft 365 Copilot to work correctly.

## Workshop complete

Congratulations! You have completed all the labs.

### What you learned in Lab 1

- Built a data agent on a Power BI semantic model and asked it natural-language
  questions
- Inspected the DAX, latency, and response quality behind each answer
- Configured AI instructions, verified answers, and an AI data schema
- Used Copilot to rename columns and add descriptions
- Compared Standard and Preview runtime performance
- Used Code Interpreter for pivot tables, visualizations, and statistical
  analysis

### What you learned in Lab 2

- Calibrated an LLM-as-Judge against labeled development and holdout sets
- Ran automated evaluation through the Python SDK and reviewed accuracy and
  latency

### What you learned in Lab 3

- Added a Lakehouse as a second data source using the Python SDK
- Built and published a multi-source data agent
- Used Build agent with AI to refine instructions, add few-shot examples, and
  generate an agent description
