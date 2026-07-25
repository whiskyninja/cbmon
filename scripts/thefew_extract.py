import sys
import time
from playwright.sync_api import sync_playwright

url = sys.argv[1] if len(sys.argv) > 1 else "https://thefew.tw/cb/low-premium"
out_path = sys.argv[2] if len(sys.argv) > 2 else "thefew_dump.json"

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://localhost:9222")
    context = browser.contexts[0] if browser.contexts else browser.new_context()
    page = context.new_page()
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    time.sleep(2)

    # scroll to bottom repeatedly to trigger any lazy loading, track body text length stability
    prev_len = -1
    stable_count = 0
    for _ in range(40):
        page.mouse.wheel(0, 3000)
        time.sleep(0.4)
        cur_len = len(page.inner_text("body"))
        if cur_len == prev_len:
            stable_count += 1
            if stable_count >= 3:
                break
        else:
            stable_count = 0
        prev_len = cur_len

    body_text = page.inner_text("body")

    with open(out_path.replace(".json", "_raw.txt"), "w", encoding="utf-8") as f:
        f.write(body_text)

    print("body_text_len", len(body_text), "stable_count", stable_count)
    context.close()
