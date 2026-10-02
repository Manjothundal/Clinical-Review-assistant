# -*- coding: utf-8 -*-
"""
Takes a screenshot of every page of the app.
    python shots.py
Needs the app running:
    streamlit run app.py --server.port 8511 --server.headless true
"""
import os
from playwright.sync_api import sync_playwright

URL = "http://localhost:8511"
OUT = "shots"


def settle(page, seconds=3.0):
    page.wait_for_timeout(int(seconds * 1000))
    for _ in range(24):
        if page.query_selector("[data-testid='stStatusWidget']") is None:
            break
        page.wait_for_timeout(500)


def go(page, name):
    page.get_by_text(name, exact=True).first.click()
    settle(page)


def shot(page, name, full=False):
    path = os.path.join(OUT, name + ".png")
    page.screenshot(path=path, full_page=full)
    print("wrote", path)


def main():
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 1000},
                                device_scale_factor=2)
        page.goto(URL, wait_until="networkidle")
        settle(page, 8)

        # 1 - Overview
        shot(page, "1_overview")

        # 2 - Outputs, on a table that has a planted problem in it
        go(page, "Outputs")
        try:
            page.get_by_text("Output", exact=True).nth(1).click()
            page.wait_for_timeout(600)
            page.get_by_text("PK_Primary_Endpoints_EPIN_adj_6050_T2_vs_R.rtf",
                             exact=True).first.click()
            settle(page)
        except Exception as exc:
            print("could not switch output:", exc)
        shot(page, "2_outputs")

        # 3 - Review, with the first Evidence panel opened
        go(page, "Review")
        shot(page, "3_review")
        try:
            page.get_by_text("Evidence", exact=True).first.click()
            page.wait_for_timeout(1200)
            page.mouse.wheel(0, 420)
            page.wait_for_timeout(800)
        except Exception as exc:
            print("could not open evidence:", exc)
        shot(page, "3b_review_evidence")

        # 4 - To look at
        go(page, "To look at")
        shot(page, "4_to_look_at")

        # 5 - What the AI sees
        go(page, "What the AI sees")
        shot(page, "5_what_the_ai_sees")

        browser.close()


if __name__ == "__main__":
    main()
