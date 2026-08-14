import streamlit as st
import pandas as pd
import json
import random
import warnings
from datetime import date, timedelta
from pathlib import Path
from copy import deepcopy
import io
import zipfile

# ── page config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Sample Data Generator",
    page_icon="🗄️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
html, body, [data-testid="stAppViewContainer"] {
    background: #0f1117; color: #e2e8f0; font-family: 'Inter', sans-serif;
}
[data-testid="stSidebar"] {
    background: #161b27 !important; border-right: 1px solid #2d3748;
}
h1 { color: #7dd3fc !important; font-weight: 700 !important; }
h2 { color: #93c5fd !important; font-weight: 600 !important; }
h3 { color: #bfdbfe !important; font-weight: 600 !important; }
[data-testid="metric-container"] {
    background: #1e2535; border: 1px solid #2d3748;
    border-radius: 12px; padding: 16px 20px;
}
[data-testid="metric-container"] label       { color: #94a3b8 !important; font-size: 0.78rem !important; }
[data-testid="metric-container"] [data-testid="stMetricValue"]
                                             { color: #7dd3fc !important; font-size: 1.6rem !important; }
[data-testid="stTabs"] [role="tablist"]      { border-bottom: 2px solid #2d3748; gap: 4px; }
[data-testid="stTabs"] button[role="tab"] {
    background: transparent; color: #94a3b8;
    border-radius: 8px 8px 0 0; border: 1px solid transparent;
    padding: 8px 18px; font-size: 0.85rem; font-weight: 500; transition: all .2s;
}
[data-testid="stTabs"] button[role="tab"]:hover         { color: #e2e8f0; background: #1e2535; }
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
    color: #7dd3fc !important; border-color: #2d3748 #2d3748 #0f1117; background: #1e2535;
}
[data-testid="stExpander"] {
    background: #1a2030 !important; border: 1px solid #2d3748 !important;
    border-radius: 10px !important;
}
[data-testid="stExpander"] summary           { color: #93c5fd !important; font-weight: 600; }
.stButton > button {
    background: linear-gradient(135deg, #1d4ed8, #1e40af); color: #fff;
    border: none; border-radius: 8px; padding: 10px 28px;
    font-weight: 600; font-size: 0.9rem; transition: all .2s;
    box-shadow: 0 2px 8px rgba(29,78,216,.35);
}
.stButton > button:hover {
    background: linear-gradient(135deg, #2563eb, #1d4ed8);
    box-shadow: 0 4px 14px rgba(29,78,216,.55); transform: translateY(-1px);
}
[data-testid="stDownloadButton"] > button {
    background: linear-gradient(135deg, #065f46, #047857);
    color: #d1fae5; border: 1px solid #059669;
    border-radius: 8px; font-weight: 600; font-size: 0.82rem; padding: 7px 18px;
}
input[type="number"], input[type="text"], textarea {
    background: #1e2535 !important; color: #e2e8f0 !important;
    border: 1px solid #374151 !important; border-radius: 6px !important;
}
[data-baseweb="select"] > div {
    background: #1e2535 !important; border-color: #374151 !important;
    color: #e2e8f0 !important; border-radius: 6px !important;
}
[data-testid="stCheckbox"] label            { color: #cbd5e1 !important; }
hr                                          { border-color: #2d3748 !important; margin: 1.2rem 0; }
code, pre { background: #1a2030 !important; color: #86efac !important; border-radius: 6px; }
.sidebar-section {
    color: #7dd3fc; font-size: 0.72rem; font-weight: 700;
    letter-spacing: 1.2px; text-transform: uppercase;
    padding: 10px 0 4px; border-bottom: 1px solid #2d3748; margin-bottom: 8px;
}
.stat-card {
    background: #1e2535; border: 1px solid #2d3748; border-radius: 10px;
    padding: 20px 24px;
}
.stat-card .icon { font-size: 1.8rem; margin-bottom: 6px; }
.stat-card .val  { color: #7dd3fc; font-weight: 700; font-size: 1rem; }
.stat-card .desc { color: #94a3b8; font-size: 0.82rem; margin-top: 4px; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

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
    "Alice","Bob","Carol","David","Eve","Frank","Grace","Henry",
    "Iris","Jack","Karen","Liam","Mia","Noah","Olivia","Paul",
    "Quinn","Rachel","Sam","Tina","Uma","Victor","Wendy","Xander",
    "Yara","Zoe","Aaron","Beth","Carlos","Diana",
]
LAST_NAMES = [
    "Johnson","Smith","Davis","Lee","Martinez","Wright","Khan",
    "Brown","Wilson","Moore","Taylor","Anderson","Thomas","Jackson",
    "White","Harris","Martin","Garcia","Rodriguez","Lewis",
    "Walker","Hall","Allen","Young","Hernandez","King","Scott",
]
STREET_TYPES = ["St","Ave","Rd","Ln","Dr","Blvd","Way","Ct","Pl"]
STREET_NAMES = [
    "Maple","Oak","Pine","Birch","Cedar","Elm","Cherry","Willow",
    "Walnut","Ash","Spruce","Poplar","Magnolia","Redwood","Cypress",
]
CITIES = [
    ("Austin","TX","78701"), ("Denver","CO","80202"),   ("Seattle","WA","98101"),
    ("Boston","MA","02108"), ("Miami","FL","33101"),     ("Chicago","IL","60601"),
    ("Atlanta","GA","30301"),("Phoenix","AZ","85001"),   ("Portland","OR","97201"),
    ("Dallas","TX","75201"), ("Nashville","TN","37201"), ("Minneapolis","MN","55401"),
]
EMAIL_DOMAINS  = ["example.com","mail.com","inbox.com","webmail.org","fastmail.net"]
ORDER_STATUSES = ["shipped","pending","delivered","cancelled"]

PER_DAY_SCHEDULE = {
    "2026-08-07": ["ORD_NEG_AMOUNT","CUST_BAD_EMAIL"],
    "2026-08-08": ["ORD_BAD_STATUS"],
    "2026-08-09": ["ORD_ZERO_QTY","CUST_MISSING_NAME","ORD_DUPLICATE"],
    "2026-08-10": ["CUST_FUTURE_SIGNUP","ORD_NULL_PRODUCT"],
}
FIXED_ROWS = [
    "ORD_NEG_AMOUNT","ORD_ZERO_QTY","ORD_BAD_STATUS",
    "CUST_BAD_EMAIL","CUST_MISSING_NAME",
]


# ══════════════════════════════════════════════════════════════════════════════
# GENERATION ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def _make_engine(cfg: dict):
    """
    Returns a run() function bound to cfg.
    All mutable state lives inside the closure — no globals, fully re-entrant.
    """
    _customer_pool:    dict = {}
    _order_counter:    list = [0]       # list so inner funcs can mutate
    _customer_counter: list = [0]
    _quarantine_log:   list = []

    rng = random.Random(cfg.get("random_seed"))   # None → non-deterministic

    # ── id helpers ───────────────────────────────────────────────────────────
    def _next_cid():
        _customer_counter[0] += 1
        return f"C{_customer_counter[0]:03d}"

    def _next_oid():
        _order_counter[0] += 1
        return f"O{_order_counter[0]:08d}"

    # ── random field helpers ─────────────────────────────────────────────────
    def _rand_email(first: str, last: str) -> str:
        domain  = rng.choice(EMAIL_DOMAINS)
        variant = rng.random()
        if variant < .33:   local = f"{first.lower()}.{last.lower()}"
        elif variant < .66: local = f"{first[0].lower()}{last.lower()}"
        else:               local = f"{first.lower()}{rng.randint(1, 99)}"
        if rng.random() < .1:
            local = local.upper()
        return f"{local}@{domain}"

    def _rand_address() -> dict:
        city, state, zip_code = rng.choice(CITIES)
        return {
            "street": (f"{rng.randint(1,999)} "
                       f"{rng.choice(STREET_NAMES)} "
                       f"{rng.choice(STREET_TYPES)}"),
            "city": city, "state": state, "zip": zip_code,
        }

    def _rand_phones() -> list:
        count = rng.choices([0, 1, 2], weights=[.05, .80, .15])[0]
        return [
            f"+1-{rng.randint(200,999)}-{rng.randint(100,999)}-{rng.randint(1000,9999)}"
            for _ in range(count)
        ]

    # ── record builders ──────────────────────────────────────────────────────
    def _build_clean_customer(date_str: str, customer_id=None) -> dict:
        cid        = customer_id or _next_cid()
        first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
        return {
            "customer_id": cid,
            "name":        f"{first} {last}",
            "email":       _rand_email(first, last),
            "signup_date": date_str,
            "address":     _rand_address(),
            "phones":      _rand_phones(),
        }

    def _build_clean_order(date_str: str, customer_id: str, has_promo=False) -> tuple:
        pid, _, _, price = rng.choice(PRODUCT_CATALOGUE)
        row = (
            _next_oid(), customer_id, pid,
            date_str, price, cfg["currency"],
            rng.choice(ORDER_STATUSES), str(rng.randint(1, 5)),
        )
        if has_promo:
            row = row + (rng.choice(cfg["promotion_codes"]),)
        return row

    # ── organic corruption ───────────────────────────────────────────────────
    def _corrupt_order(row: tuple) -> tuple:
        r   = list(row)
        bad = rng.choice(["negative_amount", "bad_status", "zero_quantity"])
        if   bad == "negative_amount": r[4] = f"-{abs(float(r[4])):.2f}"
        elif bad == "bad_status":      r[6] = rng.choice(["warped", "unknown", "??"])
        else:                          r[7] = "0"
        return tuple(r)

    def _corrupt_customer(rec: dict) -> dict:
        r = dict(rec)
        if rng.random() < .5:
            r["email"] = rng.choice(["not-an-email", "missing@", "@nodomain"])
        else:
            r.pop("name", None)
        return r

    # ── quarantine patch functions ───────────────────────────────────────────
    def _patch_neg_amount(row):
        r = list(row); r[4] = f"-{abs(float(r[4])):.2f}"; return tuple(r)

    def _patch_zero_qty(row):
        r = list(row); r[7] = "0"; return tuple(r)

    def _patch_bad_status(row):
        r = list(row)
        r[6] = rng.choice(["warped", "unknown", "in_transit_maybe", "??"])
        return tuple(r)

    def _patch_empty_oid(row):
        r = list(row); r[0] = ""; return tuple(r)

    def _patch_no_currency(row):
        r = list(row); r[5] = ""; return tuple(r)

    def _patch_null_product(row):
        r = list(row); r[2] = ""; return tuple(r)

    def _patch_dup_order(row):
        return row

    def _patch_bad_email(rec):
        r = dict(rec)
        r["email"] = rng.choice(["not-an-email", "missing@", "@nodomain"])
        return r

    def _patch_missing_name(rec):
        r = dict(rec); r.pop("name", None); return r

    def _patch_empty_addr(rec):
        r = dict(rec); r["address"] = {}; return r

    def _patch_future_signup(rec):
        r = dict(rec)
        r["signup_date"] = (
            date.fromisoformat(cfg["start_date"]) + timedelta(days=365)
        ).isoformat()
        return r

    def _patch_dup_cust(rec):
        return rec

    TEMPLATES = {
        "ORD_NEG_AMOUNT":     {"type": "order",    "desc": "Negative amount",      "patch": _patch_neg_amount},
        "ORD_ZERO_QTY":       {"type": "order",    "desc": "Zero quantity",         "patch": _patch_zero_qty},
        "ORD_BAD_STATUS":     {"type": "order",    "desc": "Unrecognised status",   "patch": _patch_bad_status},
        "ORD_EMPTY_ID":       {"type": "order",    "desc": "Empty order_id",        "patch": _patch_empty_oid},
        "ORD_NO_CURRENCY":    {"type": "order",    "desc": "Missing currency",      "patch": _patch_no_currency},
        "ORD_NULL_PRODUCT":   {"type": "order",    "desc": "Null product_id",       "patch": _patch_null_product},
        "ORD_DUPLICATE":      {"type": "order",    "desc": "Duplicate order",       "patch": _patch_dup_order,  "is_dup": True},
        "CUST_BAD_EMAIL":     {"type": "customer", "desc": "Invalid email",         "patch": _patch_bad_email},
        "CUST_MISSING_NAME":  {"type": "customer", "desc": "Missing name",          "patch": _patch_missing_name},
        "CUST_EMPTY_ADDR":    {"type": "customer", "desc": "Empty address",         "patch": _patch_empty_addr},
        "CUST_FUTURE_SIGNUP": {"type": "customer", "desc": "Future signup_date",    "patch": _patch_future_signup},
        "CUST_DUPLICATE":     {"type": "customer", "desc": "Duplicate customer",    "patch": _patch_dup_cust,   "is_dup": True},
    }

    # ── template plan builder ────────────────────────────────────────────────
    def _build_template_plan(tmpl_cfg: dict, dates: list) -> dict:
        mode = tmpl_cfg["mode"]
        plan = {d: [] for d in dates}

        if mode == "fixed":
            for i, tid in enumerate(FIXED_ROWS):
                plan[dates[i % len(dates)]].append(tid)

        elif mode == "random":
            tkeys = list(TEMPLATES.keys())
            for d in dates:
                n       = rng.randint(tmpl_cfg["random_count_min"],
                                      tmpl_cfg["random_count_max"])
                plan[d] = rng.choices(tkeys, k=n)

        elif mode == "per_day":
            for d in dates:
                plan[d] = PER_DAY_SCHEDULE.get(d, [])

        return plan

    # ── template injector ────────────────────────────────────────────────────
    def _inject_templates(date_str, order_rows, customer_recs, tids, has_promo):
        for tid in tids:
            if tid not in TEMPLATES:
                continue
            tmpl   = TEMPLATES[tid]
            is_dup = tmpl.get("is_dup", False)

            if tmpl["type"] == "order":
                cid  = (rng.choice(list(_customer_pool.keys()))
                        if _customer_pool else _next_cid())
                base = _build_clean_order(date_str, cid, has_promo=has_promo)
                row  = (rng.choice(order_rows)
                        if (is_dup and order_rows) else tmpl["patch"](base))
                order_rows.append(row)
                _quarantine_log.append({
                    "date": date_str, "source": "template",
                    "template_id": tid, "type": "order",
                    "description": tmpl["desc"], "row": list(row),
                })
            else:
                base = _build_clean_customer(date_str)
                rec  = (dict(rng.choice(customer_recs))
                        if (is_dup and customer_recs) else tmpl["patch"](base))
                customer_recs.append(rec)
                _quarantine_log.append({
                    "date": date_str, "source": "template",
                    "template_id": tid, "type": "customer",
                    "description": tmpl["desc"], "record": rec,
                })

        return order_rows, customer_recs

    # ── daily generators ─────────────────────────────────────────────────────
    def _gen_customers(date_str: str) -> list:
        count   = rng.randint(cfg["customers_per_day_min"],
                              cfg["customers_per_day_max"])
        records = []
        for _ in range(count):
            is_bad = rng.random() < cfg["customer_bad_record_chance"]
            if _customer_pool and rng.random() < .25 and not is_bad:
                cid = rng.choice(list(_customer_pool.keys()))
                rec = dict(_customer_pool[cid])
                rec["address"] = _rand_address()
                _customer_pool[cid] = rec
            else:
                rec = _build_clean_customer(date_str)
                if is_bad:
                    rec = _corrupt_customer(rec)
                else:
                    _customer_pool[rec["customer_id"]] = rec
            records.append(rec)
        return records

    def _gen_orders(date_str: str, has_promo: bool) -> list:
        count   = rng.randint(cfg["orders_per_day_min"],
                              cfg["orders_per_day_max"])
        valid_c = list(_customer_pool.keys()) or [_next_cid()]
        rows    = []
        for _ in range(count):
            cid = rng.choice(valid_c)
            row = _build_clean_order(date_str, cid, has_promo=has_promo)
            if rng.random() < cfg["order_bad_row_chance"]:
                row = _corrupt_order(row)
            rows.append(row)
        return rows

    # ── quality checkers ─────────────────────────────────────────────────────
    def _is_bad_order(row: tuple) -> bool:
        try:
            if float(row[4]) < 0:
                return True
        except (ValueError, IndexError):
            return True
        if row[6] not in ORDER_STATUSES:
            return True
        if str(row[7]) == "0":
            return True
        return False

    def _is_bad_customer(rec: dict) -> bool:
        if "name" not in rec:
            return True
        email = rec.get("email", "")
        if (not isinstance(email, str) or "@" not in email
                or email.startswith("@") or email.endswith("@")):
            return True
        return False

    # ── main run ─────────────────────────────────────────────────────────────
    def run() -> dict:
        start    = date.fromisoformat(cfg["start_date"])
        num_days = cfg["num_days"]
        drift    = cfg["schema_drift_after_day"]
        q_cfg    = cfg["quarantine_injection"]
        dates    = [(start + timedelta(days=i)).isoformat()
                    for i in range(num_days)]

        # build template injection plan up-front
        template_plan: dict = {}
        if q_cfg["enabled"] and q_cfg["template_injection"]["enabled"]:
            template_plan = _build_template_plan(
                q_cfg["template_injection"], dates
            )

        results              = []
        all_orders_flat      = []   # list[dict]  for the combined DataFrame
        all_customers_flat   = []   # list[dict]

        for day_index, date_str in enumerate(dates):
            has_promo = (drift is not None) and (day_index >= drift)

            customers = _gen_customers(date_str)
            orders    = _gen_orders(date_str, has_promo=has_promo)
            injected_tids: list = []

            if q_cfg["enabled"] and q_cfg["template_injection"]["enabled"]:
                injected_tids = template_plan.get(date_str, [])
                if injected_tids:
                    orders, customers = _inject_templates(
                        date_str, orders, customers,
                        injected_tids, has_promo,
                    )

            bad_o = sum(1 for r in orders    if _is_bad_order(r))
            bad_c = sum(1 for r in customers if _is_bad_customer(r))

            # ---- flatten orders for combined DataFrame -------------------
            ord_cols = [
                "order_id","customer_id","product_id","order_date",
                "amount","currency","status","quantity",
            ]
            if has_promo:
                ord_cols = ord_cols + ["promotion_code"]

            for row in orders:
                flat = {ord_cols[i]: (row[i] if i < len(row) else "")
                        for i in range(len(ord_cols))}
                flat["_date"] = date_str
                all_orders_flat.append(flat)

            # ---- flatten customers for combined DataFrame ----------------
            for rec in customers:
                flat = {}
                for k, v in rec.items():
                    flat[k] = json.dumps(v) if isinstance(v, (dict, list)) else v
                flat["_date"] = date_str
                all_customers_flat.append(flat)

            results.append({
                "date":          date_str,
                "day_index":     day_index + 1,
                "has_promo":     has_promo,
                "n_customers":   len(customers),
                "n_orders":      len(orders),
                "bad_customers": bad_c,
                "bad_orders":    bad_o,
                "injected_tids": injected_tids,
                "customers_raw": customers,
                "orders_raw":    orders,
                "ord_cols":      ord_cols,
            })

        # ---- products -------------------------------------------------------
        prod_initial = [(p[0], p[1], p[2], p[3]) for p in PRODUCT_CATALOGUE]
        prod_updates = []
        for pid, name, cat, price in PRODUCT_CATALOGUE:
            if rng.random() < .30:
                new_price = f"{max(.99, float(price) + rng.uniform(-10, 10)):.2f}"
                prod_updates.append((pid, name, cat, new_price))

        return {
            "results":       results,
            "quarantine_log":_quarantine_log,
            "prod_initial":  prod_initial,
            "prod_updates":  prod_updates,
            "all_orders":    all_orders_flat,
            "all_customers": all_customers_flat,
        }

    return run


# ══════════════════════════════════════════════════════════════════════════════
# SESSION STATE
# ══════════════════════════════════════════════════════════════════════════════

_DEFAULT_CONFIG: dict = {
    "start_date":                 "2026-08-01",
    "num_days":                   4,
    "orders_per_day_min":         1,
    "orders_per_day_max":         1000,
    "customers_per_day_min":      1,
    "customers_per_day_max":      100,
    "order_bad_row_chance":       0.05,
    "customer_bad_record_chance": 0.05,
    "schema_drift_after_day":     None,
    "promotion_codes":            ["BLACKFRI","SAVE10","WELCOME","SUMMER25",""],
    "currency":                   "USD",
    "landing_dir":                r"data\landing",
    "random_seed":                42,
    "quarantine_injection": {
        "enabled": True,
        "template_injection": {
            "enabled":          True,
            "mode":             "random",
            "random_count_min": 1,
            "random_count_max": 2,
        },
        "write_log": True,
    },
}

if "cfg"        not in st.session_state:
    st.session_state.cfg        = deepcopy(_DEFAULT_CONFIG)
if "run_output" not in st.session_state:
    st.session_state.run_output = None   # stays None until first successful run


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("## ⚙️ Configuration")

    # ── Date & Volume ────────────────────────────────────────────────────────
    st.markdown('<p class="sidebar-section">📅 Date &amp; Volume</p>',
                unsafe_allow_html=True)

    start_val = st.date_input(
        "Start date",
        value=date.fromisoformat(st.session_state.cfg["start_date"]),
        key="si_start",
    )
    st.session_state.cfg["start_date"] = start_val.isoformat()

    st.session_state.cfg["num_days"] = st.number_input(
        "Number of days", min_value=1, max_value=30,
        value=int(st.session_state.cfg["num_days"]),
        step=1, key="si_days",
    )

    # ── Orders ───────────────────────────────────────────────────────────────
    st.markdown('<p class="sidebar-section">🛒 Orders per Day</p>',
                unsafe_allow_html=True)
    ord_min, ord_max = st.slider(
        "Range (min → max)", 1, 5000,
        value=(int(st.session_state.cfg["orders_per_day_min"]),
               int(st.session_state.cfg["orders_per_day_max"])),
        step=10, key="si_ord",
    )
    st.session_state.cfg["orders_per_day_min"] = ord_min
    st.session_state.cfg["orders_per_day_max"] = ord_max

    # ── Customers ────────────────────────────────────────────────────────────
    st.markdown('<p class="sidebar-section">👥 Customers per Day</p>',
                unsafe_allow_html=True)
    cst_min, cst_max = st.slider(
        "Range (min → max)", 1, 500,
        value=(int(st.session_state.cfg["customers_per_day_min"]),
               int(st.session_state.cfg["customers_per_day_max"])),
        step=5, key="si_cst",
    )
    st.session_state.cfg["customers_per_day_min"] = cst_min
    st.session_state.cfg["customers_per_day_max"] = cst_max

    # ── Data Quality ─────────────────────────────────────────────────────────
    st.markdown('<p class="sidebar-section">🧪 Data Quality</p>',
                unsafe_allow_html=True)
    st.session_state.cfg["order_bad_row_chance"] = st.slider(
        "Order bad-row chance", 0.0, 1.0,
        float(st.session_state.cfg["order_bad_row_chance"]),
        step=0.01, format="%.2f", key="si_obad",
    )
    st.session_state.cfg["customer_bad_record_chance"] = st.slider(
        "Customer bad-record chance", 0.0, 1.0,
        float(st.session_state.cfg["customer_bad_record_chance"]),
        step=0.01, format="%.2f", key="si_cbad",
    )

    # ── Schema & Currency ────────────────────────────────────────────────────
    st.markdown('<p class="sidebar-section">💱 Schema &amp; Currency</p>',
                unsafe_allow_html=True)
    _currencies = ["USD","EUR","GBP","JPY","CAD","AUD"]
    _cur_idx    = (_currencies.index(st.session_state.cfg["currency"])
                   if st.session_state.cfg["currency"] in _currencies else 0)
    st.session_state.cfg["currency"] = st.selectbox(
        "Currency", _currencies, index=_cur_idx, key="si_cur",
    )

    _drift_opts   = [None] + list(range(10))
    _drift_labels = ["None (no drift)"] + [f"After day {i}" for i in range(10)]
    _drift_cur    = st.session_state.cfg["schema_drift_after_day"]
    _drift_idx    = (_drift_opts.index(_drift_cur)
                     if _drift_cur in _drift_opts else 0)
    _drift_sel    = st.selectbox(
        "Schema drift after day", _drift_labels, index=_drift_idx, key="si_drift",
    )
    st.session_state.cfg["schema_drift_after_day"] = (
        None if _drift_sel == "None (no drift)"
        else int(_drift_sel.split()[-1])
    )

    _promos_raw = st.text_input(
        "Promotion codes (comma-separated)",
        value=",".join(st.session_state.cfg["promotion_codes"]),
        key="si_promos",
    )
    st.session_state.cfg["promotion_codes"] = [
        p.strip() for p in _promos_raw.split(",")
    ]

    # ── Reproducibility ──────────────────────────────────────────────────────
    st.markdown('<p class="sidebar-section">🎲 Reproducibility</p>',
                unsafe_allow_html=True)
    _seed_on = st.checkbox(
        "Fix random seed",
        value=(st.session_state.cfg["random_seed"] is not None),
        key="si_seed_on",
    )
    if _seed_on:
        _seed_val = st.number_input(
            "Seed value", 0, 999_999,
            value=int(st.session_state.cfg["random_seed"] or 42),
            step=1, key="si_seed_val",
        )
        st.session_state.cfg["random_seed"] = int(_seed_val)
    else:
        st.session_state.cfg["random_seed"] = None

    # ── Quarantine Injection ─────────────────────────────────────────────────
    st.markdown('<p class="sidebar-section">🚨 Quarantine Injection</p>',
                unsafe_allow_html=True)
    _q_on = st.checkbox(
        "Enable quarantine injection",
        value=st.session_state.cfg["quarantine_injection"]["enabled"],
        key="si_q_on",
    )
    st.session_state.cfg["quarantine_injection"]["enabled"] = _q_on

    if _q_on:
        _tmpl_on = st.checkbox(
            "Template injection",
            value=st.session_state.cfg["quarantine_injection"]["template_injection"]["enabled"],
            key="si_tmpl_on",
        )
        st.session_state.cfg["quarantine_injection"]["template_injection"]["enabled"] = _tmpl_on

        if _tmpl_on:
            _modes    = ["random","fixed","per_day"]
            _mode_cur = st.session_state.cfg["quarantine_injection"]["template_injection"]["mode"]
            _mode_idx = _modes.index(_mode_cur) if _mode_cur in _modes else 0
            _mode_sel = st.selectbox(
                "Injection mode", _modes, index=_mode_idx, key="si_mode",
            )
            st.session_state.cfg["quarantine_injection"]["template_injection"]["mode"] = _mode_sel

            if _mode_sel == "random":
                _rc_min, _rc_max = st.slider(
                    "Injections per day (min → max)", 1, 8,
                    value=(
                        int(st.session_state.cfg["quarantine_injection"]["template_injection"]["random_count_min"]),
                        int(st.session_state.cfg["quarantine_injection"]["template_injection"]["random_count_max"]),
                    ),
                    key="si_rc",
                )
                st.session_state.cfg["quarantine_injection"]["template_injection"]["random_count_min"] = _rc_min
                st.session_state.cfg["quarantine_injection"]["template_injection"]["random_count_max"] = _rc_max

    # ── Action buttons ───────────────────────────────────────────────────────
    st.markdown("---")
    run_clicked = st.button("▶ Generate Data", use_container_width=True)

    if st.button("↺ Reset to defaults", use_container_width=True):
        st.session_state.cfg        = deepcopy(_DEFAULT_CONFIG)
        st.session_state.run_output = None
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TRIGGER GENERATION
# ══════════════════════════════════════════════════════════════════════════════

st.markdown("# 🗄️ Sample Data Generator")
st.markdown(
    "Configure pipeline parameters in the **sidebar**, then click "
    "**▶ Generate Data** to produce orders, customers, products and a "
    "quarantine log entirely in-memory — no files written to disk."
)

if run_clicked:
    _engine = _make_engine(deepcopy(st.session_state.cfg))
    with st.spinner("Generating data…"):
        try:
            st.session_state.run_output = _engine()
            st.success("✅ Data generated successfully!")
        except Exception as exc:
            st.error(f"❌ Generation failed: {exc}")
            st.session_state.run_output = None   # keep it explicitly None


# ══════════════════════════════════════════════════════════════════════════════
# RESULTS  –– only rendered when run_output is not None
# ══════════════════════════════════════════════════════════════════════════════

if st.session_state.run_output is None:
    # ── welcome / placeholder ────────────────────────────────────────────────
    st.markdown("---")
    c1, c2, c3 = st.columns(3)
    for col, icon, title, desc in [
        (c1, "📋", "Orders",
         "CSV rows with configurable volume, organic bad-row injection, "
         "and optional promotion_code schema drift."),
        (c2, "👤", "Customers",
         "JSON records with nested address & phone arrays, "
         "organic corruption, and customer-pool re-use."),
        (c3, "🚨", "Quarantine",
         "12 template-driven bad-data rules injected across "
         "both orders and customers, with a full audit log."),
    ]:
        with col:
            st.markdown(
                f'<div class="stat-card">'
                f'<div class="icon">{icon}</div>'
                f'<div class="val">{title}</div>'
                f'<div class="desc">{desc}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

else:
    # ════════════════════════════════════════════════════════════════════════
    # ALL RESULTS RENDERING IS INSIDE THIS ELSE BLOCK
    # ════════════════════════════════════════════════════════════════════════

    output   = st.session_state.run_output   # guaranteed not None here
    results  = output["results"]
    q_log    = output["quarantine_log"]
    all_ord  = output["all_orders"]
    all_cust = output["all_customers"]

    # ── top KPIs ─────────────────────────────────────────────────────────────
    total_orders    = sum(r["n_orders"]      for r in results)
    total_customers = sum(r["n_customers"]   for r in results)
    total_bad_ord   = sum(r["bad_orders"]    for r in results)
    total_bad_cust  = sum(r["bad_customers"] for r in results)

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("📦 Total Orders",      f"{total_orders:,}")
    k2.metric("👥 Total Customers",   f"{total_customers:,}")
    k3.metric(
        "⚠️ Bad Orders",
        f"{total_bad_ord:,}",
        f"{total_bad_ord / max(total_orders, 1) * 100:.1f}% of orders",
        delta_color="inverse",
    )
    k4.metric(
        "⚠️ Bad Customers",
        f"{total_bad_cust:,}",
        f"{total_bad_cust / max(total_customers, 1) * 100:.1f}% of customers",
        delta_color="inverse",
    )
    k5.metric("🚨 Quarantine Events", f"{len(q_log):,}")

    st.markdown("---")

    # ── tabs ──────────────────────────────────────────────────────────────────
    (tab_overview, tab_orders, tab_customers,
     tab_products, tab_quarantine, tab_export) = st.tabs([
        "📊 Overview", "🛒 Orders", "👥 Customers",
        "📦 Products", "🚨 Quarantine", "💾 Export",
    ])

    # ════════════════════════════════════
    # OVERVIEW
    # ════════════════════════════════════
    with tab_overview:
        st.markdown("### Daily Volume Summary")
        summary_rows = []
        for r in results:
            summary_rows.append({
                "Date":             r["date"],
                "Day":              r["day_index"],
                "Orders":           r["n_orders"],
                "Bad Orders":       r["bad_orders"],
                "Order Quality %":  f"{(1 - r['bad_orders'] / max(r['n_orders'],1)) * 100:.1f}",
                "Customers":        r["n_customers"],
                "Bad Customers":    r["bad_customers"],
                "Cust Quality %":   f"{(1 - r['bad_customers'] / max(r['n_customers'],1)) * 100:.1f}",
                "Promo Column":     "✅" if r["has_promo"] else "—",
                "Injections":       ", ".join(r["injected_tids"]) if r["injected_tids"] else "—",
            })
        st.dataframe(pd.DataFrame(summary_rows),
                     use_container_width=True, hide_index=True)

        st.markdown("### Daily Volume")
        vol_df = pd.DataFrame({
            "Date":      [r["date"]        for r in results],
            "Orders":    [r["n_orders"]    for r in results],
            "Customers": [r["n_customers"] for r in results],
        }).set_index("Date")
        st.bar_chart(vol_df, use_container_width=True)

        st.markdown("### Bad-Data Counts per Day")
        bad_df = pd.DataFrame({
            "Date":          [r["date"]          for r in results],
            "Bad Orders":    [r["bad_orders"]    for r in results],
            "Bad Customers": [r["bad_customers"] for r in results],
        }).set_index("Date")
        st.bar_chart(bad_df, use_container_width=True)

        with st.expander("🔧 Active configuration (JSON)", expanded=False):
            st.code(
                json.dumps(st.session_state.cfg, indent=2, default=str),
                language="json",
            )

    # ════════════════════════════════════
    # ORDERS
    # ════════════════════════════════════
    with tab_orders:
        st.markdown("### All Orders")

        ord_df       = pd.DataFrame(all_ord)
        date_opts    = ["All"] + sorted(ord_df["_date"].unique().tolist())
        sel_ord_date = st.selectbox("Filter by date", date_opts, key="ord_flt")
        if sel_ord_date != "All":
            ord_df = ord_df[ord_df["_date"] == sel_ord_date]

        display_ord = ord_df[[c for c in ord_df.columns if c != "_date"]]

        def _highlight_order(row):
            try:
                if float(row.get("amount", 0)) < 0:
                    return ["background-color:#3b0f0f;color:#fca5a5"] * len(row)
            except (ValueError, TypeError):
                pass
            if str(row.get("status","")) not in ORDER_STATUSES:
                return ["background-color:#3b2200;color:#fcd34d"] * len(row)
            if str(row.get("quantity","")) == "0":
                return ["background-color:#2d1a00;color:#fb923c"] * len(row)
            return [""] * len(row)

        st.dataframe(
            display_ord.style.apply(_highlight_order, axis=1),
            use_container_width=True, height=400,
        )

        st.markdown("### Per-day CSV Preview")
        for r in results:
            with st.expander(
                f"📅 {r['date']}  —  {r['n_orders']} orders  "
                f"({r['bad_orders']} bad)",
            ):
                df_day = pd.DataFrame(r["orders_raw"], columns=r["ord_cols"])
                st.dataframe(df_day, use_container_width=True, height=280)

                _csv = io.StringIO()
                _csv.write(",".join(r["ord_cols"]) + "\n")
                for _row in r["orders_raw"]:
                    _csv.write(",".join(str(v) for v in _row) + "\n")
                st.download_button(
                    f"⬇ orders_{r['date']}.csv",
                    data=_csv.getvalue(),
                    file_name=f"orders_{r['date']}.csv",
                    mime="text/csv",
                    key=f"dl_o_{r['date']}",
                )

        if "status" in ord_df.columns:
            st.markdown("### Order Status Distribution")
            _sc = (pd.DataFrame(all_ord)["status"]
                   .value_counts()
                   .reset_index()
                   .rename(columns={"index": "Status", "status": "Count"}))
            # pandas ≥ 2.0 value_counts returns named columns directly
            if "status" in _sc.columns and "count" in _sc.columns:
                _sc.columns = ["Status", "Count"]
            st.bar_chart(_sc.set_index("Status"), use_container_width=True)

    # ════════════════════════════════════
    # CUSTOMERS
    # ════════════════════════════════════
    with tab_customers:
        st.markdown("### All Customers")

        cust_df       = pd.DataFrame(all_cust)
        date_opts_c   = ["All"] + sorted(cust_df["_date"].unique().tolist())
        sel_cust_date = st.selectbox("Filter by date", date_opts_c, key="cst_flt")
        if sel_cust_date != "All":
            cust_df = cust_df[cust_df["_date"] == sel_cust_date]

        st.dataframe(
            cust_df[[c for c in cust_df.columns if c != "_date"]],
            use_container_width=True, height=380,
        )

        st.markdown("### Per-day JSON Preview")
        for r in results:
            with st.expander(
                f"📅 {r['date']}  —  {r['n_customers']} customers  "
                f"({r['bad_customers']} bad)",
            ):
                preview = r["customers_raw"][:10]
                st.json(preview)
                if len(r["customers_raw"]) > 10:
                    st.caption(
                        f"…showing first 10 of {len(r['customers_raw'])} records"
                    )
                st.download_button(
                    f"⬇ customers_{r['date']}.json",
                    data=json.dumps(r["customers_raw"], indent=2),
                    file_name=f"customers_{r['date']}.json",
                    mime="application/json",
                    key=f"dl_c_{r['date']}",
                )

        st.markdown("### Email Domain Distribution")
        _emails  = [r.get("email","") for r in all_cust
                    if isinstance(r.get("email"), str)]
        _domains = [e.split("@")[-1] if "@" in e else "invalid"
                    for e in _emails]
        _dom_df  = (pd.Series(_domains)
                    .value_counts()
                    .reset_index()
                    .rename(columns={0: "Domain", "count": "Count"}))
        # handle both pandas naming conventions
        _dom_df.columns = ["Domain", "Count"]
        st.bar_chart(_dom_df.set_index("Domain"), use_container_width=True)

    # ════════════════════════════════════
    # PRODUCTS
    # ════════════════════════════════════
    with tab_products:
        st.markdown("### Product Catalogue")
        _prod_df = pd.DataFrame(
            output["prod_initial"],
            columns=["product_id","name","category","price"],
        )
        _prod_df["price"] = _prod_df["price"].astype(float)
        st.dataframe(_prod_df, use_container_width=True, hide_index=True)

        if output["prod_updates"]:
            st.markdown(
                f"### Price Updates "
                f"*(random 30% chance — {len(output['prod_updates'])} updated)*"
            )
            _upd_df  = pd.DataFrame(
                output["prod_updates"],
                columns=["product_id","name","category","new_price"],
            )
            _upd_df["new_price"] = _upd_df["new_price"].astype(float)
            _merged  = _prod_df.merge(
                _upd_df[["product_id","new_price"]],
                on="product_id", how="inner",
            )
            _merged["Δ price"] = (_merged["new_price"] - _merged["price"]).round(2)
            _merged["change"]  = _merged["Δ price"].apply(
                lambda x: f"🔺 +{x:.2f}" if x > 0 else f"🔻 {x:.2f}"
            )
            st.dataframe(
                _merged[["product_id","name","category",
                          "price","new_price","change"]],
                use_container_width=True, hide_index=True,
            )
        else:
            st.info("No price updates this run (30% random chance per product).")

        st.markdown("### Average Price by Category")
        st.bar_chart(
            _prod_df.groupby("category")["price"]
                    .mean()
                    .rename("Avg Price"),
            use_container_width=True,
        )

    # ════════════════════════════════════
    # QUARANTINE
    # ════════════════════════════════════
    with tab_quarantine:
        if not q_log:
            st.info("No quarantine events recorded.")
        else:
            _tmpl_n = sum(1 for e in q_log if e["source"] == "template")
            _pq_n   = sum(1 for e in q_log if e["source"] == "parquet")

            qa, qb, qc = st.columns(3)
            qa.metric("Total Events",     len(q_log))
            qb.metric("Template-sourced", _tmpl_n)
            qc.metric("Parquet-sourced",  _pq_n)

            st.markdown("### Event Log")
            _q_rows = [{
                "Date":        e.get("date",""),
                "Source":      e.get("source",""),
                "Type":        e.get("type",""),
                "Template ID": e.get("template_id","—"),
                "Description": e.get("description","—"),
            } for e in q_log]
            _q_df = pd.DataFrame(_q_rows)
            st.dataframe(_q_df, use_container_width=True,
                         height=320, hide_index=True)

            st.markdown("### Events by Template ID")
            _tid_df = (_q_df[_q_df["Template ID"] != "—"]["Template ID"]
                       .value_counts()
                       .reset_index())
            _tid_df.columns = ["Template","Count"]
            if not _tid_df.empty:
                st.bar_chart(_tid_df.set_index("Template"),
                             use_container_width=True)

            st.markdown("### Events by Date")
            _date_df = (_q_df.groupby("Date").size()
                        .reset_index(name="Count"))
            st.bar_chart(_date_df.set_index("Date"), use_container_width=True)

            with st.expander("📄 Raw JSON (first 50 events)", expanded=False):
                st.json(q_log[:50])
                if len(q_log) > 50:
                    st.caption(f"…{len(q_log) - 50} more events not shown")

            st.download_button(
                "⬇ Download quarantine_log.json",
                data=json.dumps(q_log, indent=2),
                file_name="quarantine_log.json",
                mime="application/json",
            )

    # ════════════════════════════════════
    # EXPORT
    # ════════════════════════════════════
    with tab_export:
        st.markdown("### Download All Files as ZIP")
        st.markdown(
            "Packs every generated file — all daily order CSVs, customer JSONs, "
            "product catalogues, quarantine log and the active config — into one archive."
        )

        def _build_zip(out: dict, cfg: dict) -> bytes:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for r in out["results"]:
                    # orders CSV
                    _c = io.StringIO()
                    _c.write(",".join(r["ord_cols"]) + "\n")
                    for _row in r["orders_raw"]:
                        _c.write(",".join(str(v) for v in _row) + "\n")
                    zf.writestr(f"orders/orders_{r['date']}.csv", _c.getvalue())

                    # customers JSON
                    zf.writestr(
                        f"customers/customers_{r['date']}.json",
                        json.dumps(r["customers_raw"], indent=2),
                    )

                # products initial
                _p = io.StringIO()
                _p.write("product_id,name,category,price\n")
                for _row in out["prod_initial"]:
                    _p.write(",".join(str(v) for v in _row) + "\n")
                zf.writestr("products/products_initial.csv", _p.getvalue())

                # products updates
                if out["prod_updates"]:
                    _pu = io.StringIO()
                    _pu.write("product_id,name,category,price\n")
                    for _row in out["prod_updates"]:
                        _pu.write(",".join(str(v) for v in _row) + "\n")
                    zf.writestr("products/products_updates.csv", _pu.getvalue())

                # quarantine log
                if out["quarantine_log"]:
                    zf.writestr(
                        "quarantine/quarantine_log.json",
                        json.dumps(out["quarantine_log"], indent=2),
                    )

                # config snapshot
                zf.writestr(
                    "config.json",
                    json.dumps(cfg, indent=2, default=str),
                )

            buf.seek(0)
            return buf.read()

        st.download_button(
            "⬇ Download all_data.zip",
            data=_build_zip(output, st.session_state.cfg),
            file_name="all_data.zip",
            mime="application/zip",
            use_container_width=True,
        )

        st.markdown("---")
        st.markdown("### Individual File Downloads")
        col_l, col_r = st.columns(2)

        with col_l:
            st.markdown("**📂 Orders (CSV)**")
            for r in results:
                _c = io.StringIO()
                _c.write(",".join(r["ord_cols"]) + "\n")
                for _row in r["orders_raw"]:
                    _c.write(",".join(str(v) for v in _row) + "\n")
                st.download_button(
                    f"orders_{r['date']}.csv  ({r['n_orders']} rows)",
                    data=_c.getvalue(),
                    file_name=f"orders_{r['date']}.csv",
                    mime="text/csv",
                    key=f"exp_o_{r['date']}",
                )

            st.markdown("**📦 Products**")
            _p = io.StringIO()
            _p.write("product_id,name,category,price\n")
            for _row in output["prod_initial"]:
                _p.write(",".join(str(v) for v in _row) + "\n")
            st.download_button(
                "products_initial.csv",
                data=_p.getvalue(),
                file_name="products_initial.csv",
                mime="text/csv",
                key="exp_prod",
            )

        with col_r:
            st.markdown("**📂 Customers (JSON)**")
            for r in results:
                st.download_button(
                    f"customers_{r['date']}.json  ({r['n_customers']} records)",
                    data=json.dumps(r["customers_raw"], indent=2),
                    file_name=f"customers_{r['date']}.json",
                    mime="application/json",
                    key=f"exp_c_{r['date']}",
                )

            if q_log:
                st.markdown("**🚨 Quarantine**")
                st.download_button(
                    f"quarantine_log.json  ({len(q_log)} events)",
                    data=json.dumps(q_log, indent=2),
                    file_name="quarantine_log.json",
                    mime="application/json",
                    key="exp_q",
                )