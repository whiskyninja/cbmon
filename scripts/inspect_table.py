# -*- coding: utf-8 -*-
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://localhost:9222")
    context = browser.contexts[0] if browser.contexts else browser.new_context()
    page = context.new_page()
    page.goto("https://thefew.tw/cb", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(2000)

    tables = page.query_selector_all("table")
    print("table count:", len(tables))
    if tables:
        t = tables[0]
        rows = t.query_selector_all("tr")
        print("row count:", len(rows))
        if len(rows) > 1:
            print("--- header row outerHTML ---")
            print(rows[0].evaluate("el => el.outerHTML"))
            print("--- second row outerHTML (data row) ---")
            print(rows[1].evaluate("el => el.outerHTML"))
    context.close()
