"""Generate a realistic, reproducible CRM migration for demos and tests.

The output is a legacy export and a migrated export of the same customer base,
with the kinds of damage real migrations leave behind. The exact number of each
defect is written to expected.json, so a test can hold SyncProof to the truth.

    python scripts/generate_realistic.py [--rows 1200] [--seed 42]
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "examples" / "realistic"

FIRST = (
    "Ava Noah Mia Liam Sofia Oliver Emma Lucas Isla Ethan Zoe Mason Chloe Leo Nora Eli Ruby Owen "
    "Lena Hugo Maya Theo Iris Jack Alma Finn Dana Omar Vera Ivan Nina Adam Rosa Luka Elif Yuki "
    "Aiko Timur Aida Marek Petra Diego Lucia Mateo Camila Nikos Eleni Karim Leila Anton Greta"
).split()
LAST = (
    "Morgan Patel Chen Garcia Novak Smith Wilson Martin Kim Rossi Silva Haddad Tanaka Ivanov "
    "Kowalski Nguyen Fischer Dubois Costa Larsen Berg Ortiz Sato Khan Popescu Horvat Lindqvist "
    "Moreau Demir Aydin Suleiman Okafor Mendes Vargas Jensen Weber Keller Baumann Rizzo"
).split()
PLANS = {"Starter": 49, "Pro": 129, "Business": 299, "Enterprise": 1290}
COUNTRIES = ["US", "GB", "DE", "FR", "ES", "PL", "CA", "SG", "TR", "KZ", "AE", "BR"]


def _fmt_money(amount: int, style: int) -> str:
    """Three ways a billing system writes the same price."""
    if style == 0:
        return f"{amount}"
    if style == 1:
        return f"{amount}.00"
    whole = f"{amount:,}".replace(",", ".")
    return f"{whole},00"


def build(rows: int, seed: int) -> tuple[list[dict], list[dict], dict]:
    rng = random.Random(seed)
    names: list[str] = []
    seen: set[str] = set()
    while len(names) < rows + 40:
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        if name not in seen:
            seen.add(name)
            names.append(name)

    start = date(2024, 1, 1)
    source: list[dict] = []
    for i in range(rows):
        name = names[i]
        plan = rng.choices(list(PLANS), weights=[45, 35, 15, 5])[0]
        source.append({
            "customer_id": f"C-{10001 + i}",
            "full_name": name,
            "email": f"{name.lower().replace(' ', '.')}.{10001 + i}@example.com",
            "plan": plan,
            "mrr": f"{PLANS[plan]}.00",
            "start_date": (start + timedelta(days=rng.randint(0, 900))).isoformat(),
            "country": rng.choice(COUNTRIES),
        })

    order = list(range(rows))
    rng.shuffle(order)
    take = lambda n: [order.pop() for _ in range(n)]  # noqa: E731

    changed_plan = take(30)
    changed_price = take(20)
    changed_date = take(15)
    missing = take(25)
    renamed = take(40)
    duplicated = take(3)

    target: list[dict] = []
    for i, row in enumerate(source):
        if i in missing:
            continue
        out = {
            "id": row["customer_id"],
            "name": row["full_name"],
            "email_address": row["email"],
            "tier": row["plan"],
            "monthly_revenue": _fmt_money(PLANS[row["plan"]], rng.randint(0, 2)),
            "activated_at": row["start_date"],
            "country_code": row["country"],
        }
        # Formatting noise that must NOT count as a difference.
        if rng.random() < 0.30:
            out["email_address"] = out["email_address"].upper()
        if rng.random() < 0.20:
            out["name"] = f"  {out['name']} "
        if rng.random() < 0.35:
            y, m, d = out["activated_at"].split("-")
            out["activated_at"] = f"{d}.{m}.{y}"
        # Real defects.
        if i in changed_plan:
            others = [p for p in PLANS if p != row["plan"]]
            out["tier"] = rng.choice(others)
        if i in changed_price:
            out["monthly_revenue"] = _fmt_money(PLANS[row["plan"]] + rng.choice([-20, -10, 10, 25]), 1)
        if i in changed_date:
            moved = date.fromisoformat(row["start_date"]) + timedelta(days=rng.choice([-1, 1, 2]))
            out["activated_at"] = moved.isoformat()
        if i in renamed:
            out["id"] = f"CUS-{row['customer_id'][2:]}"
        target.append(out)

    # Records created in the new system after the cut-over.
    extra = 12
    for j in range(extra):
        name = names[rows + j]
        target.append({
            "id": f"C-{90001 + j}",
            "name": name,
            "email_address": f"{name.lower().replace(' ', '.')}.{90001 + j}@example.com",
            "tier": "Starter",
            "monthly_revenue": "49.00",
            "activated_at": (start + timedelta(days=950 + j)).isoformat(),
            "country_code": rng.choice(COUNTRIES),
        })

    # The legacy export contains a few rows twice.
    for i in duplicated:
        source.append(dict(source[i]))

    rng.shuffle(target)
    expected = {
        "source_rows": len(source),
        "target_rows": len(target),
        "changed": len(changed_plan) + len(changed_price) + len(changed_date),
        "fuzzy_matched": len(renamed),
        "source_only": len(missing) + len(duplicated),
        "target_only": extra,
        "duplicate_source_keys": len(duplicated),
    }
    expected["matched"] = len(source) - expected["changed"] - expected["fuzzy_matched"] - expected["source_only"]
    return source, target, expected


def _write(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=1200)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    source, target, expected = build(args.rows, args.seed)
    OUT.mkdir(parents=True, exist_ok=True)
    _write(OUT / "legacy_customers.csv", source)
    _write(OUT / "migrated_customers.csv", target)
    (OUT / "expected.json").write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(expected, indent=2))


if __name__ == "__main__":
    main()
