import json
from typing import Dict

from web_app import (
    load_country_list,
    code_for_country,
    parse_html_from_zip,
    translate_en_vi,
)


def build_vi_cache() -> Dict[str, Dict[str, Dict[str, str]]]:
    """Dịch sẵn toàn bộ nội dung tra cứu sang tiếng Việt và lưu vào cache.

    Cấu trúc kết quả:
    {
      "aa": {                       # country code (2 ký tự, viết thường)
        "Background": {
          "key_vi": "<tiêu đề dịch>",
          "val_vi": "<nội dung dịch>"
        },
        ...
      },
      ...
    }
    """
    cache: Dict[str, Dict[str, Dict[str, str]]] = {}

    countries = load_country_list()
    total = len(countries)
    for idx, name in enumerate(countries, start=1):
        code = code_for_country(name)
        if not code:
            continue
        code = code.lower()
        percent = (idx / total) * 100 if total else 0
        print(f"[{idx}/{total}] ({percent:5.1f}%) Processing {name} ({code}) ...", flush=True)
        try:
            possibilities = parse_html_from_zip(code)
        except Exception as e:  # pragma: no cover - tiện debug khi chạy script
            print(f"  Skipped {name} ({code}) due to error: {e}")
            continue

        country_cache: Dict[str, Dict[str, str]] = {}
        for key_en, val_en in possibilities.items():
            key_vi = translate_en_vi(key_en)
            val_vi = translate_en_vi(val_en)
            country_cache[key_en] = {
                "key_vi": key_vi,
                "val_vi": val_vi,
            }

        cache[code] = country_cache

    return cache


def main() -> None:
    cache = build_vi_cache()
    with open("search_vi_cache.json", "w", encoding="utf-8") as fh:
        json.dump(cache, fh, ensure_ascii=False, indent=2)
    print("Saved Vietnamese cache to search_vi_cache.json")


if __name__ == "__main__":
    main()


