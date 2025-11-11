from __future__ import annotations

import csv
import zipfile
from difflib import get_close_matches
from typing import Dict, List, Tuple
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import check_password_hash, generate_password_hash

try:
    from bs4 import BeautifulSoup
except ImportError:
    raise SystemExit("Missing dependency: beautifulsoup4. Install with: pip install beautifulsoup4")


app = Flask(__name__)
app.secret_key = "expert-system-demo"  # for flash messages only


# ----------------------
# Auth (very simple demo)
# ----------------------

USERS = {
    # username: {password_hash, role}
    # role: 'manager' can modify CSVs, 'user' can only view
    "admin": {
        "password_hash": generate_password_hash("admin123"),
        "role": "manager",
    },
    "user": {
        "password_hash": generate_password_hash("user123"),
        "role": "user",
    },
}


def login_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("login", next=request.path))
        return view_func(*args, **kwargs)

    return wrapper


def role_required(required_role: str):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            if not session.get("user"):
                return redirect(url_for("login", next=request.path))
            if session.get("role") != required_role:
                flash("You do not have permission to access this page.")
                return redirect(url_for("home"))
            return view_func(*args, **kwargs)

        return wrapper

    return decorator


# ----------------------
# Localization helpers (EN <-> VI)
# ----------------------

def _norm(s: str | None) -> str:
    return (s or "").strip().lower()


GOV_MAP = {
    "democracy": "dân chủ",
    "communist": "cộng sản",
    "monarchy": "quân chủ",
    "republic": "cộng hòa",
    "federal": "liên bang",
}
GOV_REV = {v: k for k, v in GOV_MAP.items()}

FIELD_MAP = {
    "technology": "công nghệ",
    "manufacturing": "sản xuất",
    "tourism": "du lịch",
    "infrastructure": "hạ tầng",
}
FIELD_REV = {v: k for k, v in FIELD_MAP.items()}

RELIGION_MAP = {
    "christianity": "thiên chúa giáo",
    "buddhism": "phật giáo",
    "hinduism": "ấn độ giáo",
    "islam": "hồi giáo",
    "atheist": "vô thần",
}
RELIGION_REV = {v: k for k, v in RELIGION_MAP.items()}

CLIMATE_MAP = {
    "cold": "lạnh",
    "moderate": "ôn hòa",
    "hot": "nóng",
}
CLIMATE_REV = {v: k for k, v in CLIMATE_MAP.items()}

TRADE_MAP = {
    "import": "nhập khẩu",
    "export": "xuất khẩu",
}
TRADE_REV = {v: k for k, v in TRADE_MAP.items()}

PLACE_MAP = {
    "historical": "lịch sử",
    "hill station": "núi đồi",
    "desert": "sa mạc",
    "beach": "biển",
}
PLACE_REV = {v: k for k, v in PLACE_MAP.items()}


def normalize_government(value: str | None) -> str:
    v = _norm(value)
    if v in GOV_MAP:  # english
        return v
    if v in GOV_REV:  # vietnamese
        return GOV_REV[v]
    return v


def normalize_field(value: str | None) -> str:
    v = _norm(value)
    if v in FIELD_MAP:
        return v
    if v in FIELD_REV:
        return FIELD_REV[v]
    return v


def normalize_religion(value: str | None) -> str:
    v = _norm(value)
    if v in RELIGION_MAP:
        return v
    if v in RELIGION_REV:
        return RELIGION_REV[v]
    return v


def normalize_climate(value: str | None) -> str:
    v = _norm(value)
    if v in CLIMATE_MAP:
        return v
    if v in CLIMATE_REV:
        return CLIMATE_REV[v]
    return v


def normalize_trade(value: str | None) -> str:
    v = _norm(value)
    if v in TRADE_MAP:
        return v
    if v in TRADE_REV:
        return TRADE_REV[v]
    return v


def normalize_place_type(value: str | None) -> str:
    v = _norm(value)
    if v in PLACE_MAP:
        return v
    if v in PLACE_REV:
        return PLACE_REV[v]
    return v


def get_field(info: Dict[str, str], en: str, vi: str) -> str:
    # read value from dict supporting both EN and VI headers
    return info.get(en) or info.get(vi) or ""


# ----------------------
# Data loading utilities
# ----------------------

def load_country_list() -> List[str]:
    countries: List[str] = []
    with open("countryList.txt", "r", encoding="utf-8") as fh:
        for line in fh:
            # Lines are like: "us United States" ⇒ first 2 chars are country file code
            name = line[3:].strip()
            if name:
                countries.append(name)
    return countries


def code_for_country(target_country: str) -> str | None:
    with open("countryList.txt", "r", encoding="utf-8") as fh:
        for line in fh:
            if target_country in line:
                return line[:2]
    return None


def parse_html_from_zip(country_code: str) -> Dict[str, str]:
    page = f"{country_code}.html"
    with zipfile.ZipFile("countries.zip", "r") as archive:
        with archive.open(page, "r") as html_file:
            return parse_html(html_file)


def parse_html(html_file) -> Dict[str, str]:
    soup = BeautifulSoup(html_file, "html.parser")

    possibilities: Dict[str, str] = {}

    for attr in soup.find_all("div", class_="category"):
        a_tag = attr.find("a")
        if not a_tag:
            continue

        tr_tag = attr.parent.parent.find_next_sibling("tr")
        if not tr_tag:
            continue

        if len(tr_tag) > 1:
            contents: List[str] = []
            for div in tr_tag.find_all("div", class_="category"):
                if div.contents:
                    first = div.contents[0]
                    if isinstance(first, str):
                        first_text = first.strip()
                        if first_text:
                            contents.append(first_text)
                for span in div.find_all("span"):
                    text = span.get_text(strip=True)
                    if text:
                        contents.append(text)

            for div in tr_tag.find_all("div", class_="category_data"):
                text = div.get_text(strip=True)
                if text:
                    contents.append(text)

            data = "\r\n".join(contents)
        elif tr_tag.find("td"):
            data = tr_tag.find("td").find("div", class_="category_data").get_text(strip=True)
        else:
            data = tr_tag.find("div", class_="category_data").get_text(strip=True)

        title = format_key(a_tag.string or "")
        if not title:
            continue

        if title in possibilities:
            data = possibilities[title] + "\r\n" + data

        possibilities[title] = data

    return possibilities


def format_key(key: str) -> str:
    words = key.split()
    temp: List[str] = []
    for word in words:
        if word == "-":
            break
        temp.append(word)
    return " ".join(temp)


def load_country_details() -> Dict[str, Dict[str, str]]:
    country_details: Dict[str, Dict[str, str]] = {}
    rows: List[List[str]] = []
    with open("countries.csv", "r", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        for row in reader:
            rows.append([cell.lower() for cell in row])

    if not rows:
        return country_details

    header = rows[0]
    for i in range(1, len(rows)):
        country_details[rows[i][0]] = {}
    for i in range(1, len(rows)):
        for j in range(len(header)):
            if header[j] and rows[i][j]:
                country_details[rows[i][0]][header[j]] = rows[i][j]
    return country_details


def load_tourism_data() -> Dict[str, Dict[str, str]]:
    tourism: Dict[str, Dict[str, str]] = {}
    rows: List[List[str]] = []
    with open("Tourism.csv", "r", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        for row in reader:
            rows.append([cell.lower() for cell in row])
    if not rows:
        return tourism
    header = rows[0]
    for i in range(1, len(rows)):
        tourism[rows[i][0]] = {}
    for i in range(1, len(rows)):
        for j in range(len(header)):
            if header[j] and rows[i][j]:
                tourism[rows[i][0]][header[j]] = rows[i][j]
    return tourism


# ----------------------
# CSV read/write helpers
# ----------------------

def read_csv_file(path: str) -> Tuple[List[str], List[List[str]]]:
    with open(path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        rows = list(reader)
    if not rows:
        return [], []
    header = rows[0]
    data_rows = rows[1:]
    return header, data_rows


def write_csv_file(path: str, header: List[str], rows: List[List[str]]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)


# -------------
# Web endpoints
# -------------


# Enforce login for all non-exempt routes
EXEMPT_PATHS = {"/login"}


@app.before_request
def require_login_globally():
    path = request.path or "/"
    if path.startswith("/static/"):
        return  # allow static files
    if path in EXEMPT_PATHS:
        return  # allow login page
    if not session.get("user"):
        # remember where to go after login
        next_url = request.full_path if request.query_string else request.path
        return redirect(url_for("login", next=next_url))


@app.get("/")
def home():
    return render_template("index.html")


@app.get("/login")
def login():
    return render_template("login.html")


@app.post("/login")
def do_login():
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    user = USERS.get(username)
    if not user or not check_password_hash(user["password_hash"], password):
        flash("Invalid username or password.")
        return redirect(url_for("login"))
    session["user"] = username
    session["role"] = user["role"]
    next_url = request.args.get("next") or url_for("home")
    return redirect(next_url)


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.get("/countries")
def countries():
    return render_template("countries.html", countries=load_country_list())


@app.get("/search")
def search_page():
    return render_template("search.html", countries=load_country_list(), results=None, query=None, country=None)


@app.post("/search")
def do_search():
    country = request.form.get("country", "").strip()
    query = (request.form.get("query", "") or "").lower()
    if not country:
        flash("Please select a country.")
        return redirect(url_for("search_page"))

    code = code_for_country(country)
    if not code:
        flash("Country not found in list.")
        return redirect(url_for("search_page"))

    possibilities = parse_html_from_zip(code)

    special = query.strip()
    if special.startswith(";lst") or special.startswith(";keys") or special.startswith(";matches"):
        if special.startswith(";lst"):
            results = [(k, possibilities[k]) for k in possibilities.keys()]
        elif special.startswith(";keys"):
            results = [(k, "") for k in possibilities.keys()]
        else:
            # Syntax: ";matches <keyword>"
            pattern = special.split(" ", 1)[1].strip() if " " in special else ""
            keys = list(possibilities.keys())
            if pattern:
                matches = get_close_matches(pattern, keys, n=20, cutoff=0.3)
            else:
                matches = keys[:20]
            results = [(m, possibilities.get(m, "")) for m in matches]
        return render_template("search.html", countries=load_country_list(), results=results, query=query, country=country)

    keys = list(possibilities.keys())
    matches = get_close_matches(query, keys)
    results: List[tuple[str, str]] = []
    if matches:
        for m in matches:
            results.append((m, possibilities[m]))
    return render_template("search.html", countries=load_country_list(), results=results, query=query, country=country)


@app.get("/expert")
def expert_page():
    return render_template("expert.html", result=None, section=None)


@app.post("/expert/live")
def expert_live():
    details = load_country_details()
    density = request.form.get("density")  # not used in current filter
    climate = normalize_climate(request.form.get("climate"))
    government = normalize_government(request.form.get("government"))
    religion = normalize_religion(request.form.get("religion"))

    possible: List[str] = []
    for name, info in details.items():
        info_climate = normalize_climate(get_field(info, "average weather", "khi hậu trung bình"))
        info_gov = normalize_government(get_field(info, "type of government", "hình thức chính phủ"))
        info_rel = normalize_religion(get_field(info, "major religion", "tôn giáo chính"))
        if info_climate == climate and info_gov == government and info_rel == religion:
            possible.append(name)

    return render_template("expert.html", section="live", result=possible)


@app.post("/expert/work")
def expert_work():
    details = load_country_details()
    mode = request.form.get("mode")  # business or job
    domain = normalize_field(request.form.get("domain"))
    result: List[str] = []

    if mode == "business":
        trade = normalize_trade(request.form.get("trade"))  # import/export
        for name, info in details.items():
            info_trade = normalize_trade(get_field(info, "trade type", "loại thương mại"))
            info_field = normalize_field(get_field(info, "field domain", "lĩnh vực"))
            if info_trade == trade and info_field == domain:
                result.append(name)
    else:
        for name, info in details.items():
            info_field = normalize_field(get_field(info, "field domain", "lĩnh vực"))
            if info_field == domain:
                result.append(name)

    return render_template("expert.html", section="work", result=result)


@app.post("/expert/travel")
def expert_travel():
    tourism = load_tourism_data()
    budget = request.form.get("budget")
    place_type = request.form.get("place_type")

    budget_map = {"vnd_under_30m": 0.5, "vnd_30_60m": 1.5, "vnd_above_60m": 2.5}
    target = budget_map.get(budget)

    result: List[str] = []
    if target is not None:
        for place, info in tourism.items():
            info_place = normalize_place_type(get_field(info, "type of place", "loại địa điểm"))
            if info_place == normalize_place_type(place_type) and float(get_field(info, "budget", "ngân sách") or 0) == target:
                # decorate with VND label
                if target == 0.5:
                    label = "Dưới 30.000.000 VND"
                elif target == 1.5:
                    label = "30–60 triệu VND"
                else:
                    label = "Trên 60.000.000 VND"
                result.append(f"{place}, {get_field(info, 'country', 'quốc gia')} — ngân sách: {label}")

    return render_template("expert.html", section="travel", result=result)


# ----------------------
# Admin migration to Vietnamese CSV
# ----------------------

COUNTRIES_HEADER_MAP = {
    "Country": "Quốc gia",
    "Type of Government": "Hình thức chính phủ",
    "Field Domain": "Lĩnh vực",
    "Major Religion": "Tôn giáo chính",
    "GDP": "GDP",
    "Population Density": "Mật độ dân số",
    "Average weather": "Khí hậu trung bình",
    "Import": "Nhập khẩu",
    "Export": "Xuất khẩu",
    "Trade type": "Loại thương mại",
}

TOURISM_HEADER_MAP = {
    "Name of place": "Điểm đến",
    "Country": "Quốc gia",
    "Budget": "Ngân sách",
    "Type of place": "Loại địa điểm",
}


def _map_header(header: List[str], mapping: Dict[str, str]) -> List[str]:
    new = []
    for h in header:
        if not h:
            continue
        new.append(mapping.get(h, h))
    return new


def _map_value(col_name_vi_or_en: str, value: str) -> str:
    c = _norm(col_name_vi_or_en)
    v = _norm(value)
    # Values mapping depending on semantic columns
    if c in {"type of government", "hình thức chính phủ"}:
        return GOV_MAP.get(v, GOV_MAP.get(GOV_REV.get(v, ""), value)) if v else value
    if c in {"field domain", "lĩnh vực"}:
        return FIELD_MAP.get(v, FIELD_MAP.get(FIELD_REV.get(v, ""), value)) if v else value
    if c in {"major religion", "tôn giáo chính"}:
        return RELIGION_MAP.get(v, RELIGION_MAP.get(RELIGION_REV.get(v, ""), value)) if v else value
    if c in {"average weather", "khí hậu trung bình"}:
        return CLIMATE_MAP.get(v, CLIMATE_MAP.get(CLIMATE_REV.get(v, ""), value)) if v else value
    if c in {"trade type", "loại thương mại"}:
        return TRADE_MAP.get(v, TRADE_MAP.get(TRADE_REV.get(v, ""), value)) if v else value
    if c in {"type of place", "loại địa điểm"}:
        return PLACE_MAP.get(v, PLACE_MAP.get(PLACE_REV.get(v, ""), value)) if v else value
    return value


@app.post("/admin/migrate_vi")
@login_required
@role_required("manager")
def admin_migrate_vi():
    # Countries.csv
    h, rows = read_csv_file("countries.csv")
    if h:
        # clean out empty trailing headers
        h = [x for x in h if x]
        new_h = _map_header(h, COUNTRIES_HEADER_MAP)
        new_rows: List[List[str]] = []
        for r in rows:
            # truncate/extend to header length
            r = (r + [""] * len(new_h))[: len(new_h)]
            mapped = []
            for idx, val in enumerate(r):
                col_en = h[idx] if idx < len(h) else ""
                col_vi = COUNTRIES_HEADER_MAP.get(col_en, col_en)
                mapped.append(_map_value(col_vi, val))
            new_rows.append(mapped)
        write_csv_file("countries.csv", new_h, new_rows)

    # Tourism.csv
    h2, rows2 = read_csv_file("Tourism.csv")
    if h2:
        new_h2 = _map_header(h2, TOURISM_HEADER_MAP)
        new_rows2: List[List[str]] = []
        for r in rows2:
            r = (r + [""] * len(new_h2))[: len(new_h2)]
            mapped = []
            for idx, val in enumerate(r):
                col_en = h2[idx] if idx < len(h2) else ""
                col_vi = TOURISM_HEADER_MAP.get(col_en, col_en)
                mapped.append(_map_value(col_vi, val))
            new_rows2.append(mapped)
        write_csv_file("Tourism.csv", new_h2, new_rows2)

    flash("Đã chuyển đổi tiêu đề và một số giá trị sang tiếng Việt.")
    return redirect(url_for("admin_dashboard"))


# ----------------------
# Admin endpoints
# ----------------------

@app.get("/admin")
@login_required
@role_required("manager")
def admin_dashboard():
    return render_template("admin.html")


@app.get("/admin/countries")
@login_required
@role_required("manager")
def admin_countries():
    header, rows = read_csv_file("countries.csv")
    key = request.args.get("key")
    existing = None
    if key and header:
        for r in rows:
            if r and r[0].lower() == key.lower():
                existing = dict(zip(header, r))
                break
    return render_template("admin_countries.html", header=header, rows=rows[:50], existing=existing)


@app.post("/admin/countries")
@login_required
@role_required("manager")
def admin_countries_save():
    header, rows = read_csv_file("countries.csv")
    if not header:
        flash("countries.csv is empty or missing header.")
        return redirect(url_for("admin_countries"))

    # Build row in header order; allow missing fields as empty string
    form = request.form
    original_key = (form.get("_original_key") or "").strip()
    new_row: List[str] = []
    for col in header:
        new_row.append((form.get(col) or "").strip())

    key = new_row[0].strip()
    if not key:
        flash(f"'{header[0]}' is required.")
        return redirect(url_for("admin_countries"))

    # Enforce uniqueness of primary key (case-insensitive)
    keys_lower = [r[0].lower() for r in rows if r]
    if not original_key:
        # Creating new record
        if key.lower() in keys_lower:
            flash(f"Record with {header[0]}='{key}' already exists. Use Edit to modify.")
            return redirect(url_for("admin_countries", key=key))
        rows.append(new_row)
    else:
        # Updating existing record identified by original_key
        # If user changed key, ensure it doesn't collide with another record
        if key.lower() != original_key.lower() and key.lower() in keys_lower:
            flash(f"Cannot change {header[0]} to '{key}' because it already exists.")
            return redirect(url_for("admin_countries", key=original_key))
        updated = False
        for i, r in enumerate(rows):
            if r and r[0].lower() == original_key.lower():
                rows[i] = new_row
                updated = True
                break
        if not updated:
            # If original not found, treat as create but still ensure uniqueness (handled above)
            rows.append(new_row)

    write_csv_file("countries.csv", header, rows)
    flash("countries.csv has been updated.")
    return redirect(url_for("admin_countries", key=key))


@app.get("/admin/tourism")
@login_required
@role_required("manager")
def admin_tourism():
    header, rows = read_csv_file("Tourism.csv")
    key = request.args.get("key")
    existing = None
    if key and header:
        for r in rows:
            if r and r[0].lower() == key.lower():
                existing = dict(zip(header, r))
                break
    return render_template("admin_tourism.html", header=header, rows=rows[:50], existing=existing)


@app.post("/admin/tourism")
@login_required
@role_required("manager")
def admin_tourism_save():
    header, rows = read_csv_file("Tourism.csv")
    if not header:
        flash("Tourism.csv is empty or missing header.")
        return redirect(url_for("admin_tourism"))

    form = request.form
    original_key = (form.get("_original_key") or "").strip()
    new_row: List[str] = []
    for col in header:
        new_row.append((form.get(col) or "").strip())

    key = new_row[0].strip()
    if not key:
        flash(f"'{header[0]}' is required.")
        return redirect(url_for("admin_tourism"))

    # Enforce uniqueness of primary key (case-insensitive)
    keys_lower = [r[0].lower() for r in rows if r]
    if not original_key:
        if key.lower() in keys_lower:
            flash(f"Record with {header[0]}='{key}' already exists. Use Edit to modify.")
            return redirect(url_for("admin_tourism", key=key))
        rows.append(new_row)
    else:
        if key.lower() != original_key.lower() and key.lower() in keys_lower:
            flash(f"Cannot change {header[0]} to '{key}' because it already exists.")
            return redirect(url_for("admin_tourism", key=original_key))
        updated = False
        for i, r in enumerate(rows):
            if r and r[0].lower() == original_key.lower():
                rows[i] = new_row
                updated = True
                break
        if not updated:
            rows.append(new_row)

    write_csv_file("Tourism.csv", header, rows)
    flash("Tourism.csv has been updated.")
    return redirect(url_for("admin_tourism", key=key))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)


