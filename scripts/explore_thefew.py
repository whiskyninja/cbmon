# -*- coding: utf-8 -*-
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://localhost:9222")
    context = browser.contexts[0] if browser.contexts else browser.new_context()
    page = context.new_page()
    page.goto("https://thefew.tw/cb", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(2000)
    print("URL:", page.url)
    print("TITLE:", page.title())
    links = page.eval_on_selector_all(
        "a",
        "els => els.map(e => e.href + '  |  ' + e.innerText.trim()).filter(x => x.length > 5)"
    )
    seen = set()
    for l in links:
        if l not in seen:
            seen.add(l)
            print(l)
    context.close()
