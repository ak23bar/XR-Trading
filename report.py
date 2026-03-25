#!/usr/bin/env python3
#XR Trading Internship Challenge 2026
#Authored by : Akbar Aman

"""Generate team and product sales reports from three CSV inputs."""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from decimal import Decimal, InvalidOperation, getcontext

#financial arithmetic using 28 digits of precision avoiding float drift on large multiplications
getcontext().prec = 28


class ReportError(Exception):
    """Raised when input validation or report generation fails."""


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments with the required CLI shape"""
    parser = argparse.ArgumentParser(
        description="Generate team and product reports from TeamMap, ProductMaster, and Sales CSV files."
    )
    parser.add_argument("-t", required=True, help="Path to Team Map CSV")
    parser.add_argument("-p", required=True, help="Path to Product Master CSV")
    parser.add_argument("-s", required=True, help="Path to Sales CSV")
    parser.add_argument("--team-report", required=True, help="Output path for Team Report CSV")
    parser.add_argument("--product-report", required=True, help="Output path for Product Report CSV")
    return parser.parse_args()


def is_blank_row(row: list[str]) -> bool:
    """Return True when a CSV row is empty or contains only whitespace."""
    # Tolerate trailing newlines and editors that pad with empty fields
    return not row or all(cell.strip() == "" for cell in row)


def parse_positive_int(raw: str, field_name: str, context: str) -> int:
    """Parse a strictly positive integer field."""
    text = raw.strip()
    try:
        value = int(text)
    except ValueError as exc:
        raise ReportError(f"{context}: invalid {field_name} '{raw}'") from exc
    if value <= 0:
        raise ReportError(f"{context}: {field_name} must be positive")
    return value


def parse_nonnegative_decimal(raw: str, field_name: str, context: str) -> Decimal:
    """Parse a nonnegative Decimal field."""
    text = raw.strip()
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise ReportError(f"{context}: invalid {field_name} '{raw}'") from exc
    # Reject NaN and Infinity as Decimal accepts them but they ruin the arithmetic
    if not value.is_finite():
        raise ReportError(f"{context}: {field_name} must be a finite number")
    if value < 0:
        raise ReportError(f"{context}: {field_name} must be nonnegative")
    return value


def parse_positive_decimal(raw: str, field_name: str, context: str) -> Decimal:
    """Parse a strictly positive Decimal field."""
    value = parse_nonnegative_decimal(raw, field_name, context)
    if value <= 0:
        raise ReportError(f"{context}: {field_name} must be positive")
    return value


def read_team_map(path: str) -> dict[int, str]:
    """Read Team Map CSV with header TeamId,Name."""
    team_map: dict[int, str] = {}
    header_seen = False

    try:
        with open(path, "r", newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            for line_number, row in enumerate(reader, start=1):
                if is_blank_row(row):
                    continue

                if not header_seen:
                    normalized_header = list(row)
                    if normalized_header:
                        # tolerate a UTF-8 BOM in the first header cell
                        normalized_header[0] = normalized_header[0].lstrip("\ufeff")
                    if normalized_header != ["TeamId", "Name"]:
                        raise ReportError(
                            f"{path}: line {line_number}: expected header 'TeamId,Name'"
                        )
                    header_seen = True
                    continue

                context = f"{path}: line {line_number}"
                if len(row) != 2:
                    raise ReportError(f"{context}: expected 2 columns for Team Map row")

                team_id = parse_positive_int(row[0], "TeamId", context)
                team_name = row[1].strip()
                if not team_name:
                    raise ReportError(f"{context}: Name must be non-empty")
                # Duplicate ids would rewrite therefore we treat as data error
                if team_id in team_map:
                    raise ReportError(f"{context}: duplicate TeamId {team_id}")

                team_map[team_id] = team_name
    except FileNotFoundError as exc:
        raise ReportError(f"{path}: file not found") from exc
    except OSError as exc:
        raise ReportError(f"{path}: unable to read file: {exc}") from exc

    if not header_seen:
        raise ReportError(f"{path}: missing header 'TeamId,Name'")
    if not team_map:
        raise ReportError(f"{path}: no team rows found")

    return team_map


def read_product_master(path: str) -> dict[int, dict[str, object]]:
    """Read Product Master CSV with no header per spec"""
    products: dict[int, dict[str, object]] = {}

    try:
        with open(path, "r", newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            for line_number, row in enumerate(reader, start=1):
                if is_blank_row(row):
                    continue

                context = f"{path}: line {line_number}"
                if len(row) != 4:
                    raise ReportError(f"{context}: expected 4 columns for Product Master row")

                product_id = parse_positive_int(row[0], "ProductId", context)
                product_name = row[1].strip()
                if not product_name:
                    raise ReportError(f"{context}: Name must be non-empty")
                # Price is per unit; LotSize is how many units constitute one saleable lot
                price = parse_positive_decimal(row[2], "Price", context)
                lot_size = parse_positive_int(row[3], "LotSize", context)

                if product_id in products:
                    raise ReportError(f"{context}: duplicate ProductId {product_id}")

                products[product_id] = {
                    "name": product_name,
                    "price": price,
                    "lot_size": lot_size,
                }
    except FileNotFoundError as exc:
        raise ReportError(f"{path}: file not found") from exc
    except OSError as exc:
        raise ReportError(f"{path}: unable to read file: {exc}") from exc

    if not products:
        raise ReportError(f"{path}: no product rows found")

    return products


def read_sales(path: str) -> list[dict[str, object]]:
    """Read Sales CSV — no header per spec."""
    sales: list[dict[str, object]] = []
    # Track seen SaleIds to catch duplicates the same way we do for teams and products
    seen_sale_ids: set[int] = set()

    try:
        with open(path, "r", newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            for line_number, row in enumerate(reader, start=1):
                if is_blank_row(row):
                    continue

                context = f"{path}: line {line_number}"
                if len(row) != 5:
                    raise ReportError(f"{context}: expected 5 columns for Sales row")

                sale_id = parse_positive_int(row[0], "SaleId", context)
                product_id = parse_positive_int(row[1], "ProductId", context)
                team_id = parse_positive_int(row[2], "TeamId", context)
                quantity = parse_positive_int(row[3], "Quantity", context)
                # Discount of 0 is valid thus a sale can have no discount applied
                discount = parse_nonnegative_decimal(row[4], "Discount", context)

                if sale_id in seen_sale_ids:
                    raise ReportError(f"{context}: duplicate SaleId {sale_id}")
                seen_sale_ids.add(sale_id)

                sales.append(
                    {
                        "sale_id": sale_id,
                        "product_id": product_id,
                        "team_id": team_id,
                        "quantity": quantity,
                        "discount": discount,
                        "line_number": line_number,
                    }
                )
    except FileNotFoundError as exc:
        raise ReportError(f"{path}: file not found") from exc
    except OSError as exc:
        raise ReportError(f"{path}: unable to read file: {exc}") from exc

    if not sales:
        raise ReportError(f"{path}: no sales rows found")

    return sales


def compute_reports(
    team_map: dict[int, str],
    products: dict[int, dict[str, object]],
    sales: list[dict[str, object]],
    sales_path: str,
) -> tuple[list[tuple[str, Decimal]], list[tuple[str, Decimal, int, Decimal]]]:
    """Compute team and product report rows using one pass over sales."""
    # defaultdict for team totals where the keys are bounded to validated team ids
    team_totals: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))

    product_totals: dict[int, dict[str, object]] = {}

    for sale in sales:
        product_id = sale["product_id"]
        team_id = sale["team_id"]
        line_number = sale["line_number"]
        context = f"{sales_path}: line {line_number}"

        # Foreign key checks
        if product_id not in products:
            raise ReportError(f"{context}: unknown ProductId {product_id}")
        if team_id not in team_map:
            raise ReportError(f"{context}: unknown TeamId {team_id}")

        product = products[product_id]
        quantity = sale["quantity"]
        discount = sale["discount"]

        lot_size = product["lot_size"]
        price = product["price"]
        # Quantity is in lots; convert to units before applying per-unit price
        units_sold = quantity * lot_size
        gross_revenue = Decimal(units_sold) * price
        # Discount is a % (divide by 100 before multiplying against revenue)
        discount_cost = gross_revenue * (discount / Decimal("100"))

        team_totals[team_id] += gross_revenue

        # Initialize on first encounter rather than upfront 
        if product_id not in product_totals:
            product_totals[product_id] = {
                "gross_revenue": Decimal("0"),
                "total_units": 0,
                "discount_cost": Decimal("0"),
            }

        product_total = product_totals[product_id]
        product_total["gross_revenue"] += gross_revenue
        product_total["total_units"] += units_sold
        product_total["discount_cost"] += discount_cost

    # Sort descending by revenue, then ascending by name to break ties deterministically
    team_rows = [
        (team_map[team_id], gross_revenue)
        for team_id, gross_revenue in team_totals.items()
    ]
    team_rows.sort(key=lambda item: (-item[1], item[0]))

    product_rows = []
    for product_id, totals in product_totals.items():
        product_rows.append(
            (
                products[product_id]["name"],
                totals["gross_revenue"],
                totals["total_units"],
                totals["discount_cost"],
            )
        )
    product_rows.sort(key=lambda item: (-item[1], item[0]))

    return team_rows, product_rows


def format_money(value: Decimal) -> str:
    """Format Decimal with trimmed trailing zeros and no exponent notation."""
    # common case for no discount sales 
    if value == 0:
        return "0"
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def write_team_report(path: str, rows: list[tuple[str, Decimal]]) -> None:
    """Write Team report CSV with exact header and row shape."""
    try:
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["Team", "GrossRevenue"])
            for team_name, gross_revenue in rows:
                writer.writerow([team_name, format_money(gross_revenue)])
    except OSError as exc:
        raise ReportError(f"{path}: unable to write file: {exc}") from exc


def write_product_report(path: str, rows: list[tuple[str, Decimal, int, Decimal]]) -> None:
    """Write Product report CSV with exact header and row shape."""
    try:
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["Name", "GrossRevenue", "TotalUnits", "DiscountCost"])
            for name, gross_revenue, total_units, discount_cost in rows:
                writer.writerow(
                    [
                        name,
                        format_money(gross_revenue),
                        total_units,
                        format_money(discount_cost),
                    ]
                )
    except OSError as exc:
        raise ReportError(f"{path}: unable to write file: {exc}") from exc


def main() -> int:
    """Run report generation pipeline."""
    args = parse_args()

    team_map = read_team_map(args.t)
    products = read_product_master(args.p)
    sales = read_sales(args.s)
    team_rows, product_rows = compute_reports(team_map, products, sales, args.s)

    write_team_report(args.team_report, team_rows)
    write_product_report(args.product_report, product_rows)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ReportError as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)