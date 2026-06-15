from playwright.sync_api import sync_playwright


def browser_test():
    """
    Simple test to confirm Playwright + Chromium works on Render.
    Expected result: page title such as 'Google'.
    """

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        page = browser.new_page()

        page.goto(
            "https://www.google.com",
            timeout=60000,
            wait_until="domcontentloaded",
        )

        title = page.title()

        browser.close()

        return title


def get_page_html(url):
    """
    Open any URL with a real browser and return rendered HTML.
    """

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        page = browser.new_page()

        page.goto(
            url,
            timeout=60000,
            wait_until="networkidle",
        )

        html = page.content()

        browser.close()

        return html


def search_watsons(product_name):
    url = (
        "https://www.watsonswine.com/en/search?text="
        + product_name.replace(" ", "%20")
        + "&useDefaultSearch=false&brandRedirect=true"
    )

    return get_page_html(url)


def search_winecouple(product_name):
    url = (
        "https://www.winecouple.hk/products?query="
        + product_name.replace(" ", "%20")
    )

    return get_page_html(url)


def search_cellarmaster(product_name):
    url = (
        "https://cellarmasterwines.com/search?q="
        + product_name.replace(" ", "+")
        + "&options%5Bprefix%5D=last"
    )

    return get_page_html(url)


def search_myicellar(product_name):
    url = (
        "https://shop.myicellar.com/search?q="
        + product_name.replace(" ", "+")
    )

    return get_page_html(url)


def search_ponti(product_name):
    url = (
        "https://www.pontiwinecellars.com.hk/products?query="
        + product_name.replace(" ", "%20")
    )

    return get_page_html(url)


def search_rng(product_name):
    url = (
        "https://www.rngwine.com/products?query="
        + product_name.replace(" ", "%20")
    )

    return get_page_html(url)


def search_onexcel(product_name):
    url = (
        "https://www.onexcel-wine.com/ProductAdvanceSearch?ProductName="
        + product_name.replace(" ", "%20")
    )

    return get_page_html(url)


def search_waishing(product_name):
    url = (
        "https://www.waishingwine.com.hk/products?query="
        + product_name.replace(" ", "%20")
    )

    return get_page_html(url)


def search_alcohood(product_name):
    url = (
        "https://www.alcohood.com/search?q="
        + product_name.replace(" ", "+")
    )

    return get_page_html(url)
