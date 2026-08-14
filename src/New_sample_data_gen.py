"""
generate_sample_data.py

Generates sample landing-zone data for a data pipeline demo.

Quarantine parquet folder structure expected (Hive-style date partitions):

    quarantine/
        orders/
            dt=2026-08-07/
                part-0000.parquet
                part-0001.parquet      (multiple files per day OK, all loaded)
            dt=2026-08-08/
                part-0000.parquet
        customers/
            dt=2026-08-07/
                part-0000.parquet
            dt=2026-08-09/
                part-0000.parquet

Orders and customers are discovered and injected completely independently
so they can have different sets of available dates.
"""

from __future__ import annotations

import json
import random
import sqlite3
import warnings
from datetime import date, timedelta
from pathlib import Path

try:
    import pandas as pd
    PARQUET_AVAILABLE = True
except ImportError:
    PARQUET_AVAILABLE = False
    warnings.warn(
        "pandas / pyarrow not found. Parquet quarantine injection disabled. "
        "Install with:  pip install pandas pyarrow",
        stacklevel=2,
    )

# =====================================================================
# CONFIG
# =====================================================================

CONFIG = {
    "start_date": "2026-08-01",
    "num_days": 4,

    "orders_per_day_min": 100,
    "orders_per_day_max": 1000,
    "customers_per_day_min": 10,
    "customers_per_day_max": 100,

    "order_bad_row_chance": 0.05,
    "customer_bad_record_chance": 0.05,

    "schema_drift_after_day": 2,
    "promotion_codes": ["BLACKFRI", "SAVE10", "WELCOME", "SUMMER25", ""],

    "currency": "USD",
    "landing_dir": r"data\landing",
    "random_seed": 42,

    # -----------------------------------------------------------------
    # QUARANTINE INJECTION
    # -----------------------------------------------------------------
    "quarantine_injection": {
        "enabled": True,

        # ---- Programmatic templates ---------------------------------
        "template_injection": {
            "enabled": True,
            "mode": "random",           # "fixed" | "random" | "per_day"
            "random_count_min": 1,
            "random_count_max": 2,
        },

        # ---- Parquet file injection ---------------------------------
        "parquet_injection": {
            "enabled": True,

            # Root folder.  Full expected layout:
            #   <parquet_source_dir>/
            #       orders/
            #           dt=<YYYY-MM-DD>/
            #               *.parquet
            #       customers/
            #           dt=<YYYY-MM-DD>/
            #               *.parquet
            "parquet_source_dir": r"data\quarantine",

            # Sub-folder names for each data type
            "orders_subdir":    r"data\quarantine\orders",
            "customers_subdir": r"data\quarantine\orders",

            # Hive-style partition folder naming convention.
            # {date} is replaced with the ISO date string, e.g. 2026-08-07
            "date_folder_pattern": "dt={date}",

            # Which dates to pull -- evaluated INDEPENDENTLY for orders
            # and customers (each type may have different available dates).
            #
            # "all"            -> every dt= folder found for that type
            # "match"          -> only dates inside the generated range
            # ["2026-08-07"]   -> explicit list of ISO date strings
            "orders_date_selection":    "all",
            "customers_date_selection": "all",

            # Rows to use from each day (all parquet files in the
            # dt= folder are concatenated first, then this limit applied).
            # 0 or None  ->  use ALL rows found for that day
            "max_rows_per_day": 5,

            # Optional column renaming: parquet_name -> pipeline_name
            "orders_column_map":    {},
            "customers_column_map": {},

            # Expected pipeline column order (used for CSV output)
            "orders_expected_columns": [
                "order_id", "customer_id", "product_id", "order_date",
                "amount", "currency", "status", "quantity",
            ],
            "customers_expected_columns": [
                "customer_id", "name", "email", "signup_date",
                "address", "phones",
            ],
        },

        "write_log": True,
    },
}

# =====================================================================
# QUARANTINE RULE TEMPLATES  (programmatic bad-data)
# =====================================================================

def _patch_negative_amount(row):
    r = list(row); r[4] = f"-{abs(float(r[4])):.2f}"; return tuple(r)

def _patch_zero_quantity(row):
    r = list(row); r[7] = "0"; return tuple(r)

def _patch_bad_status(row):
    r = list(row)
    r[6] = random.choice(["warped", "unknown", "in_transit_maybe", "??"])
    return tuple(r)

def _patch_empty_order_id(row):
    r = list(row); r[0] = ""; return tuple(r)

def _patch_missing_currency(row):
    r = list(row); r[5] = ""; return tuple(r)

def _patch_null_product(row):
    r = list(row); r[2] = ""; return tuple(r)

def _patch_duplicate_order(row):
    return row

def _patch_bad_email(rec):
    r = dict(rec)
    r["email"] = random.choice(["not-an-email", "missing@", "@nodomain"])
    return r

def _patch_missing_name(rec):
    r = dict(rec); r.pop("name", None); return r

def _patch_empty_address(rec):
    r = dict(rec); r["address"] = {}; return r

def _patch_future_signup(rec):
    r = dict(rec)
    r["signup_date"] = (
        date.fromisoformat(CONFIG["start_date"]) + timedelta(days=365)
    ).isoformat()
    return r

def _patch_duplicate_customer(rec):
    return rec


QUARANTINE_RULES: dict = {
    "templates": {
        "ORD_NEG_AMOUNT":     {"type": "order",    "description": "Negative amount",           "patch": _patch_negative_amount},
        "ORD_ZERO_QTY":       {"type": "order",    "description": "Zero quantity",              "patch": _patch_zero_quantity},
        "ORD_BAD_STATUS":     {"type": "order",    "description": "Unrecognised status",        "patch": _patch_bad_status},
        "ORD_EMPTY_ID":       {"type": "order",    "description": "Empty order_id",             "patch": _patch_empty_order_id},
        "ORD_NO_CURRENCY":    {"type": "order",    "description": "Missing currency",           "patch": _patch_missing_currency},
        "ORD_NULL_PRODUCT":   {"type": "order",    "description": "Null product_id",            "patch": _patch_null_product},
        "ORD_DUPLICATE":      {"type": "order",    "description": "Duplicate order",            "patch": _patch_duplicate_order,    "is_duplicate": True},
        "CUST_BAD_EMAIL":     {"type": "customer", "description": "Invalid email",              "patch": _patch_bad_email},
        "CUST_MISSING_NAME":  {"type": "customer", "description": "Missing name",               "patch": _patch_missing_name},
        "CUST_EMPTY_ADDR":    {"type": "customer", "description": "Empty address",              "patch": _patch_empty_address},
        "CUST_FUTURE_SIGNUP": {"type": "customer", "description": "Future signup_date",         "patch": _patch_future_signup},
        "CUST_DUPLICATE":     {"type": "customer", "description": "Duplicate customer",         "patch": _patch_duplicate_customer, "is_duplicate": True},
    },
    "fixed_rows": [
        "ORD_NEG_AMOUNT", "ORD_ZERO_QTY", "ORD_BAD_STATUS",
        "CUST_BAD_EMAIL", "CUST_MISSING_NAME",
    ],
    "per_day_schedule": {
        "2026-08-07": ["ORD_NEG_AMOUNT", "CUST_BAD_EMAIL"],
        "2026-08-08": ["ORD_BAD_STATUS"],
        "2026-08-09": ["ORD_ZERO_QTY", "CUST_MISSING_NAME", "ORD_DUPLICATE"],
        "2026-08-10": ["CUST_FUTURE_SIGNUP", "ORD_NULL_PRODUCT"],
    },
}

# =====================================================================
# PRODUCT CATALOGUE / NAME POOLS
# =====================================================================

PRODUCT_CATALOGUE = [
    ("P001", "Wireless Mouse",      "Electronics",  "49.99"),
    ("P002", "Mechanical Keyboard", "Electronics", "129.50"),
    ("P003", "USB-C Cable 2m",      "Accessories",  "15.00"),
    ("P004", "27in Monitor",        "Electronics", "299.00"),
    ("P005", "Notebook A5",         "Stationery",    "9.99"),
    ("P006", "Webcam HD",           "Electronics",  "79.00"),
    ("P007", "Desk Lamp",           "Accessories",  "34.99"),
    ("P008", "Mouse Pad XL",        "Accessories",  "19.99"),
]

FIRST_NAMES = [
    "Alice", "Bob", "Carol", "David", "Eve", "Frank", "Grace", "Henry",
    "Iris", "Jack", "Karen", "Liam", "Mia", "Noah", "Olivia", "Paul",
    "Quinn", "Rachel", "Sam", "Tina", "Uma", "Victor", "Wendy", "Xander",
    "Yara", "Zoe", "Aaron", "Beth", "Carlos", "Diana",
]
LAST_NAMES = [
    "Johnson", "Smith", "Davis", "Lee", "Martinez", "Wright", "Khan",
    "Brown", "Wilson", "Moore", "Taylor", "Anderson", "Thomas", "Jackson",
    "White", "Harris", "Martin", "Garcia", "Rodriguez", "Lewis",
    "Walker", "Hall", "Allen", "Young", "Hernandez", "King", "Scott",
]
STREET_TYPES = ["St", "Ave", "Rd", "Ln", "Dr", "Blvd", "Way", "Ct", "Pl"]
STREET_NAMES = [
    "Maple", "Oak", "Pine", "Birch", "Cedar", "Elm", "Cherry", "Willow",
    "Walnut", "Ash", "Spruce", "Poplar", "Magnolia", "Redwood", "Cypress",
]
CITIES = [
    ("Austin",      "TX", "78701"), ("Denver",      "CO", "80202"),
    ("Seattle",     "WA", "98101"), ("Boston",      "MA", "02108"),
    ("Miami",       "FL", "33101"), ("Chicago",     "IL", "60601"),
    ("Atlanta",     "GA", "30301"), ("Phoenix",     "AZ", "85001"),
    ("Portland",    "OR", "97201"), ("Dallas",      "TX", "75201"),
    ("Nashville",   "TN", "37201"), ("Minneapolis", "MN", "55401"),
]
EMAIL_DOMAINS  = ["example.com", "mail.com", "inbox.com", "webmail.org", "fastmail.net"]
ORDER_STATUSES = ["shipped", "pending", "delivered", "cancelled"]

# =====================================================================
# INTERNAL STATE
# =====================================================================

_customer_pool:    dict[str, dict] = {}
_order_counter:    int = 0
_customer_counter: int = 0
_quarantine_log:   list[dict] = []

# =====================================================================
# RANDOM HELPERS
# =====================================================================

def _rand_name() -> tuple[str, str]:
    return random.choice(FIRST_NAMES), random.choice(LAST_NAMES)

def _rand_email(first: str, last: str) -> str:
    domain  = random.choice(EMAIL_DOMAINS)
    variant = random.random()
    if variant < 0.33:
        local = f"{first.lower()}.{last.lower()}"
    elif variant < 0.66:
        local = f"{first[0].lower()}{last.lower()}"
    else:
        local = f"{first.lower()}{random.randint(1, 99)}"
    if random.random() < 0.1:
        local = local.upper()
    return f"{local}@{domain}"

def _rand_address() -> dict:
    city, state, zip_code = random.choice(CITIES)
    return {
        "street": (f"{random.randint(1, 999)} "
                   f"{random.choice(STREET_NAMES)} "
                   f"{random.choice(STREET_TYPES)}"),
        "city":  city,
        "state": state,
        "zip":   zip_code,
    }

def _rand_phones() -> list[str]:
    count = random.choices([0, 1, 2], weights=[0.05, 0.80, 0.15])[0]
    return [
        f"+1-{random.randint(200,999)}-{random.randint(100,999)}-{random.randint(1000,9999)}"
        for _ in range(count)
    ]

def _next_customer_id() -> str:
    global _customer_counter
    _customer_counter += 1
    return f"C{_customer_counter:03d}"

def _next_order_id() -> str:
    global _order_counter
    _order_counter += 1
    return f"O{_order_counter:08d}"

# =====================================================================
# BASE RECORD BUILDERS
# =====================================================================

def _build_clean_customer(date_str: str, customer_id: str | None = None) -> dict:
    cid         = customer_id or _next_customer_id()
    first, last = _rand_name()
    return {
        "customer_id": cid,
        "name":        f"{first} {last}",
        "email":       _rand_email(first, last),
        "signup_date": date_str,
        "address":     _rand_address(),
        "phones":      _rand_phones(),
    }

def _build_clean_order(date_str: str, customer_id: str, has_promo: bool = False) -> tuple:
    pid, _, _, price = random.choice(PRODUCT_CATALOGUE)
    row: tuple = (
        _next_order_id(), customer_id, pid,
        date_str, price, CONFIG["currency"],
        random.choice(ORDER_STATUSES), str(random.randint(1, 5)),
    )
    if has_promo:
        row = row + (random.choice(CONFIG["promotion_codes"]),)
    return row

# =====================================================================
# ORGANIC CORRUPTION
# =====================================================================

def _corrupt_order_organically(row: tuple) -> tuple:
    r   = list(row)
    bad = random.choice(["negative_amount", "bad_status", "zero_quantity"])
    if bad == "negative_amount": r[4] = f"-{abs(float(r[4])):.2f}"
    elif bad == "bad_status":    r[6] = random.choice(["warped", "unknown", "??"])
    else:                        r[7] = "0"
    return tuple(r)

def _corrupt_customer_organically(rec: dict) -> dict:
    r = dict(rec)
    if random.random() < 0.5:
        r["email"] = random.choice(["not-an-email", "missing@", "@nodomain"])
    else:
        r.pop("name", None)
    return r

# =====================================================================
# PARQUET HELPERS
# =====================================================================

def _is_valid_date(s: str) -> bool:
    """Return True if s is a valid ISO date string (YYYY-MM-DD)."""
    try:
        date.fromisoformat(s)
        return True
    except ValueError:
        return False


def _folder_to_date(folder_name: str, pattern: str) -> str | None:
    """
    Extract the ISO date string from a Hive-style folder name.

    Example:
        folder_name = "dt=2026-08-07"
        pattern     = "dt={date}"
        returns     -> "2026-08-07"

    Returns None if the folder does not match the pattern.
    """
    # Build a regex by replacing the literal "{date}" placeholder with
    # a named capture group that matches YYYY-MM-DD.
    import re
    escaped = re.escape(pattern).replace(r"\{date\}", r"(?P<date>\d{4}-\d{2}-\d{2})")
    m = re.fullmatch(escaped, folder_name)
    if not m:
        return None
    candidate = m.group("date")
    return candidate if _is_valid_date(candidate) else None


def _discover_dates_for_type(
    type_dir: Path,
    date_folder_pattern: str,
    date_selection: "str | list[str]",
    generated_dates: list[str],
) -> list[str]:
    """
    Scan type_dir for Hive-style partition folders and return the
    subset selected by date_selection.

    type_dir layout example:
        quarantine/orders/
            dt=2026-08-07/
            dt=2026-08-08/
    """
    if not type_dir.exists():
        return []

    # All valid date folders that actually exist on disk
    available: list[str] = []
    for entry in sorted(type_dir.iterdir()):
        if not entry.is_dir():
            continue
        parsed = _folder_to_date(entry.name, date_folder_pattern)
        if parsed:
            available.append(parsed)

    if not available:
        return []

    if date_selection == "all":
        return available

    if date_selection == "match":
        gen_set = set(generated_dates)
        return [d for d in available if d in gen_set]

    if isinstance(date_selection, list):
        requested = set(date_selection)
        chosen    = [d for d in available if d in requested]
        missing   = requested - set(available)
        if missing:
            warnings.warn(
                f"Requested quarantine dates not found on disk: {sorted(missing)}",
                stacklevel=2,
            )
        return chosen

    raise ValueError(
        f"date_selection must be 'all', 'match', or a list of date strings. "
        f"Got: {date_selection!r}"
    )


def _load_day_parquet(
    type_dir:            Path,
    date_str:            str,
    date_folder_pattern: str,
    column_map:          dict,
    max_rows:            int | None,
) -> list[dict]:
    """
    Load ALL .parquet files inside  type_dir/dt=<date_str>/,
    concatenate them into one DataFrame, optionally rename columns,
    optionally limit rows, and return as a list of row dicts.

    Returns [] on any error so a bad file never crashes the whole run.
    """
    if not PARQUET_AVAILABLE:
        return []

    folder_name = date_folder_pattern.replace("{date}", date_str)
    day_dir     = type_dir / folder_name

    if not day_dir.exists():
        return []

    parquet_files = sorted(day_dir.glob("*.parquet"))
    if not parquet_files:
        warnings.warn(f"No .parquet files found in {day_dir}", stacklevel=2)
        return []

    frames = []
    for pfile in parquet_files:
        try:
            frames.append(pd.read_parquet(pfile))
        except Exception as exc:                    # noqa: BLE001
            warnings.warn(f"Could not read {pfile}: {exc}", stacklevel=2)

    if not frames:
        return []

    df = pd.concat(frames, ignore_index=True)

    if column_map:
        df = df.rename(columns=column_map)

    if max_rows:
        df = df.head(max_rows)

    # Normalise every cell to str so CSV serialisation is consistent
    df = df.astype(str).replace("nan", "")
    return df.to_dict(orient="records")


# =====================================================================
# PARQUET ROW -> PIPELINE TYPE CONVERTERS
# =====================================================================

def _parquet_row_to_order_tuple(
    row:           dict,
    expected_cols: list[str],
    date_str:      str,
    has_promo:     bool,
) -> tuple:
    cols = expected_cols.copy()
    if has_promo and "promotion_code" not in cols:
        cols.append("promotion_code")
    # Always stamp the pipeline date so the row lands in the right file
    row = dict(row)
    row["order_date"] = date_str
    return tuple(str(row.get(c, "")) for c in cols)


def _parquet_row_to_customer_dict(
    row:           dict,
    expected_cols: list[str],
) -> dict:
    rec: dict = {}
    for col in expected_cols:
        val = row.get(col, "")
        if col == "address":
            if isinstance(val, dict):
                rec[col] = val
            else:
                try:
                    rec[col] = json.loads(val) if val else {}
                except (json.JSONDecodeError, TypeError):
                    rec[col] = {}
        elif col == "phones":
            if isinstance(val, list):
                rec[col] = val
            else:
                try:
                    rec[col] = json.loads(val) if val else []
                except (json.JSONDecodeError, TypeError):
                    rec[col] = []
        else:
            rec[col] = str(val) if val is not None else ""
    return rec


# =====================================================================
# PARQUET INJECTION MAP BUILDER
# =====================================================================

def _build_parquet_injection_map(
    parquet_cfg:     dict,
    generated_dates: list[str],
) -> dict[str, dict[str, list]]:
    """
    Walk the quarantine folder structure and return:

        {
            "2026-08-07": {
                "orders":    [ row_dict, ... ],
                "customers": [ row_dict, ... ],
            },
            ...
        }

    Orders and customers are discovered and loaded independently.
    """
    result: dict[str, dict[str, list]] = {}

    if not PARQUET_AVAILABLE:
        warnings.warn("Parquet injection skipped (pandas/pyarrow missing).", stacklevel=2)
        return result

    source_dir  = Path(parquet_cfg["parquet_source_dir"])
    pattern     = parquet_cfg["date_folder_pattern"]
    max_rows    = parquet_cfg.get("max_rows_per_day") or None

    ord_type_dir  = source_dir / parquet_cfg["orders_subdir"]
    cust_type_dir = source_dir / parquet_cfg["customers_subdir"]

    ord_col_map   = parquet_cfg.get("orders_column_map",    {})
    cust_col_map  = parquet_cfg.get("customers_column_map", {})

    # --- discover available dates for each type separately ---
    ord_dates  = _discover_dates_for_type(
        ord_type_dir,  pattern, parquet_cfg["orders_date_selection"],    generated_dates
    )
    cust_dates = _discover_dates_for_type(
        cust_type_dir, pattern, parquet_cfg["customers_date_selection"], generated_dates
    )

    all_active_dates = sorted(set(ord_dates) | set(cust_dates))

    if not all_active_dates:
        print("  [parquet] No matching quarantine date folders found -- skipping.")
        return result

    print(f"  [parquet] Active quarantine dates:")
    print(f"            orders    : {ord_dates  or 'none'}")
    print(f"            customers : {cust_dates or 'none'}")

    for d in all_active_dates:
        entry: dict[str, list] = {"orders": [], "customers": []}

        if d in ord_dates:
            entry["orders"] = _load_day_parquet(
                ord_type_dir, d, pattern, ord_col_map, max_rows
            )

        if d in cust_dates:
            entry["customers"] = _load_day_parquet(
                cust_type_dir, d, pattern, cust_col_map, max_rows
            )

        print(f"    {d}: {len(entry['orders'])} quarantine orders, "
              f"{len(entry['customers'])} quarantine customers loaded")

        result[d] = entry

    return result


# =====================================================================
# TEMPLATE INJECTION PLAN BUILDER
# =====================================================================

def _build_template_plan(tmpl_cfg: dict, dates: list[str]) -> dict[str, list[str]]:
    mode = tmpl_cfg["mode"]
    plan: dict[str, list[str]] = {d: [] for d in dates}

    if mode == "fixed":
        fixed = QUARANTINE_RULES["fixed_rows"]
        for i, tid in enumerate(fixed):
            plan[dates[i % len(dates)]].append(tid)

    elif mode == "random":
        templates = list(QUARANTINE_RULES["templates"].keys())
        for d in dates:
            n = random.randint(tmpl_cfg["random_count_min"], tmpl_cfg["random_count_max"])
            plan[d] = random.choices(templates, k=n)

    elif mode == "per_day":
        schedule = QUARANTINE_RULES["per_day_schedule"]
        for d in dates:
            plan[d] = schedule.get(d, [])

    else:
        raise ValueError(f"Unknown template injection mode: {mode!r}")

    return plan


# =====================================================================
# INJECTORS
# =====================================================================

def _inject_templates(
    date_str:      str,
    order_rows:    list[tuple],
    customer_recs: list[dict],
    template_ids:  list[str],
    has_promo:     bool,
) -> tuple[list[tuple], list[dict]]:
    templates = QUARANTINE_RULES["templates"]
    for tid in template_ids:
        if tid not in templates:
            print(f"  [WARN] Unknown template id: {tid!r} -- skipped")
            continue
        tmpl   = templates[tid]
        is_dup = tmpl.get("is_duplicate", False)

        if tmpl["type"] == "order":
            cid  = (random.choice(list(_customer_pool.keys()))
                    if _customer_pool else _next_customer_id())
            base = _build_clean_order(date_str, cid, has_promo=has_promo)
            row  = (random.choice(order_rows)
                    if (is_dup and order_rows) else tmpl["patch"](base))
            order_rows.append(row)
            _quarantine_log.append({
                "date": date_str, "source": "template",
                "template_id": tid, "type": "order",
                "description": tmpl["description"], "row": list(row),
            })
        else:
            base = _build_clean_customer(date_str)
            rec  = (dict(random.choice(customer_recs))
                    if (is_dup and customer_recs) else tmpl["patch"](base))
            customer_recs.append(rec)
            _quarantine_log.append({
                "date": date_str, "source": "template",
                "template_id": tid, "type": "customer",
                "description": tmpl["description"], "record": rec,
            })

    return order_rows, customer_recs


def _inject_parquet_rows(
    date_str:      str,
    order_rows:    list[tuple],
    customer_recs: list[dict],
    parquet_map:   dict[str, dict[str, list]],
    parquet_cfg:   dict,
    has_promo:     bool,
) -> tuple[list[tuple], list[dict]]:
    if date_str not in parquet_map:
        return order_rows, customer_recs

    ord_cols  = parquet_cfg["orders_expected_columns"]
    cust_cols = parquet_cfg["customers_expected_columns"]
    day_data  = parquet_map[date_str]

    for raw in day_data.get("orders", []):
        row = _parquet_row_to_order_tuple(raw, ord_cols, date_str, has_promo)
        order_rows.append(row)
        _quarantine_log.append({
            "date": date_str, "source": "parquet",
            "type": "order", "row": list(row),
        })

    for raw in day_data.get("customers", []):
        rec = _parquet_row_to_customer_dict(raw, cust_cols)
        customer_recs.append(rec)
        _quarantine_log.append({
            "date": date_str, "source": "parquet",
            "type": "customer", "record": rec,
        })

    return order_rows, customer_recs


# =====================================================================
# DAILY GENERATORS
# =====================================================================

def _generate_customers_for_day(date_str: str) -> list[dict]:
    count   = random.randint(CONFIG["customers_per_day_min"], CONFIG["customers_per_day_max"])
    records = []
    for _ in range(count):
        is_bad = random.random() < CONFIG["customer_bad_record_chance"]
        if _customer_pool and random.random() < 0.25 and not is_bad:
            cid    = random.choice(list(_customer_pool.keys()))
            record = dict(_customer_pool[cid])
            record["address"] = _rand_address()
            _customer_pool[cid] = record
        else:
            record = _build_clean_customer(date_str)
            if is_bad:
                record = _corrupt_customer_organically(record)
            else:
                _customer_pool[record["customer_id"]] = record
        records.append(record)
    return records


def _generate_orders_for_day(date_str: str, has_promo: bool) -> list[tuple]:
    count           = random.randint(CONFIG["orders_per_day_min"], CONFIG["orders_per_day_max"])
    valid_customers = list(_customer_pool.keys()) or [_next_customer_id()]
    rows            = []
    for _ in range(count):
        cid = random.choice(valid_customers)
        row = _build_clean_order(date_str, cid, has_promo=has_promo)
        if random.random() < CONFIG["order_bad_row_chance"]:
            row = _corrupt_order_organically(row)
        rows.append(row)
    return rows


# =====================================================================
# FILE WRITERS
# =====================================================================

def write_orders_csv(date_str: str, rows: list[tuple]) -> Path:
    out_dir  = Path(CONFIG["landing_dir"]) / "orders"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"orders_{date_str}.csv"
    has_promo = any(len(r) == 9 for r in rows)
    header    = (
        "order_id,customer_id,product_id,order_date,"
        "amount,currency,status,quantity"
        + (",promotion_code" if has_promo else "")
    )
    with out_path.open("w", encoding="utf-8") as f:
        f.write(header + "\n")
        for r in rows:
            f.write(",".join(str(v) for v in r) + "\n")
    return out_path


def write_customers_json(date_str: str, records: list[dict]) -> Path:
    out_dir  = Path(CONFIG["landing_dir"]) / "customers"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"customers_{date_str}.json"
    out_path.write_text(json.dumps(records, indent=2))
    return out_path


def write_quarantine_log() -> Path:
    out_dir  = Path(CONFIG["landing_dir"]) / "quarantine"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "quarantine_log.json"
    out_path.write_text(json.dumps(_quarantine_log, indent=2))
    return out_path


def write_products_sqlite(initial: list[tuple], updates: list[tuple]) -> Path:
    out_dir  = Path(CONFIG["landing_dir"]) / "products"
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path  = out_dir / "products.db"
    start    = date.fromisoformat(CONFIG["start_date"])
    con      = sqlite3.connect(db_path)
    cur      = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            product_id TEXT PRIMARY KEY, name TEXT NOT NULL,
            category TEXT NOT NULL, price TEXT NOT NULL, updated_at TEXT NOT NULL
        )
    """)
    initial_ts = start.isoformat() + "T10:00:00"
    update_ts  = (start + timedelta(days=1)).isoformat() + "T08:00:00"
    for pid, name, cat, price in initial:
        cur.execute(
            "INSERT OR IGNORE INTO products VALUES (?,?,?,?,?)",
            (pid, name, cat, price, initial_ts),
        )
    for pid, name, cat, price in updates:
        cur.execute("""
            INSERT INTO products (product_id,name,category,price,updated_at)
            VALUES (?,?,?,?,?)
            ON CONFLICT(product_id) DO UPDATE SET
                name=excluded.name, category=excluded.category,
                price=excluded.price, updated_at=excluded.updated_at""",
            (pid, name, cat, price, update_ts),
        )
    con.commit()
    con.close()
    return db_path


def _build_product_updates() -> tuple[list[tuple], list[tuple]]:
    initial = [(p[0], p[1], p[2], p[3]) for p in PRODUCT_CATALOGUE]
    updates = []
    for pid, name, cat, price in PRODUCT_CATALOGUE:
        if random.random() < 0.30:
            new_price = f"{max(0.99, float(price) + random.uniform(-10, 10)):.2f}"
            updates.append((pid, name, cat, new_price))
    return initial, updates


# =====================================================================
# VALIDATION HELPERS  (log-count only)
# =====================================================================

def _is_bad_order(row: tuple) -> bool:
    try:
        if float(row[4]) < 0:
            return True
    except (ValueError, IndexError):
        return True
    if row[6] not in ORDER_STATUSES:
        return True
    if row[7] == "0":
        return True
    return False


def _is_bad_customer(rec: dict) -> bool:
    if "name" not in rec:
        return True
    email = rec.get("email", "")
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        return True
    return False


# =====================================================================
# MAIN
# =====================================================================

def generate_all() -> None:
    if CONFIG["random_seed"] is not None:
        random.seed(CONFIG["random_seed"])

    start     = date.fromisoformat(CONFIG["start_date"])
    num_days  = CONFIG["num_days"]
    drift_day = CONFIG["schema_drift_after_day"]
    q_cfg     = CONFIG["quarantine_injection"]

    dates = [(start + timedelta(days=i)).isoformat() for i in range(num_days)]

    # --- build injection plans once up front ---
    template_plan: dict[str, list[str]] = {}
    parquet_map:   dict[str, dict]      = {}

    if q_cfg["enabled"]:
        if q_cfg["template_injection"]["enabled"]:
            template_plan = _build_template_plan(q_cfg["template_injection"], dates)
        if q_cfg["parquet_injection"]["enabled"]:
            parquet_map = _build_parquet_injection_map(q_cfg["parquet_injection"], dates)

    print(f"\n{'='*62}")
    print(f"  Generating {num_days} days of data  |  start: {start}")
    print(f"  Landing dir  : {Path(CONFIG['landing_dir']).resolve()}")
    q_status = "OFF"
    if q_cfg["enabled"]:
        parts = []
        if q_cfg["template_injection"]["enabled"]:
            parts.append(f"templates({q_cfg['template_injection']['mode']})")
        if q_cfg["parquet_injection"]["enabled"]:
            parts.append(
                f"parquet(orders={q_cfg['parquet_injection']['orders_date_selection']}, "
                f"customers={q_cfg['parquet_injection']['customers_date_selection']})"
            )
        q_status = "ON  [" + ", ".join(parts) + "]"
    print(f"  Quarantine   : {q_status}")
    print(f"{'='*62}\n")

    for day_index, date_str in enumerate(dates):
        has_promo = (drift_day is not None) and (day_index >= drift_day)

        customers = _generate_customers_for_day(date_str)
        orders    = _generate_orders_for_day(date_str, has_promo=has_promo)

        injected_tids: list[str] = []
        pq_ord_count  = 0
        pq_cust_count = 0

        if q_cfg["enabled"]:
            if q_cfg["template_injection"]["enabled"] and template_plan.get(date_str):
                injected_tids = template_plan[date_str]
                orders, customers = _inject_templates(
                    date_str, orders, customers, injected_tids, has_promo
                )
            if q_cfg["parquet_injection"]["enabled"] and date_str in parquet_map:
                pre_o = len(orders)
                pre_c = len(customers)
                orders, customers = _inject_parquet_rows(
                    date_str, orders, customers,
                    parquet_map, q_cfg["parquet_injection"], has_promo,
                )
                pq_ord_count  = len(orders)    - pre_o
                pq_cust_count = len(customers) - pre_c

        c_path = write_customers_json(date_str, customers)
        o_path = write_orders_csv(date_str, orders)

        bad_o = sum(1 for r in orders    if _is_bad_order(r))
        bad_c = sum(1 for r in customers if _is_bad_customer(r))

        print(f"  Day {day_index + 1}  ({date_str})")
        print(f"    customers : {len(customers):>3} records  ({bad_c} bad)  -> {c_path}")
        print(f"    orders    : {len(orders):>3} rows     ({bad_o} bad)  -> {o_path}")
        if has_promo:
            print(f"    [schema drift active: promotion_code column present]")
        if injected_tids:
            print(f"    [template injections : {', '.join(injected_tids)}]")
        if pq_ord_count or pq_cust_count:
            print(f"    [parquet injections  : +{pq_ord_count} orders, "
                  f"+{pq_cust_count} customers from disk]")

    initial, updates = _build_product_updates()
    p_path = write_products_sqlite(initial, updates)
    print(f"\n  products : {len(initial)} initial, {len(updates)} updates  -> {p_path}")

    if q_cfg["enabled"] and q_cfg["write_log"] and _quarantine_log:
        q_path      = write_quarantine_log()
        tmpl_count  = sum(1 for e in _quarantine_log if e["source"] == "template")
        pq_count    = sum(1 for e in _quarantine_log if e["source"] == "parquet")
        print(f"  quarantine log : {len(_quarantine_log)} total "
              f"({tmpl_count} template, {pq_count} parquet)  -> {q_path}")

    print(f"\n{'='*62}")
    print("  Done.")
    print(f"{'='*62}\n")


if __name__ == "__main__":
    generate_all()