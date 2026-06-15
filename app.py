import re
import time
import urllib.parse
from datetime import datetime

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup


st.set_page_config(
    page_title="Alcohood Competitor Price Radar",
    layout="wide"
)

st.title("🍾 Alcohood Competitor Price Radar")
st.caption(
    "Competitor Shop Search • Alcohood Price Check • Suggested Price • Action Needed"
)


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
    "Red wine": [
        "opus one",
        "penfolds bin 389",
        "pinot noir",
        "cabernet sauvignon",
        "bourgogne rouge",
    ],
    "White wine": [
        "cloudy bay sauvignon blanc",
        "chardonnay",
        "sauvignon blanc",
        "riesling",
        "chablis",
    ],
    "Sparkling Wine": [
        "prosecco",
        "cava",
        "freixenet",
        "cremant",
        "laurent perrier",
    ],
    "Champagne": [
        "moet chandon brut",
        "veuve clicquot",
        "dom perignon",
        "perrier jouet",
        "bollinger",
        "krug",
    ],
    "Sake": [
        "dassai 45",
        "kubota manju",
        "kamoshibito kuheiji",
        "hakkaisan",
        "juyondai",
        "born sake",
    ],
    "Whisky": [
        "macallan 12",
        "yamazaki 12",
        "hibiki harmony",
        "nikka from the barrel",
        "glenfiddich 12",
        "ardbeg 10",
    ],
    "Cognac": [
        "hennessy vsop",
        "martell cordon bleu",
        "remy martin vsop",
        "hennessy xo",
        "martell xo",
        "remy martin xo",
    ],
    "Brandy": [
        "torres 10",
        "st remy xo",
        "fundador brandy",
        "cardenal mendoza",
        "torres 20",
    ],
    "Gin": [
        "roku gin",
        "hendricks gin",
        "two moons gin",
        "nip gin",
        "bombay sapphire",
        "monkey 47",
    ],
    "Tequila & Agave Spirits": [
        "don julio 1942",
        "casamigos reposado",
        "patron silver",
        "818 tequila",
        "mezcal",
        "codigo tequila",
    ],
    "Liqueur": [
        "baileys",
        "kahlua",
        "disaronno",
        "cointreau",
        "malibu",
        "sheridans",
    ],
    "Fruit Wine": [
        "plum wine",
        "umeshu",
        "choya umeshu",
        "yuzu wine",
        "peach wine",
        "lychee wine",
    ],
    "Baijiu": [
        "moutai",
        "wuliangye",
        "yanghe",
        "guojiao 1573",
        "fenjiu",
        "xijiu",
    ],
}


TRENDING_PRODUCTS = {
    "Whisky": [
        "Yamazaki 12",
        "Hibiki Harmony",
        "Macallan 12",
        "Macallan 18",
        "Nikka From The Barrel",
    ],
    "Sake": [
        "Dassai 45",
        "Kubota Manju",
        "Juyondai",
        "Born Gold",
        "Hakkaisan",
    ],
    "Gin": [
        "Roku Gin",
        "Hendricks Gin",
        "Monkey 47",
        "Bombay Sapphire",
        "Two Moons Gin",
    ],
    "Champagne": [
        "Moet Brut",
        "Dom Perignon",
        "Veuve Clicquot",
        "Krug",
        "Bollinger",
    ],
    "Cognac": [
        "Hennessy VSOP",
        "Hennessy XO",
        "Martell XO",
        "Remy Martin XO",
        "Martell Cordon Bleu",
    ],
}


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 Chrome/125 Safari/537.36"
    ),
    "Accept-Language": "en-HK,en;q=0.9",
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
        r"([0-9][0-9,]*(?:\.\d+)?)\s*(?:HKD|港幣|元)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.I)

        if match:
            try:
                return float(match.group(1).replace(",", ""))
            except Exception:
                return None

    return None


def clean_google_url(href):
    if not href:
        return ""

    if href.startswith("/url?q="):
        parsed = urllib.parse.urlparse(href)
        query = urllib.parse.parse_qs(parsed.query)
        return query.get("q", [""])[0]

    return href


def google_site_search(query, domain, max_links=3):
    search_query = f"site:{domain} {query} hong kong"
    url = (
        "https://www.google.com/search?hl=en-HK&gl=HK&q="
        + urllib.parse.quote(search_query)
    )

    html = fetch(url)
    soup = BeautifulSoup(html, "html.parser")

    links = []

    for link_tag in soup.find_all("a", href=True):
        href = clean_google_url(link_tag["href"])

        if domain in href and href.startswith("http"):
            links.append(href)

    unique_links = list(dict.fromkeys(links))

    return unique_links[:max_links], url


def extract_price_from_page(url):
    html = fetch(url)

    if not html:
        return None, ""

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    price = money_to_float(text)

    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    else:
        title = url

    return price, title


def competitor_search(product_query, selected_competitors):
    results = []

    for competitor_name in selected_competitors:
        domain = COMPETITORS[competitor_name]

        links, search_url = google_site_search(
            product_query,
            domain,
            max_links=3,
        )

        best_result = None

        for link in links:
            price, title = extract_price_from_page(link)

            if price:
                best_result = {
                    "competitor_name": competitor_name,
                    "competitor_domain": domain,
                    "competitor_title": title,
                    "competitor_price": price,
                    "competitor_url": link,
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
                }
            )

        time.sleep(0.5)

    return results


def alcohood_search(product_query):
    links, search_url = google_site_search(
        product_query,
        "alcohood.com",
        max_links=3,
    )

    for link in links:
        price, title = extract_price_from_page(link)

        if price:
            return {
                "alcohood_title": title,
                "alcohood_price": price,
                "alcohood_url": link,
            }

    return {
        "alcohood_title": "Not found",
        "alcohood_price": None,
        "alcohood_url": search_url,
    }


def build_report(selected_categories, selected_competitors, limit):
    rows = []

    for category in selected_categories:
        product_queries = CATEGORIES[category][:limit]

        for product_query in product_queries:
            own = alcohood_search(product_query)
            own_price = own.get("alcohood_price")

            competitor_results = competitor_search(
                product_query,
                selected_competitors,
            )

            valid_competitors = [
                item
                for item in competitor_results
                if item.get("competitor_price")
            ]

            if valid_competitors:
                cheapest = sorted(
                    valid_competitors,
                    key=lambda x: x["competitor_price"],
                )[0]
            else:
                cheapest = {}

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

            time.sleep(1)

    return pd.DataFrame(rows)


def build_competitor_detail_report(selected_categories, selected_competitors, limit):
    rows = []

    for category in selected_categories:
        product_queries = CATEGORIES[category][:limit]

        for product_query in product_queries:
            competitor_results = competitor_search(
                product_query,
                selected_competitors,
            )

            for result in competitor_results:
                rows.append(
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

            time.sleep(1)

    return pd.DataFrame(rows)


def build_trending_products():
    trend_rows = []

    for category, products in TRENDING_PRODUCTS.items():
        for rank, product in enumerate(products, start=1):
            trend_rows.append(
                {
                    "Category": category,
                    "Rank": rank,
                    "Product": product,
                    "Trend Score": max(100 - ((rank - 1) * 10), 50),
                    "Search Term": f"{product} hong kong",
                }
            )

    return pd.DataFrame(trend_rows)


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

    limit = st.slider(
        "Products per category",
        1,
        6,
        3,
    )

    discover = st.button(
        "🔥 Discover Trending Products"
    )

    run = st.button(
        "Run competitor price radar",
        type="primary",
    )


st.info(
    "This version searches selected competitor websites using Google site search, "
    "then compares public product prices with Alcohood public pages. "
    "If Google blocks the search or product pages hide prices, the result will show No Reliable Match."
)


if discover:
    st.subheader("🔥 Trending Products Radar")

    trend_df = build_trending_products()

    st.dataframe(
        trend_df,
        use_container_width=True,
    )

    st.download_button(
        "Download Trending Products CSV",
        trend_df.to_csv(index=False).encode("utf-8-sig"),
        "alcohood_trending_products.csv",
        "text/csv",
    )


if run:
    with st.spinner("Searching competitor shops and building dashboard..."):
        df = build_report(
            selected_categories,
            selected_competitors,
            limit,
        )

        detail_df = build_competitor_detail_report(
            selected_categories,
            selected_competitors,
            limit,
        )

    st.success("Done")

    k1, k2, k3 = st.columns(3)

    k1.metric("Products Checked", len(df))
    k2.metric(
        "Price Opportunities",
        int((df["Status"] == "🟠 Lower Price").sum()),
    )
    k3.metric(
        "Potential New Listings",
        int(df["Status"].str.contains("Consider", na=False).sum()),
    )

    st.subheader("Action Needed")

    action_needed = df[
        df["Status"].isin(
            [
                "🟠 Lower Price",
                "🟡 Consider Listing",
                "🔴 No Reliable Match",
            ]
        )
    ]

    st.dataframe(
        action_needed,
        use_container_width=True,
    )

    st.markdown(
        """
        ### Status Guide

        🟢 **Competitive** = Alcohood price is equal to or lower than the cheapest selected competitor.

        🟡 **Consider Listing** = Competitor has a product but Alcohood product was not found.

        🟠 **Lower Price** = Selected competitor appears cheaper. Suggested price = competitor price - HK$1.

        🔴 **No Reliable Match** = Product match or price data is uncertain.
        """
    )

    st.subheader("Full Dashboard")

    st.dataframe(
        df,
        use_container_width=True,
    )

    st.download_button(
        "Download Main Dashboard CSV",
        df.to_csv(index=False).encode("utf-8-sig"),
        "alcohood_competitor_price_radar.csv",
        "text/csv",
    )

    st.subheader("Competitor Detail Report")

    st.dataframe(
        detail_df,
        use_container_width=True,
    )

    st.download_button(
        "Download Competitor Detail CSV",
        detail_df.to_csv(index=False).encode("utf-8-sig"),
        "alcohood_competitor_detail_report.csv",
        "text/csv",
    )

else:
    st.subheader("How to use")
    st.write(
        "1. 左邊選酒類。 2. 選要監察的競爭對手。 "
        "3. 可先按 🔥 Discover Trending Products。 "
        "4. 按 Run competitor price radar 做比價。 "
        "5. 下載 CSV 或直接睇 Action Needed。"
    )
