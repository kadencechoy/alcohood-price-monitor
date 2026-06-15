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
st.caption("Competitor Website Search • Price Extraction • Alcohood Comparison • Suggested Price")


COMPETITORS = {
    "Watson's Wine": "watsonswine.com",
    "Wine Couple": "winecouple.hk",
    "Cellarmaster": "cellarmasterwines.com",
    "MyiCellar": "myicellar.com",
    "Ponti Wine Cellars": "pontiwinecellars.com.hk",
    "RNG Wine": "rngwine.com",
    "Onexcel Wine": "onexcel-wine.com",
    "偉成洋酒": "waishingwine.com",
}


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
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code == 200:
            return response.text
        return ""
    except Exception:
        return ""


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


def extract_price_from_json_ld(soup):
    scripts = soup.find_all("script", type="application/ld+json")

    for script in scripts:
        try:
            data = json.loads(script.string or "{}")

            if isinstance(data, dict):
                offers = data.get("offers")

                if isinstance(offers, dict):
                    price = offers.get("price")
                    if price:
                        return float(str(price).replace(",", ""))

                if isinstance(offers, list):
                    for offer in offers:
                        price = offer.get("price")
                        if price:
                            return float(str(price).replace(",", ""))

            if isinstance(data, list):
                for item in data:
                    offers = item.get("offers") if isinstance(item, dict) else None
                    if isinstance(offers, dict) and offers.get("price"):
                        return float(str(offers.get("price")).replace(",", ""))

        except Exception:
            continue

    return None


def extract_page_info(url):
    html = fetch(url)

    if not html:
        return None, "", ""

    soup = BeautifulSoup(html, "html.parser")

    title = soup.title.string.strip() if soup.title and soup.title.string else url

    json_price = extract_price_from_json_ld(soup)
    text_price = money_to_float(soup.get_text(" ", strip=True))

    price = json_price if json_price else text_price

    return price, title, url


def clean_search_result_url(href):
    if not href:
        return ""

    if href.startswith("/url?q="):
        parsed = urllib.parse.urlparse(href)
        query = urllib.parse.parse_qs(parsed.query)
        return query.get("q", [""])[0]

    if href.startswith("//duckduckgo.com/l/?uddg="):
        parsed = urllib.parse.urlparse("https:" + href)
        query = urllib.parse.parse_qs(parsed.query)
        return urllib.parse.unquote(query.get("uddg", [""])[0])

    if "duckduckgo.com/l/?uddg=" in href:
        parsed = urllib.parse.urlparse(href)
        query = urllib.parse.parse_qs(parsed.query)
        return urllib.parse.unquote(query.get("uddg", [""])[0])

    return href


def search_duckduckgo_site(product_query, domain, max_links=5):
    search_query = f"site:{domain} {product_query}"
    search_url = (
        "https://duckduckgo.com/html/?q="
        + urllib.parse.quote(search_query)
    )

    html = fetch(search_url)
    soup = BeautifulSoup(html, "html.parser")

    links = []

    for a in soup.find_all("a", href=True):
        href = clean_search_result_url(a["href"])

        if domain in href and href.startswith("http"):
            if not any(skip in href.lower() for skip in ["cart", "login", "account", "checkout"]):
                links.append(href)

    return list(dict.fromkeys(links))[:max_links], search_url


def search_google_site(product_query, domain, max_links=5):
    search_query = f"site:{domain} {product_query}"
    search_url = (
        "https://www.google.com/search?hl=en-HK&gl=HK&q="
        + urllib.parse.quote(search_query)
    )

    html = fetch(search_url)
    soup = BeautifulSoup(html, "html.parser")

    links = []

    for a in soup.find_all("a", href=True):
        href = clean_search_result_url(a["href"])

        if domain in href and href.startswith("http"):
            if not any(skip in href.lower() for skip in ["cart", "login", "account", "checkout"]):
                links.append(href)

    return list(dict.fromkeys(links))[:max_links], search_url


def search_site(product_query, domain, max_links=5):
    links, search_url = search_duckduckgo_site(product_query, domain, max_links)

    if links:
        return links, search_url, "DuckDuckGo"

    links, search_url = search_google_site(product_query, domain, max_links)

    if links:
        return links, search_url, "Google"

    return [], search_url, "No search result"


def competitor_search(product_query, selected_competitors):
    results = []

    for competitor_name in selected_competitors:
        domain = COMPETITORS[competitor_name]

        links, search_url, source = search_site(product_query, domain, max_links=5)

        best_result = None

        for link in links:
            price, title, product_url = extract_page_info(link)

            if price:
                best_result = {
                    "competitor_name": competitor_name,
                    "competitor_domain": domain,
                    "competitor_title": title,
                    "competitor_price": price,
                    "competitor_url": product_url,
                    "search_source": source,
                }
                break

        if best_result:
            results.append(best_result)
        else:
            results.append(
                {
                    "competitor_name": competitor_name,
                    "competitor_domain": domain,
                    "competitor_title": "Not found",
                    "competitor_price": None,
                    "competitor_url": search_url,
                    "search_source": source,
                }
            )

        time.sleep(0.4)

    return results


def alcohood_search(product_query):
    links, search_url, source = search_site(product_query, "alcohood.com", max_links=5)

    for link in links:
        price, title, product_url = extract_page_info(link)

        if price:
            return {
                "alcohood_title": title,
                "alcohood_price": price,
                "alcohood_url": product_url,
                "alcohood_source": source,
            }

    return {
        "alcohood_title": "Not found",
        "alcohood_price": None,
        "alcohood_url": search_url,
        "alcohood_source": source,
    }


def build_report(selected_categories, selected_competitors, limit):
    rows = []
    detail_rows = []

    for category in selected_categories:
        product_queries = CATEGORIES[category][:limit]

        for product_query in product_queries:
            own = alcohood_search(product_query)
            own_price = own.get("alcohood_price")

            competitor_results = competitor_search(product_query, selected_competitors)

            for competitor in competitor_results:
                detail_rows.append(
                    {
                        "Date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "Category": category,
                        "Product Search": product_query,
                        "Competitor": competitor.get("competitor_name"),
                        "Competitor Product": competitor.get("competitor_title"),
                        "Competitor Price": competitor.get("competitor_price"),
                        "Competitor URL": competitor.get("competitor_url"),
                        "Search Source": competitor.get("search_source"),
                    }
                )

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

            rows.append(
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

            time.sleep(0.8)

    return pd.DataFrame(rows), pd.DataFrame(detail_rows)


with st.sidebar:
    st.header("Settings")

    selected_categories = st.multiselect(
        "Categories",
        list(CATEGORIES.keys()),
        default=["Whisky", "Sake", "Gin", "Champagne", "Cognac"],
    )

    selected_competitors = st.multiselect(
        "Competitors",
        list(COMPETITORS.keys()),
        default=[
            "Watson's Wine",
            "Wine Couple",
            "Cellarmaster",
            "MyiCellar",
            "Ponti Wine Cellars",
        ],
    )

    limit = st.slider("Products per category", 1, 6, 3)

    run = st.button("Run competitor price radar", type="primary")


st.info(
    "Fine-tuned version: it first searches competitor product pages using DuckDuckGo site search, "
    "then falls back to Google site search. It also tries structured product price data before scanning page text."
)


if run:
    with st.spinner("Searching competitor shops and extracting prices..."):
        df, detail_df = build_report(selected_categories, selected_competitors, limit)

    st.success("Done")

    k1, k2, k3 = st.columns(3)

    k1.metric("Products Checked", len(df))
    k2.metric("Price Opportunities", int((df["Status"] == "🟠 Lower Price").sum()))
    k3.metric("Potential New Listings", int(df["Status"].str.contains("Consider", na=False).sum()))

    st.subheader("Action Needed")

    action_needed = df[
        df["Status"].isin(["🟠 Lower Price", "🟡 Consider Listing", "🔴 No Reliable Match"])
    ]

    st.dataframe(action_needed, use_container_width=True)

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
        "2. The app searches product pages using DuckDuckGo site search first. "
        "3. If no result is found, it tries Google site search. "
        "4. It opens possible product pages and extracts HKD prices. "
        "5. It compares the cheapest competitor price with Alcohood."
    )
