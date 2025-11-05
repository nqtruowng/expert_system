from __future__ import annotations

import csv
import zipfile
from difflib import get_close_matches
from typing import Dict, List

from flask import Flask, render_template, request, redirect, url_for, flash

try:
    from bs4 import BeautifulSoup
except ImportError:
    raise SystemExit("Missing dependency: beautifulsoup4. Install with: pip install beautifulsoup4")


app = Flask(__name__)
app.secret_key = "expert-system-demo"  # for flash messages only


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


# -------------
# Web endpoints
# -------------


@app.get("/")
def home():
    return render_template("index.html")


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
    density = request.form.get("density")
    climate = request.form.get("climate")
    government = request.form.get("government")
    religion = request.form.get("religion")

    possible: List[str] = []
    for name, info in details.items():
        if (
            info.get("average weather") == climate
            and info.get("type of government") == government
            and info.get("major religion") == religion
        ):
            possible.append(name)

    return render_template("expert.html", section="live", result=possible)


@app.post("/expert/work")
def expert_work():
    details = load_country_details()
    mode = request.form.get("mode")  # business or job
    domain = request.form.get("domain")
    result: List[str] = []

    if mode == "business":
        trade = request.form.get("trade")  # import/export
        for name, info in details.items():
            if info.get("trade type") == trade and info.get("field domain") == domain:
                result.append(name)
    else:
        for name, info in details.items():
            if info.get("field domain") == domain:
                result.append(name)

    return render_template("expert.html", section="work", result=result)


@app.post("/expert/travel")
def expert_travel():
    tourism = load_tourism_data()
    budget = request.form.get("budget")
    place_type = request.form.get("place_type")

    # map to the numeric in CSV used by original app
    budget_map = {"under1": 0.5, "between1and2": 1.5, "above2": 2.5}
    target = budget_map.get(budget)

    result: List[str] = []
    if target is not None:
        for place, info in tourism.items():
            if info.get("type of place") == place_type and float(info.get("budget", 0)) == target:
                result.append(f"{place}, {info.get('country', '')}")

    return render_template("expert.html", section="travel", result=result)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)


