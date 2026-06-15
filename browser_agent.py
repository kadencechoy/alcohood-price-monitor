from playwright.sync_api import sync_playwright

def browser_test():

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True
        )

        page = browser.new_page()

        page.goto(
            "https://www.google.com",
            timeout=60000
        )

        title = page.title()

        browser.close()

        return title
