from playwright.sync_api import sync_playwright


def search_watsons(product_name):

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True
        )

        page = browser.new_page()

        search_url = (
            "https://www.watsonswine.com/en/search?text="
            + product_name.replace(" ", "%20")
        )

        page.goto(
            search_url,
            wait_until="networkidle"
        )

        html = page.content()

        browser.close()

        return html
