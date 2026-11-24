"""Daily meal cost calculator.

Keeps track of what I eat and spend each day, saves it to JSON + CSV,
and warns when a day goes over budget.
"""

import csv
import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

JSON_FILE = "meal_records.json"
CSV_FILE = "meal_records.csv"
REPORT_FILE = "summary.md"

MEAL_TYPES = ("Breakfast", "Lunch", "Dinner", "Snack", "Beverage")
CUR = "₹"
DAILY_LIMIT = 700.00
MIN_PRICE, MAX_PRICE = 1.00, 10000.00
MIN_QTY, MAX_QTY = 1, 50


@dataclass
class MealEntry:
    entry_id: str
    date: str
    meal_type: str
    item_name: str
    unit_price: float
    quantity: int
    total_cost: float = field(init=False)
    budget_flag: str = field(init=False)

    def __post_init__(self):
        self.unit_price = round(float(self.unit_price), 2)
        self.quantity = int(self.quantity)
        self.total_cost = round(self.unit_price * self.quantity, 2)
        # a single item costing more than half the daily budget is "high cost"
        self.budget_flag = "HIGH_COST" if self.total_cost > DAILY_LIMIT / 2 else "NORMAL"

    @classmethod
    def from_dict(cls, d):
        return cls(
            entry_id=str(d["entry_id"]),
            date=str(d["date"]),
            meal_type=str(d["meal_type"]),
            item_name=str(d["item_name"]),
            unit_price=float(d["unit_price"]),
            quantity=int(d["quantity"]),
        )


# ---------- input helpers ----------

def ask_text(prompt, max_len=40):
    while True:
        text = input(prompt).strip()
        if not text:
            print("  Can't be empty, try again.")
        elif len(text) > max_len:
            print(f"  Too long (max {max_len} characters).")
        elif not re.match(r"^[A-Za-z0-9\s\-&()'.]+$", text):
            print("  Only letters, numbers and basic punctuation please.")
        else:
            return text


def ask_date(prompt):
    while True:
        text = input(prompt).strip()
        if not text:
            return datetime.now().strftime("%Y-%m-%d")
        try:
            return datetime.strptime(text, "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError:
            print("  Use YYYY-MM-DD, or just press Enter for today.")


def ask_meal_type(prompt):
    while True:
        text = input(f"{prompt} ({'/'.join(MEAL_TYPES)}): ").strip().title()
        if text in MEAL_TYPES:
            return text
        print(f"  Pick one of: {', '.join(MEAL_TYPES)}")


def ask_price(prompt):
    while True:
        try:
            value = float(input(prompt).strip())
        except ValueError:
            print("  That's not a number (try something like 250).")
            continue
        if value != value or value in (float("inf"), float("-inf")):
            print("  That's not a number (try something like 250).")
        elif not MIN_PRICE <= value <= MAX_PRICE:
            print(f"  Price should be between {CUR}{MIN_PRICE:.2f} and {CUR}{MAX_PRICE:.2f}.")
        else:
            return round(value, 2)


def ask_quantity(prompt):
    while True:
        try:
            value = int(input(prompt).strip())
        except ValueError:
            print("  Please enter a whole number.")
            continue
        if MIN_QTY <= value <= MAX_QTY:
            return value
        print(f"  Quantity should be between {MIN_QTY} and {MAX_QTY}.")


# ---------- saving and loading ----------

def load_records():
    if not os.path.exists(JSON_FILE):
        save_records([])
        return []

    try:
        with open(JSON_FILE, encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, list):
            raise ValueError("expected a list at the top level")
    except (json.JSONDecodeError, ValueError, OSError) as err:
        print(f"  Couldn't read {JSON_FILE} ({err}). Keeping a backup and starting fresh.")
        try:
            os.replace(JSON_FILE, f"{JSON_FILE}.{int(datetime.now().timestamp())}.bak")
        except OSError:
            pass
        save_records([])
        return []

    records = []
    for i, item in enumerate(raw, start=1):
        try:
            records.append(MealEntry.from_dict(item))
        except (KeyError, ValueError, TypeError) as err:
            print(f"  Skipping bad record #{i}: {err}")
    return records


def save_records(records):
    rows = [asdict(r) for r in records]
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)

    columns = ["entry_id", "date", "meal_type", "item_name",
               "unit_price", "quantity", "total_cost", "budget_flag"]
    with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def import_csv(path, records):
    if not os.path.exists(path):
        print(f"  File not found: {path}")
        return records

    added = rejected = 0
    next_num = len(records) + 1
    try:
        with open(path, encoding="utf-8") as f:
            for line_no, row in enumerate(csv.DictReader(f), start=2):
                try:
                    date = row["date"].strip()
                    datetime.strptime(date, "%Y-%m-%d")
                    meal_type = row["meal_type"].strip().title()
                    if meal_type not in MEAL_TYPES:
                        raise ValueError(f"unknown meal type '{meal_type}'")
                    name = row["item_name"].strip()
                    if not name:
                        raise ValueError("item name is empty")
                    price = float(row["unit_price"])
                    qty = int(row["quantity"])
                    if not (MIN_PRICE <= price <= MAX_PRICE and MIN_QTY <= qty <= MAX_QTY):
                        raise ValueError("price or quantity out of range")
                except (KeyError, ValueError, AttributeError) as err:
                    rejected += 1
                    print(f"  Row {line_no}: {err}")
                    continue

                records.append(MealEntry(f"ML-{next_num:04d}", date, meal_type, name, price, qty))
                next_num += 1
                added += 1
    except OSError as err:
        print(f"  Couldn't read the file: {err}")
        return records

    save_records(records)
    print(f"  Import done: {added} added, {rejected} rejected.")
    return records


# ---------- analytics ----------

def daily_totals(records):
    totals = {}
    for r in records:
        totals[r.date] = round(totals.get(r.date, 0.0) + r.total_cost, 2)
    return dict(sorted(totals.items()))


def category_totals(records):
    totals = {t: 0.0 for t in MEAL_TYPES}
    for r in records:
        totals[r.meal_type] = round(totals[r.meal_type] + r.total_cost, 2)
    return totals


def summarise(records):
    days = daily_totals(records)
    grand_total = round(sum(r.total_cost for r in records), 2)
    return {
        "entries": len(records),
        "days": len(days),
        "total": grand_total,
        "avg_day": round(grand_total / len(days), 2),
        "avg_item": round(grand_total / len(records), 2),
        "priciest_day": max(days.items(), key=lambda x: x[1]),
        "cheapest_day": min(days.items(), key=lambda x: x[1]),
        "over_budget": [(d, t) for d, t in days.items() if t > DAILY_LIMIT],
        "by_category": category_totals(records),
    }


def export_report(records, path=REPORT_FILE):
    if not records:
        print("  Nothing to export yet.")
        return
    s = summarise(records)
    total = s["total"] or 1.0

    lines = [
        "# Meal Cost Summary",
        f"Generated {datetime.now():%Y-%m-%d %H:%M}, daily budget {CUR}{DAILY_LIMIT:.2f}",
        "",
        "## Overview",
        f"- Items recorded: {s['entries']}",
        f"- Days tracked: {s['days']}",
        f"- Total spent: {CUR}{s['total']:.2f}",
        f"- Average per day: {CUR}{s['avg_day']:.2f}",
        f"- Average per item: {CUR}{s['avg_item']:.2f}",
        f"- Most expensive day: {s['priciest_day'][0]} ({CUR}{s['priciest_day'][1]:.2f})",
        "",
        "## By category",
        "| Category | Spent | Share |",
        "| :--- | ---: | ---: |",
    ]
    for cat, amount in s["by_category"].items():
        lines.append(f"| {cat} | {CUR}{amount:.2f} | {amount / total * 100:.1f}% |")

    lines += ["", "## Over budget"]
    if s["over_budget"]:
        for day, amount in s["over_budget"]:
            lines.append(f"- {day}: {CUR}{amount:.2f} ({CUR}{amount - DAILY_LIMIT:.2f} over)")
    else:
        lines.append("- No days went over budget.")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  Report saved to {path}")


# ---------- demo data ----------

def build_demo_data():
    start = datetime(2026, 11, 10)
    # (day offset, meal type, item, price, quantity)
    samples = [
        (0, "Breakfast", "Oatmeal & Chia Bowl", 110.00, 1),
        (0, "Lunch", "Grilled Chicken Quinoa Salad", 255.00, 1),
        (0, "Dinner", "Baked Salmon & Asparagus", 330.00, 1),
        (0, "Snack", "Roasted Almonds Pack", 65.00, 1),  # day total ₹760, over budget
        (1, "Breakfast", "Greek Yogurt Parfait", 96.00, 1),
        (1, "Lunch", "Lentil & Spinach Soup", 170.00, 1),
        (1, "Dinner", "Vegetable Stir Fry & Tofu", 224.00, 1),
        (1, "Beverage", "Matcha Green Tea", 85.00, 1),
        (2, "Breakfast", "Avocado Toast & Poached Egg", 180.00, 1),
        (2, "Lunch", "Turkey Whole Wheat Wrap", 210.00, 1),
        (2, "Dinner", "Paneer Tikka & Brown Rice", 268.00, 1),
        (3, "Breakfast", "Banana Peanut Butter Smoothie", 125.00, 1),
        (3, "Lunch", "Chickpea Buddha Bowl", 220.00, 1),
        (3, "Snack", "Fresh Apple Slices", 35.00, 2),
        (3, "Dinner", "Herb Roasted Cod & Potatoes", 296.00, 1),
        (4, "Breakfast", "Scrambled Eggs & Sourdough", 150.00, 1),
        (4, "Lunch", "Black Bean Burrito Bowl", 218.00, 1),
        (4, "Dinner", "Mushroom Risotto", 304.00, 1),
        (4, "Beverage", "Cold Brew Coffee", 78.00, 1),  # day total ₹750, over budget
        (5, "Breakfast", "Steel Cut Oats & Berries", 102.00, 1),
        (5, "Lunch", "Mediterranean Falafel Plate", 236.00, 1),
        (5, "Dinner", "Grilled Shrimp Tacos", 290.00, 1),
        (6, "Breakfast", "Whole Grain Pancakes", 164.00, 1),
        (6, "Lunch", "Caprese Pesto Panini", 195.00, 1),
        (6, "Snack", "Dark Chocolate Square", 50.00, 1),
        (6, "Dinner", "Eggplant Parmesan", 272.00, 1),
        (7, "Breakfast", "Chia Seed Pudding", 108.00, 1),
        (7, "Lunch", "Tuna Nicoise Salad", 248.00, 1),
        (7, "Dinner", "Teriyaki Chicken Bowl", 278.00, 1),
        (8, "Breakfast", "Veggie Omelette", 156.00, 1),
        (8, "Lunch", "Minestrone Soup & Roll", 178.00, 1),
        (8, "Dinner", "Beef & Broccoli Stir Fry", 284.00, 1),
        (8, "Beverage", "Sparkling Mineral Water", 42.00, 2),
        # edge cases: a very cheap item and a bulk order
        (9, "Snack", "Single Espresso Shot", 30.00, 1),
        (9, "Dinner", "Catering Platter", 440.00, 2),
    ]
    entries = []
    for i, (offset, meal_type, name, price, qty) in enumerate(samples, start=1):
        date = (start + timedelta(days=offset)).strftime("%Y-%m-%d")
        entries.append(MealEntry(f"ML-{i:04d}", date, meal_type, name, price, qty))
    return entries


# ---------- menu actions ----------

def print_table(rows, page_size=12):
    if not rows:
        print("  No records found.")
        return

    header = (f"{'ID':<8} | {'Date':<10} | {'Category':<10} | {'Item':<26} | "
              f"{'Price':>9} | {'Qty':>3} | {'Total':>10} | {'Status':<9}")
    line = "-" * len(header)

    for start in range(0, len(rows), page_size):
        chunk = rows[start:start + page_size]
        print(f"\n{line}\n{header}\n{line}")
        for r in chunk:
            name = r.item_name if len(r.item_name) <= 26 else r.item_name[:23] + "..."
            print(f"{r.entry_id:<8} | {r.date:<10} | {r.meal_type:<10} | {name:<26} | "
                  f"{CUR}{r.unit_price:>8.2f} | {r.quantity:>3} | {CUR}{r.total_cost:>9.2f} | {r.budget_flag:<9}")
        print(line)
        if start + page_size < len(rows):
            answer = input(f"  Showing {start + len(chunk)}/{len(rows)}. Enter for more, 'q' to stop: ")
            if answer.strip().lower() == "q":
                break


def add_entry(records):
    print("\n--- Add a meal ---")
    date = ask_date("  Date (YYYY-MM-DD, Enter for today): ")
    meal_type = ask_meal_type("  Meal type")
    name = ask_text("  Item name: ")
    price = ask_price(f"  Unit price ({CUR}{MIN_PRICE:.2f}-{CUR}{MAX_PRICE:.2f}): ")
    qty = ask_quantity(f"  Quantity ({MIN_QTY}-{MAX_QTY}): ")

    entry = MealEntry(f"ML-{len(records) + 1:04d}", date, meal_type, name, price, qty)
    records.append(entry)
    save_records(records)

    print(f"\n  Saved {entry.entry_id}: {entry.quantity} x {entry.item_name} = {CUR}{entry.total_cost:.2f}")
    day_total = sum(r.total_cost for r in records if r.date == date)
    print(f"  Total for {date}: {CUR}{day_total:.2f} (limit {CUR}{DAILY_LIMIT:.2f})")
    if day_total > DAILY_LIMIT:
        print(f"  Heads up: that's {CUR}{day_total - DAILY_LIMIT:.2f} over your daily limit.")


def search_records(records):
    print("\n--- Search records ---")
    print("  1. By item name")
    print("  2. By meal type")
    print("  3. By date")
    print("  4. Show everything")
    choice = input("  Choose 1-4: ").strip()

    if choice == "1":
        keyword = input("  Keyword: ").strip().lower()
        found = [r for r in records if keyword in r.item_name.lower()]
    elif choice == "2":
        meal_type = ask_meal_type("  Meal type")
        found = [r for r in records if r.meal_type == meal_type]
    elif choice == "3":
        date = ask_date("  Date (YYYY-MM-DD): ")
        found = [r for r in records if r.date == date]
    else:
        found = records

    print_table(found)
    if found:
        print(f"  Subtotal for {len(found)} items: {CUR}{sum(r.total_cost for r in found):.2f}")


def show_summary(records):
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    if not records:
        print("  No records yet. Add some, or load the demo data.")
        return

    s = summarise(records)
    print(f"  Items recorded   : {s['entries']}")
    print(f"  Days tracked     : {s['days']}")
    print(f"  Total spent      : {CUR}{s['total']:.2f}")
    print(f"  Average per day  : {CUR}{s['avg_day']:.2f}")
    print(f"  Average per item : {CUR}{s['avg_item']:.2f}")
    print(f"  Priciest day     : {s['priciest_day'][0]} ({CUR}{s['priciest_day'][1]:.2f})")
    print(f"  Cheapest day     : {s['cheapest_day'][0]} ({CUR}{s['cheapest_day'][1]:.2f})")

    print("\n  Spending by category:")
    total = s["total"] or 1.0
    for cat, amount in s["by_category"].items():
        pct = amount / total * 100
        print(f"  {cat:<10} {CUR}{amount:>7.2f} ({pct:>5.1f}%) {'#' * int(pct // 4)}")

    print("\n  Days over budget:")
    if s["over_budget"]:
        for day, amount in s["over_budget"]:
            print(f"  {day}: {CUR}{amount:.2f} ({CUR}{amount - DAILY_LIMIT:.2f} over)")
    else:
        print("  None, nice.")
    print("=" * 60)


def load_demo_data(records):
    answer = input("  This replaces your current data with demo records. Continue? (y/n): ")
    if answer.strip().lower() != "y":
        return records
    records = build_demo_data()
    save_records(records)
    print(f"  Loaded {len(records)} demo records.")
    return records


def main():
    records = load_records()
    print("\n" + "=" * 60)
    print("  Daily Meal Cost Calculator")
    print("=" * 60)
    print(f"  Loaded {len(records)} saved records.")

    while True:
        print("\nMenu:")
        print("  1. Add a meal")
        print("  2. View / search records")
        print("  3. Summary")
        print("  4. Export report (markdown)")
        print("  5. Import from CSV")
        print("  6. Load demo data")
        print("  0. Exit")

        choice = input("\nChoose: ").strip()
        if choice == "1":
            add_entry(records)
        elif choice == "2":
            search_records(records)
        elif choice == "3":
            show_summary(records)
        elif choice == "4":
            export_report(records)
        elif choice == "5":
            records = import_csv(input("  CSV path: ").strip(), records)
        elif choice == "6":
            records = load_demo_data(records)
        elif choice == "0":
            save_records(records)
            print("  Saved. Bye!")
            break
        else:
            print("  Please pick a number from 0 to 6.")


if __name__ == "__main__":
    main()
