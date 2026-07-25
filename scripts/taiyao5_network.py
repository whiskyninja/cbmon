import json
import time
from playwright.sync_api import sync_playwright

url = "https://thefew.tw/quote/62745"
captured = []

def on_response(response):
    try:
        ct = response.headers.get("content-type", "")
        if "json" in ct and response.status == 200:
            body = response.json()
            captured.append({"url": response.url, "body": body})
    except Exception:
        pass

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://localhost:9222")
    context = browser.contexts[0] if browser.contexts else browser.new_context()
    page = context.new_page()
    page.on("response", on_response)
    page.goto(url, wait_until="networkidle", timeout=30000)
    time.sleep(1)
    # click through range buttons to trigger any lazy-loaded series
    for label in ["1M", "3M", "6M", "1Y"]:
        try:
            page.get_by_text(label, exact=True).first.click(timeout=3000)
            time.sleep(1.5)
        except Exception as e:
            print("click fail", label, e)
    context.close()

with open("taiyao5_network_dump.json", "w", encoding="utf-8") as f:
    json.dump(captured, f, ensure_ascii=False, indent=2)

print("captured responses:", len(captured))
for c in captured:
    print(c["url"])
