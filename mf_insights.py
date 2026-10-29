from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from sip_liquid import build_sip_liquid, inr
from workbook_cache import cached_sheets

SHEET_NAME = "MonthlyMF"
REQUIRED = {"Date", "Invested Amount", "Current Value"}


def xirr(flows: list[tuple[pd.Timestamp, float]]) -> float | None:
    if len(flows) < 2 or not any(a < 0 for _, a in flows) or not any(a > 0 for _, a in flows):
        return None
    start = flows[0][0]
    years = [((d - start).days / 365.0, a) for d, a in flows]

    def npv(rate: float) -> float:
        return sum(a / (1 + rate) ** t for t, a in years)

    low, high = -0.95, 10.0
    if npv(low) * npv(high) > 0:
        return None
    for _ in range(200):
        mid = (low + high) / 2
        if npv(low) * npv(mid) <= 0:
            high = mid
        else:
            low = mid
    return (low + high) / 2


def num(value) -> float | None:
    return None if value is None or pd.isna(value) else float(value)


def load_sheet(workbook: Path) -> pd.DataFrame | None:
    sheet = cached_sheets(workbook).get(SHEET_NAME)
    if sheet is None or sheet.empty:
        return None
    raw = sheet.iloc[1:].copy()
    raw.columns = [str(c).strip() for c in sheet.iloc[0]]
    if not REQUIRED.issubset(raw.columns):
        return None
    for column in ("Invested Amount", "Current Value", "Actual Monthly Investment",
                   "Withdrawal", "Deposit", "Annual Return", "Actual SIP"):
        raw[column] = pd.to_numeric(raw[column], errors="coerce") if column in raw.columns else float("nan")
    raw["Date"] = pd.to_datetime(raw["Date"], errors="coerce")
    if "Month" in raw.columns:
        # Month is the period the row describes; fall back to one month before Date when blank.
        month = pd.to_datetime(raw["Month"], errors="coerce")
        raw["Date"] = month.fillna(raw["Date"] - pd.DateOffset(months=1))
    return raw.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)


def build_mf_insights(workbook: Path, income: pd.DataFrame | None = None,
                      expenses: pd.DataFrame | None = None) -> dict:
    raw = load_sheet(workbook)
    if raw is None:
        return {"available": False,
                "error": f"Sheet '{SHEET_NAME}' with columns Date, Invested Amount and Current Value was not found."}

    # Recompute flows and gains from balances. The sheet's own "Monthly Investment" is an
    # absolute change, so it cannot tell a withdrawal from a contribution.
    frame = raw.dropna(subset=["Invested Amount", "Current Value"]).copy()
    frame["flow"] = frame["Invested Amount"].diff()
    frame["gain"] = frame["Current Value"].diff() - frame["flow"]
    frame["gain_pct"] = frame["gain"] / frame["Current Value"].shift(1) * 100
    frame["profit"] = frame["Current Value"] - frame["Invested Amount"]
    frame["year"] = frame["Date"].dt.year
    moves = frame.iloc[1:]

    first, last = frame.iloc[0], frame.iloc[-1]
    invested, value = float(last["Invested Amount"]), float(last["Current Value"])
    profit = value - invested

    flows = [(first["Date"], -float(first["Current Value"]))]
    flows += [(r.Date, -float(r.flow)) for r in moves.itertuples() if r.flow]
    flows.append((last["Date"], value))
    overall_xirr = xirr(flows)

    year_ago = last["Date"] - pd.DateOffset(years=1)
    base = frame[frame["Date"] <= year_ago]
    trailing = None
    trailing_gain = trailing_flow = None
    if not base.empty:
        anchor = base.iloc[-1]
        window = frame[frame["Date"] > anchor["Date"]]
        trailing_flows = [(anchor["Date"], -float(anchor["Current Value"]))]
        trailing_flows += [(r.Date, -float(r.flow)) for r in window.itertuples() if r.flow]
        trailing_flows.append((last["Date"], value))
        trailing = xirr(trailing_flows)
        trailing_gain = float(window["gain"].sum())
        trailing_flow = float(window["flow"].sum())

    peak_idx = frame["Current Value"].idxmax()
    peak = frame.loc[peak_idx]
    drawdown = (value / float(peak["Current Value"]) - 1) * 100
    worst = moves.loc[moves["gain"].idxmin()]
    best = moves.loc[moves["gain"].idxmax()]
    up_share = float((moves["gain"] > 0).mean() * 100)

    years = []
    for year, group in frame.groupby("year"):
        before = frame[frame["Date"] < group["Date"].min()]
        start_value = float(before.iloc[-1]["Current Value"]) if not before.empty else float(group.iloc[0]["Current Value"])
        group_moves = group if not before.empty else group.iloc[1:]
        net = float(group_moves["flow"].sum())
        gain = float(group_moves["gain"].sum())
        denominator = start_value + net / 2
        years.append({
            "year": int(year),
            "net_invested": net,
            "gain": gain,
            "end_value": float(group.iloc[-1]["Current Value"]),
            "return_pct": gain / denominator * 100 if denominator else None,
            "partial": bool(before.empty or len(group) < 12),
        })
    full_years = [y for y in years if y["return_pct"] is not None and not y["partial"]]
    best_year = max(full_years, key=lambda y: y["return_pct"], default=None)
    worst_year = min(full_years, key=lambda y: y["return_pct"], default=None)

    recent = frame.tail(12)
    actual = raw["Actual Monthly Investment"]
    recent_sip = raw.tail(12)["Actual Monthly Investment"]
    earlier_sip = raw.iloc[-24:-12]["Actual Monthly Investment"]
    last_year_raw = raw[raw["Date"] > year_ago]

    milestones = []
    for target in (1e6, 5e6, 1e7, 1.5e7):
        hit = frame[frame["Current Value"] >= target]
        if not hit.empty:
            milestones.append({"label": inr(target), "month": hit.iloc[0]["Date"].strftime("%b %Y")})

    reported = raw.dropna(subset=["Annual Return"])
    insights = []
    insights.append({
        "tone": "good" if profit >= 0 else "bad", "title": "Overall position",
        "text": f"You have invested {inr(invested)} and the portfolio is worth {inr(value)}: a profit of "
                f"{inr(profit)} ({profit / invested * 100:.1f}%). Every ₹1 put in is now ₹{value / invested:.2f}."})
    if overall_xirr is not None:
        trailing_text = f" Over the last 12 months it was about {trailing * 100:.1f}%." if trailing is not None else ""
        insights.append({
            "tone": "good" if overall_xirr >= 0 else "bad", "title": "Annualised return",
            "text": f"Accounting for when each rupee went in, the estimated return since {first['Date']:%b %Y} is "
                    f"{overall_xirr * 100:.1f}% a year.{trailing_text}"})
    insights.append({
        "tone": "warn" if drawdown < -2 else "good", "title": "Distance from peak",
        "text": f"The portfolio peaked at {inr(float(peak['Current Value']))} in {peak['Date']:%b %Y}. "
                f"It is currently {abs(drawdown):.1f}% {'below' if drawdown < 0 else 'at'} that peak."})
    latest_move = moves.iloc[-1]
    insights.append({
        "tone": "good" if latest_move["gain"] >= 0 else "bad", "title": f"Latest month ({last['Date']:%b %Y})",
        "text": f"Markets moved your holdings by {inr(float(latest_move['gain']), True)} "
                f"({latest_move['gain_pct']:+.1f}%) while you added {inr(float(latest_move['flow']))}."})
    insights.append({
        "tone": "neutral", "title": "Consistency",
        "text": f"{up_share:.0f}% of months ended with a market gain. Best month: {best['Date']:%b %Y} "
                f"({inr(float(best['gain']), True)}). Worst month: {worst['Date']:%b %Y} ({inr(float(worst['gain']), True)})."})
    if best_year and worst_year:
        insights.append({
            "tone": "neutral", "title": "Best and worst full years",
            "text": f"{best_year['year']} was the strongest year at about {best_year['return_pct']:.1f}%; "
                    f"{worst_year['year']} was the weakest at about {worst_year['return_pct']:.1f}%."})
    if recent_sip.notna().any() and earlier_sip.notna().any():
        now_avg, then_avg = float(recent_sip.mean()), float(earlier_sip.mean())
        insights.append({
            "tone": "good" if now_avg >= then_avg else "warn", "title": "Total monthly investing",
            "text": f"Including top-ups and withdrawals you averaged {inr(now_avg)} a month over the last 12 months, "
                    f"{'up' if now_avg >= then_avg else 'down'} from {inr(then_avg)} the year before."})
    market_share = profit / value * 100 if value else 0
    insights.append({
        "tone": "neutral", "title": "Where the value comes from",
        "text": f"{market_share:.0f}% of today's value is market growth and {100 - market_share:.0f}% is money you put in."})
    if len(reported):
        top, bottom = reported.loc[reported["Annual Return"].idxmax()], reported.loc[reported["Annual Return"].idxmin()]
        insights.append({
            "tone": "neutral", "title": "Annual return column",
            "text": f"Your sheet's own figure is {float(reported.iloc[-1]['Annual Return']):.1f}% now, "
                    f"peaking at {float(top['Annual Return']):.1f}% ({top['Date']:%b %Y}) and bottoming at "
                    f"{float(bottom['Annual Return']):.1f}% ({bottom['Date']:%b %Y})."})

    notes = ["The sheet holds typed values, not formulas, so everything shown is derived from the Invested Amount and Current Value columns."]
    missing = raw[raw["Invested Amount"].isna() | raw["Current Value"].isna()]
    if len(missing):
        notes.append("Months with missing balances (their change is rolled into the next month): "
                     + ", ".join(missing["Date"].dt.strftime("%b %Y")) + ".")
    gaps = raw[raw["Annual Return"].isna() & (raw["Date"] > reported["Date"].min())] if len(reported) else raw.iloc[0:0]
    if len(gaps):
        notes.append("Annual Return is blank for: " + ", ".join(gaps["Date"].dt.strftime("%b %Y")) + ".")
    notes.append("Gain = change in value minus money added. Annualised return is a money-weighted estimate. This is analysis of your own data, not financial advice.")

    extra = build_sip_liquid(raw, frame.set_index("Date")["gain"].dropna(), last["Date"], income, expenses)
    insights.extend(extra["insights"])
    notes = extra["notes"] + notes

    return {
        "available": True,
        "sip": extra["sip"], "liquid": extra["liquid"], "plan": extra["plan"],
        "as_of": last["Date"].strftime("%b %Y"),
        "since": first["Date"].strftime("%b %Y"),
        "kpis": {
            "value": value, "invested": invested, "profit": profit,
            "profit_pct": profit / invested * 100, "xirr": None if overall_xirr is None else overall_xirr * 100,
            "trailing_xirr": None if trailing is None else trailing * 100,
            "drawdown": drawdown, "peak_value": float(peak["Current Value"]), "peak_month": peak["Date"].strftime("%b %Y"),
            "trailing_gain": trailing_gain, "trailing_flow": trailing_flow,
            "withdrawal_total": float(raw["Withdrawal"].sum()), "deposit_total": float(raw["Deposit"].sum()),
            "withdrawal_12m": float(last_year_raw["Withdrawal"].sum()), "deposit_12m": float(last_year_raw["Deposit"].sum()),
        },
        "insights": insights,
        "milestones": milestones,
        "notes": notes,
        "years": years,
        "series": {
            "months": frame["Date"].dt.strftime("%Y-%m-%d").tolist(),
            "invested": frame["Invested Amount"].round(2).tolist(),
            "value": frame["Current Value"].round(2).tolist(),
            "profit": frame["profit"].round(2).tolist(),
            "gain_months": moves["Date"].dt.strftime("%Y-%m-%d").tolist(),
            "gain": moves["gain"].round(2).tolist(),
            "reported_months": reported["Date"].dt.strftime("%Y-%m-%d").tolist(),
            "reported_return": reported["Annual Return"].tolist(),
        },
        "generated": date.today().isoformat(),
    }
