import json
import time
from playwright.sync_api import sync_playwright

codes = ["80963", "61876", "41904", "32943", "34913", "54642", "68032", "41239", "36806", "47148"]

results = {}

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://localhost:9222")
    context = browser.contexts[0] if browser.contexts else browser.new_context()
    page = context.new_page()

    for code in codes:
        captured = []

        def on_response(response, captured=captured):
            try:
                ct = response.headers.get("content-type", "")
                if "json" in ct and response.status == 200 and "/api/prices/" in response.url:
                    body = response.json()
                    captured.append(body)
            except Exception:
                pass

        page.on("response", on_response)
        try:
            page.goto(f"https://thefew.tw/quote/{code}", wait_until="networkidle", timeout=20000)
            time.sleep(1.5)
        except Exception as e:
            print(code, "goto fail", e)
        page.remove_listener("response", on_response)
        results[code] = captured

with open("auction_batch_dump.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

for code, caps in results.items():
    total = sum(len(c.get("data", [])) for c in caps if isinstance(c, dict))
    print(code, "responses:", len(caps), "total points:", total)
