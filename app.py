from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pandas as pd
from flask import Flask, flash, jsonify, redirect, render_template, request, url_for

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
ALLOWED_EXTENSIONS = {".xlsx", ".xls"}
REQUIRED_COLUMNS = {
    "Id", "SNo", "Year-Month", "Date", "Expense", "ExpenseGroup",
    "Amount", "PaymentGroup", "Remark",
}
INVESTMENT_COLUMNS = {"ID", "SNo", "Year-Month", "Date", "Investment", "Group", "Amount", "Remark"}
INCOME_COLUMNS = {"ID", "SNo", "Year-Month", "Date", "Income", "Group", "Amount"}


def clean_column_name(value: object) -> str:
    return str(value).replace("\ufeff", "").strip()


def read_workbook_table(workbook: Path, required_columns: set[str] = REQUIRED_COLUMNS) -> pd.DataFrame:
    sheets = pd.read_excel(workbook, sheet_name=None, header=None)
    for sheet_name, raw in sheets.items():
        for header_row, row in raw.iterrows():
            columns = [clean_column_name(value) for value in row.tolist()]
            if required_columns.issubset(columns):
                frame = raw.iloc[header_row + 1:].copy()
                frame.columns = columns
                return frame.loc[:, columns]

    sheet_details = []
    for sheet_name, raw in sheets.items():
        preview = [clean_column_name(value) for value in raw.iloc[0].tolist()] if not raw.empty else []
        sheet_details.append(f"{sheet_name}: {', '.join(preview[:9]) or 'empty'}")
    raise ValueError(
        "Could not find the required header row. Expected columns: "
        f"{', '.join(sorted(required_columns))}. Sheets found: {'; '.join(sheet_details)}"
    )

app = Flask(__name__)
app.config["SECRET_KEY"] = "expense-dashboard-local"
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024


def latest_workbook() -> Path | None:
    files = [path for path in UPLOAD_DIR.iterdir() if path.suffix.lower() in ALLOWED_EXTENSIONS]
    return max(files, key=lambda path: path.stat().st_mtime) if files else None


def replace_active_workbook(uploaded, suffix: str) -> Path:
    temporary = UPLOAD_DIR / f".uploading-{uuid4().hex}{suffix}"
    uploaded.save(temporary)
    try:
        read_workbook_table(temporary)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    active = UPLOAD_DIR / f"Expense{suffix}"
    for workbook in UPLOAD_DIR.iterdir():
        if workbook.suffix.lower() in ALLOWED_EXTENSIONS and workbook != temporary:
            workbook.unlink()
    temporary.replace(active)
    return active


def read_expenses() -> pd.DataFrame:
    workbook = latest_workbook()
    if workbook is None:
        return pd.DataFrame(columns=["Date", "Amount", "ExpenseGroup", "PaymentGroup", "Remark"])

    frame = read_workbook_table(workbook)
    frame.columns = [clean_column_name(column) for column in frame.columns]
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"Missing columns: {', '.join(sorted(missing))}")

    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    frame["Amount"] = pd.to_numeric(frame["Amount"], errors="coerce")
    frame = frame.dropna(subset=["Date", "Amount"]).copy()
    frame["ExpenseGroup"] = frame["ExpenseGroup"].fillna("Uncategorized").astype(str)
    frame["PaymentGroup"] = frame["PaymentGroup"].fillna("Other").astype(str)
    frame["Remark"] = frame["Remark"].fillna("").astype(str)
    frame["Month"] = frame["Date"].dt.to_period("M").dt.to_timestamp()
    return frame


def read_investments() -> pd.DataFrame:
    workbook = latest_workbook()
    if workbook is None:
        return pd.DataFrame(columns=["Date", "Amount", "Investment", "Group", "Month"])

    try:
        frame = read_workbook_table(workbook, INVESTMENT_COLUMNS)
    except ValueError:
        return pd.DataFrame(columns=["Date", "Amount", "Investment", "Group", "Month"])

    frame = frame.rename(columns={"ID": "Id"})
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    frame["Amount"] = pd.to_numeric(frame["Amount"], errors="coerce")
    frame = frame.dropna(subset=["Date", "Amount"]).copy()
    frame["Investment"] = frame["Investment"].fillna("Investment").astype(str)
    frame["Group"] = frame["Group"].fillna("Other").astype(str)
    frame["Month"] = frame["Date"].dt.to_period("M").dt.to_timestamp()
    return frame


def read_income() -> pd.DataFrame:
    workbook = latest_workbook()
    empty = pd.DataFrame(columns=["Date", "Amount", "Income", "Group", "Month"])
    if workbook is None:
        return empty

    try:
        frame = read_workbook_table(workbook, INCOME_COLUMNS)
    except ValueError:
        return empty

    frame = frame.rename(columns={"ID": "Id"})
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    frame["Amount"] = pd.to_numeric(frame["Amount"], errors="coerce")
    frame = frame.dropna(subset=["Date", "Amount"]).copy()
    frame["Income"] = frame["Income"].fillna("Income").astype(str)
    frame["Group"] = frame["Group"].fillna("Other").astype(str)
    frame["Month"] = frame["Date"].dt.to_period("M").dt.to_timestamp()
    return frame


def filtered_expenses() -> tuple[pd.DataFrame, pd.Timestamp | None, pd.Timestamp | None]:
    frame = read_expenses()
    if frame.empty:
        return frame, None, None

    latest = frame["Date"].max().normalize()
    default_start = (latest - pd.DateOffset(months=11)).replace(day=1)
    start = pd.to_datetime(request.args.get("start"), errors="coerce")
    end = pd.to_datetime(request.args.get("end"), errors="coerce")
    start = start if not pd.isna(start) else default_start
    end = end if not pd.isna(end) else latest
    selected = frame[frame["Date"].between(start, end)].copy()

    group = request.args.get("group")
    payment = request.args.get("payment")
    if group:
        selected = selected[selected["ExpenseGroup"] == group]
    if payment:
        selected = selected[selected["PaymentGroup"] == payment]
    return selected, start, end


def yearly_series(frame: pd.DataFrame, start_year: int, end_year: int) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype="float64")
    selected = frame[frame["Date"].dt.year.between(start_year, end_year)]
    return selected.groupby(selected["Date"].dt.year)["Amount"].sum()


@app.get("/")
def index():
    try:
        frame = read_expenses()
        error = None
    except ValueError as exc:
        frame = pd.DataFrame()
        error = str(exc)
    return render_template("index.html", workbook=latest_workbook(), error=error)


@app.post("/upload")
def upload():
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        flash("Choose an Excel workbook before uploading.", "error")
        return redirect(url_for("index"))
    suffix = Path(uploaded.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        flash("Only .xlsx and .xls files are supported.", "error")
        return redirect(url_for("index"))

    try:
        destination = replace_active_workbook(uploaded, suffix)
    except (ValueError, ImportError) as exc:
        flash(f"That workbook could not be imported: {exc}", "error")
    else:
        flash(f"Imported {destination.name} successfully.", "success")
    return redirect(url_for("index"))


@app.get("/api/dashboard")
def dashboard():
    try:
        frame, start, end = filtered_expenses()
        all_data = read_expenses()
        investment_data = read_investments()
        income_data = read_income()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if frame.empty:
        return jsonify({
            "empty": True,
            "has_data": not all_data.empty,
            "start": start.strftime("%Y-%m-%d") if start is not None else "",
            "end": end.strftime("%Y-%m-%d") if end is not None else "",
            "groups": sorted(all_data["ExpenseGroup"].unique().tolist()) if not all_data.empty else [],
            "payments": sorted(all_data["PaymentGroup"].unique().tolist()) if not all_data.empty else [],
        })

    monthly = frame.groupby("Month", as_index=False)["Amount"].sum().sort_values("Month")
    start_month = start.to_period("M").to_timestamp()
    end_month = end.to_period("M").to_timestamp()
    selected_investments = investment_data[investment_data["Month"].between(start_month, end_month)]
    investment_monthly = selected_investments.groupby("Month")["Amount"].sum()
    selected_income = income_data[income_data["Month"].between(start_month, end_month)]
    income_monthly = selected_income.groupby("Month")["Amount"].sum()
    year_frames = [all_data["Date"].dt.year.dropna().astype(int)]
    if not investment_data.empty:
        year_frames.append(investment_data["Date"].dt.year.dropna().astype(int))
    if not income_data.empty:
        year_frames.append(income_data["Date"].dt.year.dropna().astype(int))
    available_years = pd.concat(year_frames).drop_duplicates().sort_values()
    latest_year = int(available_years.max())
    requested_start_year = request.args.get("year_start", type=int)
    requested_end_year = request.args.get("year_end", type=int)
    end_year = requested_end_year if requested_end_year is not None else latest_year
    start_year = requested_start_year if requested_start_year is not None else end_year - 9
    start_year, end_year = min(start_year, end_year), max(start_year, end_year)
    years = list(range(start_year, end_year + 1))
    yearly_expenses = yearly_series(all_data, start_year, end_year)
    yearly_investments = yearly_series(investment_data, start_year, end_year)
    yearly_income = yearly_series(income_data, start_year, end_year)
    by_group = frame.groupby("ExpenseGroup", as_index=False)["Amount"].sum().sort_values("Amount", ascending=False)
    by_payment = frame.groupby("PaymentGroup", as_index=False)["Amount"].sum().sort_values("Amount", ascending=False)
    peak = monthly.loc[monthly["Amount"].idxmax()]
    months = max(monthly["Month"].nunique(), 1)
    records = frame.sort_values("Date", ascending=False).copy()
    records["Date"] = records["Date"].dt.strftime("%Y-%m-%d")
    record_columns = ["Id", "SNo", "Year-Month", "Date", "Expense", "ExpenseGroup", "Amount", "PaymentGroup", "Remark"]
    records = records[record_columns].where(pd.notna(records[record_columns]), "")
    records["Amount"] = pd.to_numeric(records["Amount"], errors="coerce").round(2)

    return jsonify({
        "empty": False,
        "has_data": True,
        "start": start.strftime("%Y-%m-%d"),
        "end": end.strftime("%Y-%m-%d"),
        "total": round(float(frame["Amount"].sum()), 2),
        "average": round(float(frame["Amount"].sum()) / months, 2),
        "peak_month": peak["Month"].strftime("%b %Y"),
        "peak_amount": round(float(peak["Amount"]), 2),
        "months": [item.strftime("%b %Y") for item in monthly["Month"]],
        "monthly": [round(float(item), 2) for item in monthly["Amount"]],
        "investment_available": not investment_data.empty,
        "investment_monthly": [round(float(investment_monthly.get(month, 0)), 2) for month in monthly["Month"]],
        "income_available": not income_data.empty,
        "income_months": [month.strftime("%b %Y") for month in income_monthly.index],
        "income_monthly": [round(float(amount), 2) for amount in income_monthly],
        "years": years,
        "yearly_expenses": [round(float(yearly_expenses.get(year, 0)), 2) for year in years],
        "yearly_investments": [round(float(yearly_investments.get(year, 0)), 2) for year in years],
        "yearly_income": [round(float(yearly_income.get(year, 0)), 2) for year in years],
        "year_start": start_year,
        "year_end": end_year,
        "available_year_start": int(available_years.min()),
        "available_year_end": int(available_years.max()),
        "groups": sorted(all_data["ExpenseGroup"].unique().tolist()),
        "payments": sorted(all_data["PaymentGroup"].unique().tolist()),
        "group_labels": by_group["ExpenseGroup"].tolist(),
        "group_values": [round(float(item), 2) for item in by_group["Amount"]],
        "payment_labels": by_payment["PaymentGroup"].tolist(),
        "payment_values": [round(float(item), 2) for item in by_payment["Amount"]],
        "records": records.to_dict(orient="records"),
    })


if __name__ == "__main__":
    app.run(debug=True)
