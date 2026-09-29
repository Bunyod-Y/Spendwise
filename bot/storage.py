"""Excel storage: one .xlsx per month (Date | Time | Amount | Reason).

Callers work with a single `datetime`; it is split into the Date and Time
columns on write and combined again on read.
"""
from __future__ import annotations

import io
from datetime import date, datetime, time
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.worksheet import Worksheet

HEADERS = ("Date", "Time", "Amount", "Reason")
WIDTHS = (12, 8, 16, 80)
DATE_FORMAT = "DD.MM.YYYY"
TIME_FORMAT = "HH:MM"
TOP = Alignment(vertical="top")
WRAP_TOP = Alignment(vertical="top", wrap_text=True)

Spending = tuple[datetime, float, str]


def amount_format(amount: float) -> str:
    return "#,##0" if float(amount).is_integer() else "#,##0.00"


def _setup_sheet(ws: Worksheet, title: str, headers: tuple[str, ...], widths: tuple[int, ...]) -> None:
    ws.title = title
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="DDDDDD")
    for col, width in zip("ABCDEFG", widths):
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A2"


def _read_when(day_value, time_value) -> datetime | None:
    """Combine Date and Time cell values back into one datetime."""
    if isinstance(day_value, datetime):
        day_value = day_value.date()
    if not isinstance(day_value, date):
        return None
    if isinstance(time_value, datetime):
        time_value = time_value.time()
    if not isinstance(time_value, time):
        time_value = time()
    return datetime.combine(day_value, time_value)


def _write_amount(ws: Worksheet, row: int, amount: float) -> None:
    cell = ws.cell(row=row, column=3, value=amount)
    cell.number_format = amount_format(amount)
    cell.alignment = TOP


def _write_reason(ws: Worksheet, row: int, reason: str) -> None:
    cell = ws.cell(row=row, column=4, value=reason)
    # Force plain text so reasons starting with "=" are never treated as formulas.
    cell.data_type = "s"
    cell.alignment = WRAP_TOP


def _write_row(ws: Worksheet, row: int, when: datetime, amount: float, reason: str) -> None:
    date_cell = ws.cell(row=row, column=1, value=when.date())
    date_cell.number_format = DATE_FORMAT
    date_cell.alignment = TOP
    time_cell = ws.cell(row=row, column=2, value=when.time().replace(second=0, microsecond=0))
    time_cell.number_format = TIME_FORMAT
    time_cell.alignment = TOP
    _write_amount(ws, row, amount)
    _write_reason(ws, row, reason)


def _read_row(ws: Worksheet, row: int) -> Spending:
    return (
        _read_when(ws.cell(row=row, column=1).value, ws.cell(row=row, column=2).value),
        ws.cell(row=row, column=3).value or 0,
        ws.cell(row=row, column=4).value or "",
    )


def _save(wb: Workbook, path: Path) -> None:
    # Write to a temp file then rename, so a crash never leaves a half-written file.
    tmp = path.with_name(path.name + ".tmp")
    wb.save(tmp)
    tmp.replace(path)


class SpendingStorage:
    def __init__(self, data_dir: Path):
        self.dir = data_dir / "spendings"
        self.dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, year: int, month: int) -> Path:
        return self.dir / f"{year:04d}-{month:02d}.xlsx"

    def exists(self, year: int, month: int) -> bool:
        return self.path_for(year, month).exists()

    def months(self) -> list[tuple[int, int]]:
        result = []
        for p in self.dir.glob("*.xlsx"):
            try:
                year, month = p.stem.split("-")
                result.append((int(year), int(month)))
            except ValueError:
                continue
        return sorted(result)

    def ensure(self, year: int, month: int) -> Path:
        path = self.path_for(year, month)
        if not path.exists():
            wb = Workbook()
            _setup_sheet(wb.active, f"{month:02d}.{year}", HEADERS, WIDTHS)
            _save(wb, path)
        return path

    def entries(self, year: int, month: int) -> list[Spending]:
        path = self.path_for(year, month)
        if not path.exists():
            return []
        wb = load_workbook(path, read_only=True)
        try:
            return [
                (_read_when(d, t), amount or 0, reason or "")
                for d, t, amount, reason in wb.active.iter_rows(
                    min_row=2, max_col=4, values_only=True
                )
                if d is not None or amount is not None
            ]
        finally:
            wb.close()

    def append(self, when: datetime, amount: float, reason: str) -> int:
        """Add a spending at the end of its month's file. Returns its number (1-based)."""
        path = self.ensure(when.year, when.month)
        wb = load_workbook(path)
        ws = wb.active
        row = ws.max_row + 1
        _write_row(ws, row, when, amount, reason)
        _save(wb, path)
        return row - 1

    def insert_sorted(self, when: datetime, amount: float, reason: str) -> int:
        """Add a spending in chronological position. Returns its number (1-based)."""
        path = self.ensure(when.year, when.month)
        wb = load_workbook(path)
        ws = wb.active
        row = ws.max_row + 1
        for r in range(2, ws.max_row + 1):
            existing = _read_row(ws, r)[0]
            if existing is not None and existing > when:
                row = r
                ws.insert_rows(r)
                break
        _write_row(ws, row, when, amount, reason)
        _save(wb, path)
        return row - 1

    def update(self, year: int, month: int, number: int, amount: float, reason: str) -> Spending | None:
        """Replace amount and reason of spending `number`. Returns the old one, or None."""
        path = self.path_for(year, month)
        if not path.exists():
            return None
        wb = load_workbook(path)
        ws = wb.active
        row = number + 1
        if number < 1 or row > ws.max_row:
            return None
        old = _read_row(ws, row)
        _write_amount(ws, row, amount)
        _write_reason(ws, row, reason)
        _save(wb, path)
        return old

    def delete(self, year: int, month: int, number: int | None = None) -> Spending | None:
        """Delete spending `number` (or the last one). Returns it, or None if missing."""
        path = self.path_for(year, month)
        if not path.exists():
            return None
        wb = load_workbook(path)
        ws = wb.active
        row = ws.max_row if number is None else number + 1
        if row < 2 or row > ws.max_row:
            return None
        removed = _read_row(ws, row)
        ws.delete_rows(row)
        _save(wb, path)
        return removed

    def export(self, year: int, month: int) -> tuple[bytes, int, float]:
        """The month's file with a TOTAL row and a per-day Summary sheet.

        Returns (xlsx bytes, count, total).
        """
        wb = load_workbook(self.ensure(year, month))
        ws = wb.active
        last = ws.max_row
        rows = [_read_row(ws, r) for r in range(2, last + 1)]
        total = sum(amount for _, amount, _ in rows)

        label = ws.cell(row=last + 2, column=1, value="TOTAL")
        label.font = Font(bold=True)
        total_cell = ws.cell(row=last + 2, column=3, value=total)
        total_cell.font = Font(bold=True)
        total_cell.number_format = amount_format(total)

        per_day: dict[date, float] = {}
        for when, amount, _ in rows:
            if when is not None:
                per_day[when.date()] = per_day.get(when.date(), 0) + amount
        summary = wb.create_sheet("Summary")
        _setup_sheet(summary, "Summary", ("Date", "Total"), (12, 16))
        for day in sorted(per_day):
            summary.append((day, per_day[day]))
            summary.cell(row=summary.max_row, column=1).number_format = DATE_FORMAT
            summary.cell(row=summary.max_row, column=2).number_format = amount_format(per_day[day])

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue(), len(rows), total
