If no time window is specified, assume last 30 days based on [Latest Date] measure which is the most recent Product Log date.

If a user asks about for <KPI> for last N days, follow below pattern:
DEFINE
VAR _LatestDate = [Latest Date]

EVALUATE
  ROW(
    "KPI - Last N Days",
    CALCULATE(
      <KPI>,
      DATESINPERIOD('Date'[Date], _LatestDate, -N, DAY)
    )
  )

For Day Production Yield question use [Day Yield Pct] measure. 

RQX = [Quality %] measure

For all questions related to "machines" use Assets[Manufacturer] column

Product[Price] column should not be used for calculating sales or revenue. ONLY use measures, if present.