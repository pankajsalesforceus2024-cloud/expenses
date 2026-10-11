# Ledgerline expense dashboard

A small Flask and pandas dashboard for visualizing `Expense.xlsx` workbooks.

## Run locally

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
py app.py
```

Open http://127.0.0.1:5000. Use the import control to upload an `.xlsx` or `.xls` file. Uploaded workbooks are saved in `uploads/`; the most recently uploaded workbook is used.

The workbook must contain these columns: `Id`, `SNo`, `Year-Month`, `Date`, `Expense`, `ExpenseGroup`, `Amount`, `PaymentGroup`, and `Remark`. Amounts are grouped by month from `Date`. The initial view uses the latest 12 months present in the workbook. Filters can narrow the date range, expense category, or payment group.
