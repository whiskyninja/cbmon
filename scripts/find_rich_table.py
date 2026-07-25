# -*- coding: utf-8 -*-
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://localhost:9222")
    context = browser.contexts[0] if browser.contexts else browser.new_context()
    page = context.new_page()
    page.goto("https://thefew.tw/cb", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(1500)

    # search whole page text for markers unique to the rich table
    body = page.inner_text("body")
    for marker in ["轉換比例", "進階篩選", "集保戶數", "轉換開始日", "起日", "迄日", "轉換價格生效日"]:
        print(marker, "->", marker in body)

    # look for buttons/tabs
    buttons = page.query_selector_all("button, [role=tab], a")
    texts = set()
    for b in buttons:
        t = b.inner_text().strip()
        if t and len(t) < 20:
            texts.add(t)
    print("--- short clickable texts ---")
    for t in sorted(texts):
        print(t)
    context.close()
