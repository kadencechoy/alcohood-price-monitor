import re
import time
import urllib.parse
from datetime import datetime

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup


st.set_page_config(
    page_title="Alcohood Google Shopping Price Radar",
    layout="wide"
)

st.title("🍾 Alcohood Google Shopping Price Radar")
st.caption(
    "Google Shopping First Result • Full Product Name • Alcohood Price Check • Suggested Price"
)


GOOGLE_SHOPPING_TEMPLATE = "https://www.google.com/search?q={query}&hl=en-HK&gl=HK&udm=28"
ALCOHOOD_SEARCH_TEMPLATE = "https://www.alcohood.com/search?q={query}"


CATEGORIES = {
    "Whisky": [
        "macallan 12",
        "yamazaki 12",
        "hibiki harmony",
        "nikka from the barrel",
        "glenfiddich 12",
        "ardbeg 10",
    ],
    "Sake": [
        "dassai 45",
        "kubota manju",
        "hakkaisan",
        "juyondai",
        "born sake",
    ],
    "Gin": [
        "roku gin",
        "hendricks gin",
        "monkey 47",
        "bombay sapphire",
        "two moons gin",
    ],
    "Champagne": [
        "moet chandon brut",
        "veuve clicquot",
        "dom perignon",
        "perrier jouet",
        "bollinger",
        "krug",
    ],
    "Cognac": [
        "hennessy vsop",
        "hennessy xo",
        "martell cordon bleu",
        "martell xo",
        "remy martin xo",
    ],
    "Red wine": [
        "opus one",
        "penfolds bin 389",
        "pinot noir",
        "cabernet sauvignon",
    ],
    "White wine": [
        "cloudy bay sauvignon blanc",
        "chardonnay",
        "sauvignon blanc",
        "riesling",
    ],
    "Sparkling Wine": [
        "prosecco",
        "cava",
        "freixenet",
        "cremant",
    ],
    "Tequila & Agave Spirits": [
        "don julio 1942",
        "casamigos reposado",
        "patron silver",
        "mezcal",
    ],
    "Liqueur": [
        "baileys",
        "kahlua",
        "disaronno",
        "cointreau",
    ],
    "Fruit Wine": [
        "choya umeshu",
        "plum wine",
        "yuzu wine",
        "peach wine",
    ],
    "Baijiu": [
        "moutai",
        "wuliangye",
        "yanghe",
        "guojiao 1573",
    ],
}


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/125 Safari/537.36"
    ),
    "Accept-Language": "en-HK,en;q=0.9,zh-HK;q=0.8",
}


@st.cache_data(ttl=3600)
def fetch(url):
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=20,
        )

        if response.status_code == 200:
            return response.text

        return ""

    except Exception:
        return ""


def build_search_url(template, query):
    encoded_query = urllib.parse.quote_plus(query)
    return template.replace("{query}", encoded_query)


def money_to_float(text):
    if not text:
        return None

    patterns = [
        r"(?:HK\$|HKD|\$)\s*([0-9][0-9,]*(?:\.\d+)?)",
        r"([0-9][0-9,]*(?:\.\d+)?)\s*(?:HKD|港幣|港元)",
    ]

    prices = []

    for pattern in patterns:
        matches = re.findall(pattern, text, re.I)

        for match in matches:
            try:
                price = float(match.replace(",", ""))

                if 20 <= price <= 100000:
                    prices.append(price)

            except Exception:
                pass

    if not prices:
        return None

    return min(prices)


def extract_google_shopping_first_result(query):
    search_url = build_search_url(
        GOOGLE_SHOPPING_TEMPLATE,
        query,
    )

    html = fetch(search_url)

    if not html:
        return {
            "google_product_name": "Google Shopping blocked / no response",
            "google_price": None,
            "google_store": "",
            "google_result_snippet": "",
            "google_url": search_url,
        }

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    price_match = re.search(
        r"(HK\$|HKD|\$)\s*[0-9][0-9,]*(?:\.\d+)?",
        text,
        re.I,
    )

    if not price_match:
        return {
            "google_product_name": "No price found from Google Shopping",
            "google_price": None,
            "google_store": "",
            "google_result_snippet": text[:300],
            "google_url": search_url,
        }

    price = money_to_float(price_match.group(0))

    start = max(0, price_match.start() - 180)
    end = min(len(text), price_match.end() + 220)
    snippet = text[start:end]

    before_price = text[start:price_match.start()].strip()
    after_price = text[price_match.end():end].strip()

    product_name = before_price[-180:].strip()
    store_name = ""

    store_patterns = [
        r"From\s+([A-Za-z0-9 '&\-.]+)",
        r"([A-Za-z0-9 '&\-.]+)\s+Nearby",
        r"([A-Za-z0-9 '&\-.]+)\s+Also nearby",
    ]

    for pattern in store_patterns:
        match = re.search(pattern, snippet)
        if match:
            store_name = match.group(1).strip()
            break

    if not product_name:
        product_name = snippet[:180]

    return {
        "google_product_name": product_name,
        "google_price": price,
        "google_store": store_name,
        "google_result_snippet": snippet,
        "google_url": search_url,
    }


def extract_links_from_search_page(html, base_url, allowed_domain=None):
    soup = BeautifulSoup(html, "html.parser")
    links = []

    parsed_base = urllib.parse.urlparse(base_url)
    base_domain = parsed_base.netloc

    for link_tag in soup.find_all("a", href=True):
        href = link_tag["href"]

        if href.startswith("/"):
            href = f"{parsed_base.scheme}://{base_domain}{href}"

        if not href.startswith("http"):
            continue

        lowered = href.lower()

        if any(
            skip in lowered
            for skip in [
                "cart",
                "checkout",
                "account",
                "login",
                "register",
                "wishlist",
                "facebook",
                "instagram",
                "whatsapp",
                "mailto",
                "tel:",
            ]
        ):
            continue

        if allowed_domain and allowed_domain not in lowered:
            continue

        links.append(href)

    return list(dict.fromkeys(links))[:10]


def extract_page_price_and_title(url):
    html = fetch(url)

    if not html:
        return None, "", url

    soup = BeautifulSoup(html, "html.parser")

    title = (
        soup.title.string.strip()
        if soup.title and soup.title.string
        else url
    )

    price = money_to_float(
        soup.get_text(" ", strip=True)
    )

    return price, title, url


def alcohood_search(product_query):
    search_url = build_search_url(
        ALCOHOOD_SEARCH_TEMPLATE,
        product_query,
    )

    html = fetch(search_url)

    if not html:
        return {
            "alcohood_title": "Alcohood search page blocked / no response",
            "alcohood_price": None,
            "alcohood_url": search_url,
        }

    soup = BeautifulSoup(html, "html.parser")
    search_text = soup.get_text(" ", strip=True)
    search_price = money_to_float(search_text)

    links = extract_links_from_search_page(
        html,
        search_url,
        allowed_domain="alcohood.com",
    )

    for link in links:
        price, title, product_url = extract_page_price_and_title(link)

        if price:
            return {
                "alcohood_title": title,
                "alcohood_price": price,
                "alcohood_url": product_url,
            }

    if search_price:
        return {
            "alcohood_title": "Price found on Alcohood search results page",
            "alcohood_price": search_price,
            "alcohood_url": search_url,
        }

    return {
        "alcohood_title": "Not found",
        "alcohood_price": None,
        "alcohood_url": search_url,
    }


def build_report(selected_categories, limit):
    rows = []

    for category in selected_categories:
        product_queries = CATEGORIES[category][:limit]

        for product_query in product_queries:
            google_result = extract_google_shopping_first_result(product_query)
            alcohood_result = alcohood_search(product_query)

            google_price = google_result.get("google_price")
            own_price = alcohood_result.get("alcohood_price")

            if own_price and google_price:
                difference = own_price - google_price

                if difference > 0:
                    suggested_price = google_price - 1
                    status = "🟠 Lower Price"
                else:
                    suggested_price = own_price
                    status = "🟢 Competitive"

            elif google_price and not own_price:
                difference = ""
                suggested_price = ""
                status = "🟡 Consider Listing / Alcohood Not Found"

            else:
                difference = ""
                suggested_price = ""
                status = "🔴 No Reliable Match"

            rows.append(
                {
                    "Date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "Category": category,
                    "Search Term": product_query,
                    "Google Shopping Product Name": google_result.get("google_product_name"),
                    "Google Shopping Price": google_price,
                    "Google Store / Source": google_result.get("google_store"),
                    "Google Shopping Link": google_result.get("google_url"),
                    "Google Result Snippet": google_result.get("google_result_snippet"),
                    "Alcohood Product": alcohood_result.get("alcohood_title"),
                    "Alcohood Price": own_price,
                    "Alcohood URL": alcohood_result.get("alcohood_url"),
                    "Difference": difference,
                    "Suggested Price": suggested_price,
                    "Status": status,
                }
            )

            time.sleep(0.8)

    return pd.DataFrame(rows)


with st.sidebar:
    st.header("Settings")

    selected_categories = st.multiselect(
        "Categories",
        list(CATEGORIES.keys()),
        default=[
            "Whisky",
            "Sake",
            "Gin",
            "Champagne",
            "Cognac",
        ],
    )

    limit = st.slider(
        "Products per category",
        1,
        6,
        3,
    )

    run = st.button(
        "Run Google Shopping Radar",
        type="primary",
    )


st.info(
    "This version uses Google Shopping search results and takes the first visible priced result as reference. "
    "It records the full visible product name, price, and Google Shopping link to reduce SKU misunderstanding."
)


if run:
    with st.spinner("Searching Google Shopping and Alcohood..."):
        df = build_report(
            selected_categories,
            limit,
        )

    st.success("Done")

    k1, k2, k3 = st.columns(3)

    k1.metric(
        "Products Checked",
        len(df),
    )

    k2.metric(
        "Price Opportunities",
        int((df["Status"] == "🟠 Lower Price").sum()),
    )

    k3.metric(
        "Potential New Listings",
        int(df["Status"].str.contains("Consider", na=False).sum()),
    )

    st.subheader("Action Needed")

    st.dataframe(
        df[
            df["Status"].isin(
                [
                    "🟠 Lower Price",
                    "🟡 Consider Listing / Alcohood Not Found",
                    "🔴 No Reliable Match",
                ]
            )
        ],
        use_container_width=True,
    )

    st.subheader("Full Dashboard")

    st.dataframe(
        df,
        use_container_width=True,
    )

    st.download_button(
        "Download CSV",
        df.to_csv(index=False).encode("utf-8-sig"),
        "alcohood_google_shopping_price_radar.csv",
        "text/csv",
    )

else:
    st.subheader("How this searches")
    st.write(
        "1. Select categories. "
        "2. The app searches Google Shopping using udm=28. "
        "3. It takes the first visible priced result. "
        "4. It records the full visible product name and Google Shopping link. "
        "5. It compares the Google price with Alcohood. "
        "6. If Alcohood is more expensive, suggested price = Google Shopping price - HK$1."
    )
