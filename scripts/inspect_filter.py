# -*- coding: utf-8 -*-
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://localhost:9222")
    context = browser.contexts[0] if browser.contexts else browser.new_context()
    page = context.new_page()
    page.goto("https://thefew.tw/cb", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(1500)

    # find element containing text 進階篩選
    els = page.query_selector_all("text=進階篩選")
    print("found 進階篩選 elements:", len(els))
    for e in els:
        print(repr(e.evaluate("el => el.tagName + '|' + el.className")))

    if els:
        els[0].click()
        page.wait_for_timeout(1500)
        print("after click, url:", page.url)
        # dump visible modal/panel text
        body_text = page.inner_text("body")
        with open("filter_panel_dump.txt", "w", encoding="utf-8") as f:
            f.write(body_text)
        print("dumped body text len:", len(body_text))

    context.close()
