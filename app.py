import re
import time
import json
import urllib.parse
from datetime import datetime

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup


st.set_page_config(page_title="Alcohood Competitor Price Radar", layout="wide")

st.title("🍾 Alcohood Competitor Price Radar")
st.caption("Direct Competitor Search • Price Extraction • Alcohood Comparison • Suggested Price")


COMPETITOR_SEARCH_URLS = {
    "Watson's Wine": "https://www.watsonswine.com/en/search?text={query}&useDefaultSearch=false&brandRedirect=true",
    "Wine Couple": "https://www.winecouple.hk/products?query={query}",
    "Cellarmaster": "https://cellarmasterwines.com/search?q={query}&options%5Bprefix%5D=last",
    "MyiCellar": "https://shop.myicellar.com/search?q={query}",
    "Ponti Wine Cellars": "https://www.pontiwinecellars.com.hk/products?query={query}",
    "RNG Wine": "https://www.rngwine.com/products?query={query}",
    "Onexcel Wine": "https://www.onexcel-wine.com/ProductAdvanceSearch?ProductName={query}",
    "偉成洋酒": "https://www.waishingwine.com.hk/products?query={query}",
}


CATEGORIES = {
    "Whisky": ["macallan 12", "yamazaki 12", "hibiki harmony", "nikka from the barrel", "glenfiddich 12", "ardbeg 10"],
    "Sake": ["dassai 45", "kubota manju", "hakkaisan", "juyondai", "born sake"],
    "Gin": ["roku gin", "hendricks gin", "monkey 47", "bombay sapphire", "two moons gin"],
    "Champagne": ["moet chandon brut", "veuve clicquot", "dom perignon", "perrier jouet", "bollinger", "krug"],
    "Cognac": ["hennessy vsop", "hennessy xo", "martell cordon bleu", "martell xo", "remy martin xo"],
    "Red wine": ["opus one", "penfolds bin 389", "pinot noir", "cabernet sauvignon"],
    "White wine": ["cloudy bay sauvignon blanc", "chardonnay", "sauvignon blanc", "riesling"],
    "Sparkling Wine": ["prosecco", "cava", "freixenet", "cremant"],
    "Tequila & Agave Spirits": ["don julio 1942", "casamigos reposado", "patron silver", "mezcal"],
    "Liqueur": ["baileys", "kahlua", "disaronno", "cointreau"],
    "Fruit Wine": ["choya umeshu", "plum wine", "yuzu wine", "peach wine"],
    "Baijiu": ["moutai", "wuliangye", "yanghe", "guojiao 1573"],
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
        response = requests.get(url, headers=HEADERS, timeout=20)
        if response.status_code == 200:
            return response.text
        return ""
    except Exception:
        return ""


def build_search_url(template, query):
    encoded_query = urllib.parse.quote(query)
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


def extract_json_ld_price(soup):
    scripts = soup.find_all("script", type="application/ld+json")

    for script in scripts:
        try:
            data = json.loads(script.string or "{}")

            items = data if isinstance(data, list) else [data]

            for item in items:
                if not isinstance(item, dict):
                    continue

                offers = item.get("offers")

                if isinstance(offers, dict):
                    price = offers.get("price")
                    if price:
                        return float(str(price).replace(",", ""))

                if isinstance(offers, list):
                    for offer in offers:
                        price = offer.get("price")
                        if price:
                            return float(str(price).replace(",", ""))

        except Exception:
            continue

    return None


def extract_links_from_search_page(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    links = []

    for a in soup.find_all("a", href=True):
        href = a["href"]

        if href.startswith("/"):
            parsed_base = urllib.parse.urlparse(base_url)
            href = f"{parsed_base.scheme}://{parsed_base.netloc}{href}"

        if href.startswith("http"):
            lowered = href.lower()

            if any(skip in lowered for skip in ["cart", "checkout", "account", "login", "register", "wishlist"]):
                continue

            links.append(href)

    return list(dict.fromkeys(links))[:8]


def extract_page_info(url):
    html = fetch(url)

    if not html:
        return None, "", url

    soup = BeautifulSoup(html, "html.parser")

    title = soup.title.string.strip() if soup.title and soup.title.string else url

    json_price = extract_json_ld_price(soup)
    text_price = money_to_float(soup.get_text(" ", strip=True))

    price = json_price if json_price else text_price

    return price, title, url


def search_competitor_product(product_query, competitor_name):
    search_template = COMPETITOR_SEARCH_URLS[competitor_name]
    search_url = build_search_url(search_template, product_query)

    html = fetch(search_url)

    if not html:
        return {
            "competitor_name": competitor_name,
            "competitor_title": "Search page blocked / no response",
            "competitor_price": None,
            "competitor_url": search_url,
        }

    search_price = money_to_float(BeautifulSoup(html, "html.parser").get_text(" ", strip=True))

    links = extract_links_from_search_page(html, search_url)

    best_result = None

    for link in links:
        price, title, product_url = extract_page_info(link)

        if price:
            best_result = {
                "competitor_name": competitor_name,
                "competitor_title": title,
                "competitor_price": price,
                "competitor_url": product_url,
            }
            break

    if best_result:
        return best_result

    if search_price:
        return {
            "competitor_name": competitor_name,
            "competitor_title": "Price found on search results page",
            "competitor_price": search_price,
            "competitor_url": search_url,
        }

    return {
        "competitor_name": competitor_name,
        "competitor_title": "Not found",
        "competitor_price": None,
        "competitor_url": search_url,
    }


def alcohood_search(product_query):
    search_url = f"https://www.alcohood.com/search?q={urllib.parse.quote(product_query)}"

    html = fetch(search_url)

    if not html:
        return {
            "alcohood_title": "Search page blocked / no response",
            "alcohood_price": None,
            "alcohood_url": search_url,
        }

    search_price = money_to_float(BeautifulSoup(html, "html.parser").get_text(" ", strip=True))

    links = extract_links_from_search_page(html, search_url)

    for link in links:
        if "alcohood.com" not in link:
            continue

        price, title, product_url = extract_page_info(link)

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


def build_report(selected_categories, selected_competitors, limit):
    main_rows = []
    detail_rows = []

    for category in selected_categories:
        product_queries = CATEGORIES[category][:limit]

        for product_query in product_queries:
            own = alcohood_search(product_query)
            own_price = own.get("alcohood_price")

            competitor_results = []

            for competitor_name in selected_competitors:
                result = search_competitor_product(product_query, competitor_name)
                competitor_results.append(result)

                detail_rows.append(
                    {
                        "Date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "Category": category,
                        "Product Search": product_query,
                        "Competitor": result.get("competitor_name"),
                        "Competitor Product": result.get("competitor_title"),
                        "Competitor Price": result.get("competitor_price"),
                        "Competitor URL": result.get("competitor_url"),
                    }
                )

                time.sleep(0.5)

            valid_competitors = [
                item for item in competitor_results if item.get("competitor_price")
            ]

            cheapest = sorted(
                valid_competitors,
                key=lambda x: x["competitor_price"],
            )[0] if valid_competitors else {}

            competitor_price = cheapest.get("competitor_price")
            competitor_name = cheapest.get("competitor_name", "")
            competitor_title = cheapest.get("competitor_title", "")
            competitor_url = cheapest.get("competitor_url", "")

            if own_price and competitor_price:
                difference = own_price - competitor_price

                if difference > 0:
                    suggested_price = competitor_price - 1
                    status = "🟠 Lower Price"
                else:
                    suggested_price = own_price
                    status = "🟢 Competitive"

            elif competitor_price and not own_price:
                difference = ""
                suggested_price = ""
                status = "🟡 Consider Listing"

            else:
                difference = ""
                suggested_price = ""
                status = "🔴 No Reliable Match"

            main_rows.append(
                {
                    "Date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "Category": category,
                    "Product Search": product_query,
                    "Alcohood Product": own.get("alcohood_title"),
                    "Alcohood Price": own_price,
                    "Alcohood URL": own.get("alcohood_url"),
                    "Cheapest Competitor": competitor_name,
                    "Competitor Product": competitor_title,
                    "Competitor Price": competitor_price,
                    "Competitor URL": competitor_url,
                    "Difference": difference,
                    "Suggested Price": suggested_price,
                    "Status": status,
                }
            )

            time.sleep(0.5)

    return pd.DataFrame(main_rows), pd.DataFrame(detail_rows)


with st.sidebar:
    st.header("Settings")

    selected_categories = st.multiselect(
        "Categories",
        list(CATEGORIES.keys()),
        default=["Whisky", "Sake", "Gin", "Champagne", "Cognac"],
    )

    selected_competitors = st.multiselect(
        "Competitors",
        list(COMPETITOR_SEARCH_URLS.keys()),
        default=[
            "Watson's Wine",
            "Wine Couple",
            "Cellarmaster",
            "MyiCellar",
            "Ponti Wine Cellars",
        ],
    )

    limit = st.slider("Products per category", 1, 6, 3)

    run = st.button("Run direct competitor search", type="primary")


st.info(
    "This version uses each competitor's own search URL instead of Google Shopping. "
    "It opens search result pages, extracts product links and prices, then compares with Alcohood."
)


if run:
    with st.spinner("Searching competitor websites directly and extracting prices..."):
        df, detail_df = build_report(selected_categories, selected_competitors, limit)

    st.success("Done")

    k1, k2, k3 = st.columns(3)

    k1.metric("Products Checked", len(df))
    k2.metric("Price Opportunities", int((df["Status"] == "🟠 Lower Price").sum()))
    k3.metric("Potential New Listings", int(df["Status"].str.contains("Consider", na=False).sum()))

    st.subheader("Action Needed")
    st.dataframe(
        df[df["Status"].isin(["🟠 Lower Price", "🟡 Consider Listing", "🔴 No Reliable Match"])],
        use_container_width=True,
    )

    st.subheader("Full Dashboard")
    st.dataframe(df, use_container_width=True)

    st.download_button(
        "Download Main Dashboard CSV",
        df.to_csv(index=False).encode("utf-8-sig"),
        "alcohood_competitor_price_radar.csv",
        "text/csv",
    )

    st.subheader("Competitor Detail Report")
    st.dataframe(detail_df, use_container_width=True)

    st.download_button(
        "Download Competitor Detail CSV",
        detail_df.to_csv(index=False).encode("utf-8-sig"),
        "alcohood_competitor_detail_report.csv",
        "text/csv",
    )

else:
    st.subheader("How this searches")
    st.write(
        "1. Select categories and competitors. "
        "2. The app opens each competitor's own search URL. "
        "3. It scans search results and product pages for HKD prices. "
        "4. It compares the cheapest competitor price with Alcohood. "
        "5. If Alcohood is more expensive, suggested price = competitor price - HK$1."
    )
