from __future__ import annotations

import csv
import json
import os
import zipfile
from difflib import get_close_matches
from typing import Any, Callable, Dict, List, Tuple
from functools import wraps, lru_cache

from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import check_password_hash, generate_password_hash

try:
    from bs4 import BeautifulSoup
except ImportError:
    raise SystemExit("Missing dependency: beautifulsoup4. Install with: pip install beautifulsoup4")

try:
    # Dùng Google Translate qua deep-translator để dịch EN -> VI cho phần tra cứu
    from deep_translator import GoogleTranslator
except ImportError:
    GoogleTranslator = None  # type: ignore[assignment]


app = Flask(__name__)
app.secret_key = "expert-system-demo"  # for flash messages only


# ----------------------
# Translation helper cho bước dịch TRƯỚC (EN -> VI) dùng trong script pretranslate_search.py.
# Ở runtime, web app CHỈ đọc từ cache search_vi_cache.json, không gọi dịch nữa.
# ----------------------

if GoogleTranslator is not None:
    _translator_en_vi: GoogleTranslator | None = GoogleTranslator(source="en", target="vi")
else:
    _translator_en_vi = None


@lru_cache(maxsize=4096)
def translate_en_vi(text: str | None) -> str:
    """Dịch EN -> VI để tạo cache bằng Google Translate (deep-translator).

    - Nếu thiếu thư viện / lỗi mạng thì trả lại tiếng Anh để không làm hỏng script.
    """
    text_norm = (text or "").strip()
    if not text_norm:
        return ""
    if _translator_en_vi is None:
        return text_norm
    # Giới hạn độ dài để tránh lỗi từ dịch vụ; nếu quá dài thì giữ nguyên.
    if len(text_norm) > 4000:
        return text_norm
    try:
        return _translator_en_vi.translate(text_norm)  # type: ignore[call-arg]
    except Exception:
        return text_norm


# ----------------------
# Cache đã dịch sẵn cho phần tra cứu (nếu có)
# ----------------------

def _load_search_vi_cache() -> Dict[str, Dict[str, Dict[str, str]]]:
    """Đọc file cache đã dịch sẵn (do script pretranslate_search.py tạo)."""
    path = "search_vi_cache.json"
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data  # type: ignore[return-value]
    except Exception:
        return {}
    return {}


SEARCH_VI_CACHE: Dict[str, Dict[str, Dict[str, str]]] = _load_search_vi_cache()


def get_vi_key_val(country_code: str, key_en: str, val_en: str) -> Tuple[str, str]:
    """Lấy tiêu đề và nội dung tiếng Việt từ cache; nếu không có thì fallback về EN."""
    country = SEARCH_VI_CACHE.get(country_code.lower()) or {}
    entry = country.get(key_en) or {}
    key_vi = entry.get("key_vi") or key_en
    val_vi = entry.get("val_vi") or val_en
    return key_vi, val_vi


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
# Simple forward-chaining engine for expert rules
# ----------------------

CountryFacts = Dict[str, Any]
Rule = Callable[[str, Dict[str, str], Dict[str, Any], CountryFacts], bool]


def forward_chain_for_country(
    name: str, info: Dict[str, str], context: Dict[str, Any], rules: List[Rule]
) -> CountryFacts:
    """Áp dụng các luật suy diễn tiến cho một quốc gia.

    - facts: tập các sự kiện đã suy ra cho quốc gia đó.
    - Mỗi rule() trả về True nếu tạo ra sự kiện mới, cho phép vòng lặp tiếp tục.
    """
    facts: CountryFacts = {}
    changed = True
    while changed:
        changed = False
        for rule in rules:
            if rule(name, info, context, facts):
                changed = True
    return facts


# ---- Luật cho gợi ý Sống ----

def rule_live_climate(name: str, info: Dict[str, str], ctx: Dict[str, Any], facts: CountryFacts) -> bool:
    if facts.get("climate_match") or not ctx.get("climate"):
        return False
    info_climate = normalize_climate(get_field(info, "average weather", "khí hậu trung bình"))
    if info_climate == ctx["climate"]:
        facts["climate_match"] = True
        return True
    return False


def rule_live_government(name: str, info: Dict[str, str], ctx: Dict[str, Any], facts: CountryFacts) -> bool:
    if facts.get("gov_match") or not ctx.get("government"):
        return False
    info_gov = normalize_government(get_field(info, "type of government", "hình thức chính phủ"))
    if info_gov == ctx["government"]:
        facts["gov_match"] = True
        return True
    return False


def rule_live_religion(name: str, info: Dict[str, str], ctx: Dict[str, Any], facts: CountryFacts) -> bool:
    if facts.get("religion_match") or not ctx.get("religion"):
        return False
    info_rel = normalize_religion(get_field(info, "major religion", "tôn giáo chính"))
    if info_rel == ctx["religion"]:
        facts["religion_match"] = True
        return True
    return False


def rule_live_selected(name: str, info: Dict[str, str], ctx: Dict[str, Any], facts: CountryFacts) -> bool:
    if facts.get("selected"):
        return False
    if facts.get("climate_match") and facts.get("gov_match") and facts.get("religion_match"):
        facts["selected"] = True
        return True
    return False


LIVE_RULES: List[Rule] = [
    rule_live_climate,
    rule_live_government,
    rule_live_religion,
    rule_live_selected,
]


# ---- Luật cho gợi ý Làm việc ----

def rule_work_field(name: str, info: Dict[str, str], ctx: Dict[str, Any], facts: CountryFacts) -> bool:
    if facts.get("field_match") or not ctx.get("domain"):
        return False
    info_field = normalize_field(get_field(info, "field domain", "lĩnh vực"))
    if info_field == ctx["domain"]:
        facts["field_match"] = True
        return True
    return False


def rule_work_trade(name: str, info: Dict[str, str], ctx: Dict[str, Any], facts: CountryFacts) -> bool:
    # Chỉ áp dụng khi chế độ là "business"
    if ctx.get("mode") != "business" or facts.get("trade_match") or not ctx.get("trade"):
        return False
    info_trade = normalize_trade(get_field(info, "trade type", "loại thương mại"))
    if info_trade == ctx["trade"]:
        facts["trade_match"] = True
        return True
    return False


def rule_work_selected(name: str, info: Dict[str, str], ctx: Dict[str, Any], facts: CountryFacts) -> bool:
    if facts.get("selected"):
        return False
    # Nếu là business: cần cả field_match và trade_match.
    # Nếu là job: chỉ cần field_match.
    if ctx.get("mode") == "business":
        if facts.get("field_match") and facts.get("trade_match"):
            facts["selected"] = True
            return True
    else:
        if facts.get("field_match"):
            facts["selected"] = True
            return True
    return False


WORK_RULES: List[Rule] = [
    rule_work_field,
    rule_work_trade,
    rule_work_selected,
]

def describe_country(name: str, info: Dict[str, str]) -> str:
    """Tạo câu mô tả ngắn gọn về một quốc gia dựa trên dữ liệu CSV."""
    gov_en = normalize_government(get_field(info, "type of government", "hình thức chính phủ"))
    field_en = normalize_field(get_field(info, "field domain", "lĩnh vực"))
    rel_en = normalize_religion(get_field(info, "major religion", "tôn giáo chính"))
    climate_en = normalize_climate(get_field(info, "average weather", "khí hậu trung bình"))

    gov = GOV_MAP.get(gov_en, gov_en or "không rõ")
    field = FIELD_MAP.get(field_en, field_en or "không rõ")
    rel = RELIGION_MAP.get(rel_en, rel_en or "không rõ")
    climate = CLIMATE_MAP.get(climate_en, climate_en or "không rõ")

    density = get_field(info, "population density", "mật độ dân số")
    gdp = get_field(info, "gdp", "gdp")

    parts: List[str] = []
    if gov:
        parts.append(f"hình thức chính phủ {gov}")
    if field:
        parts.append(f"thế mạnh về lĩnh vực {field}")
    if rel:
        parts.append(f"tôn giáo chính là {rel}")
    if climate:
        parts.append(f"khí hậu trung bình {climate}")
    if density:
        parts.append(f"mật độ dân số khoảng {density} người/km²")
    if gdp:
        parts.append(f"GDP khoảng {gdp} tỷ USD")

    detail = "; ".join(parts) if parts else "thông tin chi tiết đang được cập nhật"
    return f"Với các điều kiện mà bạn chọn thì nơi phù hợp sẽ là {name}. Quốc gia này có {detail}."


def describe_place(place: str, info: Dict[str, str], target_budget: float, selected_type: str | None) -> str:
    """Tạo câu mô tả ngắn gọn về một điểm đến du lịch."""
    country = get_field(info, "country", "quốc gia") or "một quốc gia phù hợp"
    budget_val = target_budget
    if budget_val == 0.5:
        label = "dưới 30.000.000 VND"
    elif budget_val == 1.5:
        label = "khoảng 30–60 triệu VND"
    else:
        label = "trên 60.000.000 VND"

    place_type_en = normalize_place_type(get_field(info, "type of place", "loại địa điểm") or selected_type)
    place_type_vi = PLACE_MAP.get(place_type_en, place_type_en or "điểm tham quan")

    return (
        f"Với ngân sách {label} cho mỗi người và mong muốn trải nghiệm kiểu địa điểm {place_type_vi}, "
        f"điểm đến phù hợp là {place} tại {country}."
    )


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
EXEMPT_PATHS = {"/login", "/register"}


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


@app.get("/register")
def register():
    return render_template("register.html")


@app.post("/register")
def do_register():
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    password2 = request.form.get("password2") or ""

    if not username or not password:
        flash("Vui lòng nhập đầy đủ tài khoản và mật khẩu.")
        return redirect(url_for("register", next=request.args.get("next")))

    if password != password2:
        flash("Mật khẩu nhập lại không khớp.")
        return redirect(url_for("register", next=request.args.get("next")))

    # Kiểm tra trùng tài khoản (không phân biệt hoa thường)
    existing_usernames = {u.lower() for u in USERS.keys()}
    if username.lower() in existing_usernames:
        flash("Tài khoản đã tồn tại, vui lòng chọn tên khác.")
        return redirect(url_for("register", next=request.args.get("next")))

    # Tạo tài khoản mới với quyền 'user'
    USERS[username] = {
        "password_hash": generate_password_hash(password),
        "role": "user",
    }

    # Đăng nhập luôn sau khi đăng ký thành công
    session["user"] = username
    session["role"] = "user"
    next_url = request.args.get("next") or url_for("home")
    flash("Đăng ký tài khoản thành công.")
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
    query_raw = (request.form.get("query", "") or "")
    # Giữ bản gốc để hiển thị lại, lower-case chỉ dùng cho kiểm tra tiền tố ;lst, ;keys, ;matches
    query = query_raw.lower()
    if not country:
        flash("Please select a country.")
        return redirect(url_for("search_page"))

    code = code_for_country(country)
    if not code:
        flash("Country not found in list.")
        return redirect(url_for("search_page"))

    code = code.lower()
    possibilities = parse_html_from_zip(code)

    special = query.strip()
    if special.startswith(";lst") or special.startswith(";keys") or special.startswith(";matches"):
        if special.startswith(";lst"):
            # Liệt kê toàn bộ: ưu tiên dùng bản dịch đã cache sẵn (nếu có)
            results = [get_vi_key_val(code, k, possibilities[k]) for k in possibilities.keys()]
        elif special.startswith(";keys"):
            # Chỉ danh sách đầu mục: dùng key đã dịch sẵn
            results = [(get_vi_key_val(code, k, "")[0], "") for k in possibilities.keys()]
        else:
            # Syntax: ";matches <keyword>" – cho phép keyword là tiếng Việt.
            # Vì đã có cache tiếng Việt, ta so khớp trực tiếp trên tiêu đề VI.
            pattern_vi = special.split(" ", 1)[1].strip() if " " in special else ""
            keys = list(possibilities.keys())
            # Map từ key EN -> key VI đã cache (hoặc EN nếu chưa có trong cache)
            vi_keys = {k: get_vi_key_val(code, k, "")[0] for k in keys}
            if pattern_vi:
                matches_vi = get_close_matches(pattern_vi.lower(), [v.lower() for v in vi_keys.values()], n=20, cutoff=0.3)
                # Tìm lại key EN tương ứng với mỗi key VI khớp
                matches: List[str] = []
                for mv in matches_vi:
                    for k, v in vi_keys.items():
                        if v.lower() == mv and k not in matches:
                            matches.append(k)
                            break
            else:
                matches = keys[:20]
            results = []
            for m in matches:
                key_vi, val_vi = get_vi_key_val(code, m, possibilities.get(m, ""))
                results.append((key_vi, val_vi))
        return render_template("search.html", countries=load_country_list(), results=results, query=query, country=country)

    keys = list(possibilities.keys())
    # Người dùng gõ tiếng Việt: so khớp trực tiếp với tiêu đề VI trong cache
    vi_keys = {k: get_vi_key_val(code, k, "")[0] for k in keys}
    matches_vi = get_close_matches(query.strip().lower(), [v.lower() for v in vi_keys.values()])
    # Chuyển ngược về key EN
    matches: List[str] = []
    for mv in matches_vi:
        for k, v in vi_keys.items():
            if v.lower() == mv and k not in matches:
                matches.append(k)
                break
    results: List[tuple[str, str]] = []
    if matches:
        for m in matches:
            key_vi, val_vi = get_vi_key_val(code, m, possibilities[m])
            results.append((key_vi, val_vi))
    return render_template("search.html", countries=load_country_list(), results=results, query=query, country=country)


@app.get("/expert")
def expert_page():
    return render_template(
        "expert.html",
        result=None,
        section=None,
        density=None,
        climate=None,
        government=None,
        religion=None,
        mode=None,
        trade=None,
        domain=None,
        budget=None,
        place_type=None,
    )


@app.post("/expert/live")
def expert_live():
    details = load_country_details()
    density = request.form.get("density")  # not used in current filter
    climate_raw = request.form.get("climate")
    government_raw = request.form.get("government")
    religion_raw = request.form.get("religion")

    # Chuẩn hóa input người dùng thành context cho bộ suy diễn
    context = {
        "climate": normalize_climate(climate_raw),
        "government": normalize_government(government_raw),
        "religion": normalize_religion(religion_raw),
    }

    result: List[Dict[str, str]] = []
    for name, info in details.items():
        facts = forward_chain_for_country(name, info, context, LIVE_RULES)
        if facts.get("selected"):
            result.append(
                {
                    "name": name,
                    "summary": describe_country(name, info),
                }
            )

    return render_template(
        "expert.html",
        section="live",
        result=result,
        density=density,
        climate=climate_raw,
        government=government_raw,
        religion=religion_raw,
        mode=None,
        trade=None,
        domain=None,
        budget=None,
        place_type=None,
    )


@app.post("/expert/work")
def expert_work():
    details = load_country_details()
    mode = request.form.get("mode")  # business or job
    trade_raw = request.form.get("trade")
    domain_raw = request.form.get("domain")

    context = {
        "mode": mode,
        "trade": normalize_trade(trade_raw) if trade_raw else None,
        "domain": normalize_field(domain_raw) if domain_raw else None,
    }
    result: List[Dict[str, str]] = []

    for name, info in details.items():
        facts = forward_chain_for_country(name, info, context, WORK_RULES)
        if facts.get("selected"):
            result.append(
                {
                    "name": name,
                    "summary": describe_country(name, info),
                }
            )

    return render_template(
        "expert.html",
        section="work",
        result=result,
        density=None,
        climate=None,
        government=None,
        religion=None,
        mode=mode,
        trade=trade_raw,
        domain=domain_raw,
        budget=None,
        place_type=None,
    )


@app.post("/expert/travel")
def expert_travel():
    tourism = load_tourism_data()
    budget_raw = request.form.get("budget") or ""
    place_type = request.form.get("place_type")

    # Chuyển số tiền VND người dùng nhập thành 3 khoảng ngân sách
    amount = None
    try:
        amount = float(budget_raw.replace(",", "").strip())
    except ValueError:
        amount = None

    bucket = None  # 'under' | 'mid' | 'over'
    if amount is not None:
        if amount < 30_000_000:
            bucket = "under"
        elif amount <= 60_000_000:
            bucket = "mid"
        else:
            bucket = "over"

    budget_label_map = {
        "under": "Dưới 30.000.000",
        "mid": "30–60 triệu",
        "over": "Trên 60.000.000",
    }
    target_label_norm = _norm(budget_label_map.get(bucket))

    result: List[Dict[str, str]] = []
    if target_label_norm:
        for place, info in tourism.items():
            info_place = normalize_place_type(get_field(info, "type of place", "loại địa điểm"))
            if info_place != normalize_place_type(place_type):
                continue

            raw_budget = get_field(info, "budget", "ngân sách")
            if _norm(raw_budget) != target_label_norm:
                continue

            # Truyền giá trị số tượng trưng vào describe_place chỉ để chọn label hiển thị
            numeric_hint = {"under": 0.5, "mid": 1.5, "over": 2.5}.get(bucket, 0.0)

            result.append(
                {
                    "name": place,
                    "summary": describe_place(place, info, numeric_hint, place_type),
                }
            )

    return render_template(
        "expert.html",
        section="travel",
        result=result,
        density=None,
        climate=None,
        government=None,
        religion=None,
        mode=None,
        trade=None,
        domain=None,
        budget=budget_raw,
        place_type=place_type,
    )


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
    countries_list = load_country_list()
    key = request.args.get("key")
    existing = None
    if key and header:
        for r in rows:
            if r and r[0].lower() == key.lower():
                existing = dict(zip(header, r))
                break
    return render_template(
        "admin_countries.html",
        header=header,
        rows=rows,
        existing=existing,
        countries=countries_list,
    )


@app.post("/admin/countries/delete")
@login_required
@role_required("manager")
def admin_countries_delete():
    header, rows = read_csv_file("countries.csv")
    if not header:
        flash("countries.csv trống hoặc thiếu header.")
        return redirect(url_for("admin_countries"))

    key = (request.form.get("key") or "").strip()
    if not key:
        flash("Không xác định được dòng cần xóa.")
        return redirect(url_for("admin_countries"))

    new_rows = [r for r in rows if not (r and r[0].strip().lower() == key.lower())]
    if len(new_rows) == len(rows):
        flash(f"Không tìm thấy dòng có {header[0]} = '{key}'.")
    else:
        write_csv_file("countries.csv", header, new_rows)
        flash(f"Đã xóa dòng có {header[0]} = '{key}'.")
    return redirect(url_for("admin_countries"))


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
    countries_list = load_country_list()
    key = request.args.get("key")
    existing = None
    if key and header:
        for r in rows:
            if r and r[0].lower() == key.lower():
                existing = dict(zip(header, r))
                break
    return render_template(
        "admin_tourism.html",
        header=header,
        rows=rows,
        existing=existing,
        countries=countries_list,
    )


@app.post("/admin/tourism/delete")
@login_required
@role_required("manager")
def admin_tourism_delete():
    header, rows = read_csv_file("Tourism.csv")
    if not header:
        flash("Tourism.csv trống hoặc thiếu header.")
        return redirect(url_for("admin_tourism"))

    key = (request.form.get("key") or "").strip()
    if not key:
        flash("Không xác định được dòng cần xóa.")
        return redirect(url_for("admin_tourism"))

    new_rows = [r for r in rows if not (r and r[0].strip().lower() == key.lower())]
    if len(new_rows) == len(rows):
        flash(f"Không tìm thấy dòng có {header[0]} = '{key}'.")
    else:
        write_csv_file("Tourism.csv", header, new_rows)
        flash(f"Đã xóa dòng có {header[0]} = '{key}'.")
    return redirect(url_for("admin_tourism"))


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


