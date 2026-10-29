from __future__ import annotations

import math

import pandas as pd

ROUND_TO = 5000


def inr(value: float, sign: bool = False) -> str:
    prefix = "-" if value < 0 else ("+" if sign and value > 0 else "")
    amount = abs(value)
    if amount >= 1e7:
        text = f"{amount / 1e7:.2f} Cr"
    elif amount >= 1e5:
        text = f"{amount / 1e5:.2f} L"
    else:
        text = f"{amount:,.0f}"
    return f"{prefix}₹{text}"


def months_between(start: pd.Timestamp, end: pd.Timestamp) -> int:
    return (end.year - start.year) * 12 + end.month - start.month


def floor_to(value: float) -> float:
    return math.floor(value / ROUND_TO) * ROUND_TO


def ceil_to(value: float) -> float:
    return math.ceil(value / ROUND_TO) * ROUND_TO


def sip_analysis(raw: pd.DataFrame, as_of: pd.Timestamp) -> dict | None:
    if "Actual SIP" not in raw.columns:
        return None
    data = raw.loc[raw["Actual SIP"] > 0, ["Date", "Actual SIP"]].rename(columns={"Actual SIP": "sip"})
    if data.empty:
        return None

    steps, previous, change_month = [], None, data.iloc[0]["Date"]
    for row in data.itertuples():
        if previous is not None and row.sip != previous:
            steps.append({
                "month": row.Date.strftime("%b %Y"), "from": float(previous), "to": float(row.sip),
                "pct": (row.sip / previous - 1) * 100, "gap_months": months_between(change_month, row.Date),
                "date": row.Date.strftime("%Y-%m-%d"),
            })
            change_month = row.Date
        previous = row.sip

    first, current = data.iloc[0], data.iloc[-1]
    span = max(months_between(first["Date"], current["Date"]), 1)
    cagr = ((current["sip"] / first["sip"]) ** (12 / span) - 1) * 100 if first["sip"] else None

    # Year-end SIP vs previous year-end, so years without a raise show 0%.
    year_end = data.groupby(data["Date"].dt.year)["sip"].last()
    yearly = []
    for year, sip in year_end.items():
        before = year_end.get(year - 1)
        yearly.append({"year": int(year), "sip": float(sip),
                       "pct": None if before is None else (sip / before - 1) * 100})

    year_ago = as_of - pd.DateOffset(years=1)
    earlier = data[data["Date"] <= year_ago]
    last_12m_pct = (current["sip"] / earlier.iloc[-1]["sip"] - 1) * 100 if not earlier.empty else None
    pcts = [s["pct"] for s in steps]
    gaps = [s["gap_months"] for s in steps]
    return {
        "current": float(current["sip"]), "first": float(first["sip"]), "first_month": first["Date"].strftime("%b %Y"),
        "cagr": cagr, "steps": steps, "yearly": yearly,
        "avg_step_pct": sum(pcts) / len(pcts) if pcts else None,
        "median_step_pct": float(pd.Series(pcts).median()) if pcts else None,
        "avg_gap_months": sum(gaps) / len(gaps) if gaps else None,
        "months_since_raise": months_between(change_month, as_of),
        "last_raise_month": change_month.strftime("%b %Y") if steps else None,
        "last_12m_pct": last_12m_pct,
        "series_months": data["Date"].dt.strftime("%Y-%m-%d").tolist(),
        "series_sip": data["sip"].astype(float).tolist(),
    }


def liquid_analysis(raw: pd.DataFrame, gain_by_month: pd.Series, as_of: pd.Timestamp) -> dict | None:
    if "Withdrawal" not in raw.columns or "Deposit" not in raw.columns:
        return None
    flows = raw[["Date", "Withdrawal", "Deposit"]].copy().fillna({"Withdrawal": 0.0, "Deposit": 0.0})
    if not (flows["Withdrawal"].any() or flows["Deposit"].any()):
        return None
    # Deposit adds to the MF month and Withdrawal reduces it. Net liquid flow is the mirror image:
    # a positive value means money was parked in the liquid fund, a negative one means it was drawn.
    flows["net"] = flows["Withdrawal"] - flows["Deposit"]
    flows["balance"] = flows["net"].cumsum()
    flows["year"] = flows["Date"].dt.year

    yearly = [{"year": int(y), "deposit": float(g["Deposit"].sum()), "withdrawal": float(g["Withdrawal"].sum()),
               "net": float(g["net"].sum())} for y, g in flows.groupby("year")]
    year_ago = as_of - pd.DateOffset(years=1)
    recent = flows[flows["Date"] > year_ago]
    prior = flows[(flows["Date"] > year_ago - pd.DateOffset(years=1)) & (flows["Date"] <= year_ago)]

    deposit_rows = flows[flows["Deposit"] > 0]
    withdrawal_rows = flows[flows["Withdrawal"] > 0]
    gains = deposit_rows["Date"].map(gain_by_month).dropna()
    previous_gain = deposit_rows["Date"].map(lambda d: gain_by_month.get(d - pd.DateOffset(months=1))).dropna()
    base_down = float((gain_by_month < 0).mean() * 100) if len(gain_by_month) else None
    dip_deposits = float((gains < 0).mean() * 100) if len(gains) else None
    after_dip = float((previous_gain < 0).mean() * 100) if len(previous_gain) else None
    first_month = None
    active = flows[(flows["Withdrawal"] > 0) | (flows["Deposit"] > 0)]
    if not active.empty:
        first_month = active.iloc[0]["Date"].strftime("%b %Y")
    return {
        "deposit_total": float(flows["Deposit"].sum()), "withdrawal_total": float(flows["Withdrawal"].sum()),
        "net_total": float(flows["net"].sum()),
        "deposit_12m": float(recent["Deposit"].sum()), "withdrawal_12m": float(recent["Withdrawal"].sum()),
        "net_12m": float(recent["net"].sum()),
        "deposit_prior_12m": float(prior["Deposit"].sum()), "withdrawal_prior_12m": float(prior["Withdrawal"].sum()),
        "deposit_months_12m": int((recent["Deposit"] > 0).sum()), "withdrawal_months_12m": int((recent["Withdrawal"] > 0).sum()),
        "avg_deposit": float(deposit_rows["Deposit"].mean()) if len(deposit_rows) else 0.0,
        "avg_withdrawal": float(withdrawal_rows["Withdrawal"].mean()) if len(withdrawal_rows) else 0.0,
        "deposit_count": int(len(deposit_rows)), "withdrawal_count": int(len(withdrawal_rows)),
        "dip_deposits_pct": dip_deposits, "after_dip_pct": after_dip, "base_down_pct": base_down,
        "first_month": first_month,
        "yearly": yearly,
        "months": flows["Date"].dt.strftime("%Y-%m-%d").tolist(),
        "deposit": flows["Deposit"].astype(float).tolist(),
        "withdrawal": flows["Withdrawal"].astype(float).tolist(),
        "balance": flows["balance"].astype(float).tolist(),
    }


def cash_flow_context(raw: pd.DataFrame, income: pd.DataFrame | None, expenses: pd.DataFrame | None,
                      as_of: pd.Timestamp) -> dict | None:
    if income is None or expenses is None or income.empty or expenses.empty:
        return None
    end = min(income["Month"].max(), as_of)
    months = pd.date_range(end=end, periods=12, freq="MS")
    inc = income.groupby("Month")["Amount"].sum().reindex(months)
    if inc.notna().sum() < 6:
        return None
    exp = expenses.groupby("Month")["Amount"].sum().reindex(months).fillna(0.0)
    used = inc.dropna().index
    invested = raw.assign(month=raw["Date"].dt.to_period("M").dt.to_timestamp()) \
        .groupby("month")["Actual Monthly Investment"].sum().reindex(used).fillna(0.0)
    avg_income, avg_expense = float(inc[used].mean()), float(exp[used].mean())
    return {
        "from": used.min().strftime("%b %Y"), "to": used.max().strftime("%b %Y"), "months": int(len(used)),
        "avg_income": avg_income, "avg_expense": avg_expense, "avg_invested": float(invested.mean()),
        "surplus": avg_income - avg_expense,
        "heavy_expense": float(exp[used].quantile(0.75)),
    }


def sip_plan(sip: dict, cash: dict | None, raw: pd.DataFrame, as_of: pd.Timestamp) -> dict:
    current = sip["current"]
    recent = raw[raw["Date"] > as_of - pd.DateOffset(years=1)]
    avg_actual = float(recent["Actual Monthly Investment"].mean()) if recent["Actual Monthly Investment"].notna().any() else current

    candidates = {}
    if cash and cash["surplus"] > current:
        candidates["Fits your salary surplus"] = floor_to(cash["surplus"])
    candidates["Gentle +10% step"] = ceil_to(current * 1.10)
    if avg_actual > current:
        candidates["Match what you really invest"] = floor_to(avg_actual)
    options = []
    for label, amount in candidates.items():
        if amount <= current:
            continue
        gap = amount - cash["surplus"] if cash else None
        options.append({"label": label, "sip": amount, "extra": amount - current, "pct": (amount / current - 1) * 100,
                        "income_share": amount / cash["avg_income"] * 100 if cash else None,
                        "gap": gap, "fits": None if gap is None else gap <= 0})
    options.sort(key=lambda o: o["sip"])
    # Several rules can land on the same amount; keep the first label for each.
    seen, unique = set(), []
    for option in options:
        if option["sip"] not in seen:
            seen.add(option["sip"])
            unique.append(option)
    return {"current": current, "avg_actual": avg_actual, "options": unique, "cash": cash}


def build_sip_liquid(raw: pd.DataFrame, gain_by_month: pd.Series, as_of: pd.Timestamp,
                     income: pd.DataFrame | None, expenses: pd.DataFrame | None) -> dict:
    sip = sip_analysis(raw, as_of)
    liquid = liquid_analysis(raw, gain_by_month, as_of)
    cash = cash_flow_context(raw, income, expenses, as_of)
    plan = sip_plan(sip, cash, raw, as_of) if sip else None
    insights, notes = [], []

    if sip:
        steps = sip["steps"]
        recent_steps = ", ".join(f"{s['month']} ({s['pct']:+.0f}%)" for s in steps[-3:])
        text = (f"Your SIP grew from {inr(sip['first'])} in {sip['first_month']} to {inr(sip['current'])}, about "
                f"{sip['cagr']:.0f}% a year. You raised it {len(steps)} times, on average {sip['avg_step_pct']:.0f}% "
                f"each time, roughly every {sip['avg_gap_months']:.0f} months. Latest raises: {recent_steps}.") if steps else (
            f"Your SIP has stayed at {inr(sip['current'])} since {sip['first_month']}.")
        insights.append({"tone": "good", "title": "SIP step-up history", "text": text})
        if steps:
            overdue = sip["months_since_raise"] > (sip["avg_gap_months"] or 0)
            insights.append({
                "tone": "warn" if overdue else "neutral", "title": "Time since last raise",
                "text": f"The last raise was {sip['last_raise_month']}, {sip['months_since_raise']} months ago "
                        f"(your usual gap is {sip['avg_gap_months']:.0f} months). The SIP is "
                        f"{'flat' if not sip['last_12m_pct'] else f'up {sip['last_12m_pct']:.1f}%'} over the last 12 months."})
            trend = [s["pct"] for s in steps]
            if len(trend) >= 3 and trend[-1] < sum(trend[:-1]) / (len(trend) - 1):
                insights.append({"tone": "warn", "title": "Raises are getting smaller",
                                 "text": f"Your latest raise was {trend[-1]:+.0f}% against an earlier average of "
                                         f"{sum(trend[:-1]) / (len(trend) - 1):.0f}%. Percentage steps naturally shrink as the base grows."})

    if liquid:
        insights.append({
            "tone": "neutral", "title": "Liquid fund activity",
            "text": f"Since {liquid['first_month']} you made {liquid['deposit_count']} deposits "
                    f"(average {inr(liquid['avg_deposit'])}) and {liquid['withdrawal_count']} withdrawals "
                    f"(average {inr(liquid['avg_withdrawal'])}). Net, {inr(abs(liquid['net_total']))} "
                    f"{'more went into' if liquid['net_total'] < 0 else 'more came out of'} the mutual funds than left them."})
        insights.append({
            "tone": "warn" if liquid["net_12m"] < 0 else "good", "title": "Last 12 months in liquid",
            "text": f"You deposited {inr(liquid['deposit_12m'])} in {liquid['deposit_months_12m']} months and withdrew "
                    f"{inr(liquid['withdrawal_12m'])} in {liquid['withdrawal_months_12m']} months. The year before it was "
                    f"{inr(liquid['deposit_prior_12m'])} deposited and {inr(liquid['withdrawal_prior_12m'])} withdrawn."})
        if liquid["dip_deposits_pct"] is not None and liquid["base_down_pct"] is not None:
            insights.append({
                "tone": "neutral", "title": "Do you top up on dips?",
                "text": f"{liquid['dip_deposits_pct']:.0f}% of your deposits were in months the market fell, against "
                        f"{liquid['base_down_pct']:.0f}% of all months. "
                        f"{liquid['after_dip_pct']:.0f}% came the month after a fall."})

    if plan and plan["options"]:
        best = plan["options"][0]
        text = (f"Over the last 12 months you actually put in {inr(plan['avg_actual'])} a month against a "
                f"{inr(plan['current'])} SIP, so about {inr(plan['avg_actual'] - plan['current'])} a month comes from "
                f"top-ups.")
        if cash:
            gap_text = (f" Your salary left about {inr(cash['surplus'])} a month after expenses ({cash['from']} to {cash['to']}), "
                        f"so a SIP above that has to be funded from the liquid fund or other savings.")
            text += gap_text
        text += f" The most comfortable next step is {inr(best['sip'])} ({best['pct']:+.1f}%)."
        insights.append({"tone": "good", "title": "How much can the SIP go up?", "text": text})
    elif plan and cash:
        insights.append({
            "tone": "warn", "title": "How much can the SIP go up?",
            "text": f"Your SIP of {inr(plan['current'])} already uses all of the {inr(cash['surplus'])} monthly salary "
                    f"surplus. A higher SIP needs lower expenses or higher income."})

    if cash:
        notes.append(f"Affordability uses your Income and Expense sheets for {cash['from']} to {cash['to']}: average income "
                     f"{inr(cash['avg_income'])}, average expenses {inr(cash['avg_expense'])}. Irregular heavy months can swing this.")
    else:
        notes.append("Add data to the Income and Expense sheets to get a salary-based affordability check for the SIP.")
    notes.append("Withdrawal and Deposit are read the way your sheet does: Actual Monthly Investment = SIP + Deposit − Withdrawal.")

    if sip:
        check = raw.dropna(subset=["Actual SIP", "Actual Monthly Investment"]).copy()
        check["expected"] = check["Actual SIP"] + check["Deposit"].fillna(0) - check["Withdrawal"].fillna(0)
        off = check[(check["expected"] - check["Actual Monthly Investment"]).abs() > 1]
        if len(off):
            notes.append("Actual Monthly Investment does not equal SIP + Deposit − Withdrawal for: "
                         + ", ".join(off["Date"].dt.strftime("%b %Y")) + ".")

    return {"sip": sip, "liquid": liquid, "plan": plan, "insights": insights, "notes": notes}
