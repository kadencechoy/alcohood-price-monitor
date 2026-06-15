import re
import time
import urllib.parse
from datetime import datetime

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup


st.set_page_config(
    page_title="Alcohood AI Pricing Monitor",
    layout="wide"
)

st.title("Alcohood AI Pricing Monitor")
st.caption(
    "ChatGPT-made no-API prototype: Google Shopping public search + Alcohood public pages. "
    "Results depend on what public webpages return."
)


CATEGORIES = {
    "Red wine": [
        "red wine hong kong",
        "pinot noir hong kong",
        "cabernet sauvignon hong kong",
        "bourgogne rouge hong kong",
        "opus one hong kong",
        "penfolds bin 389 hong kong",
    ],
    "White wine": [
        "white wine hong kong",
        "chardonnay hong kong",
        "sauvignon blanc hong kong",
        "riesling hong kong",
        "cloudy bay sauvignon blanc hong kong",
        "chablis hong kong",
    ],
    "Sparkling Wine": [
        "sparkling wine hong kong",
        "prosecco hong kong",
        "cava hong kong",
        "freixenet hong kong",
        "cremant hong kong",
        "laurent perrier hong kong",
    ],
    "Champagne": [
        "moet chandon brut hong kong",
        "veuve clicquot hong kong",
        "dom perignon hong kong",
        "perrier jouet hong kong",
        "bollinger hong kong",
        "krug hong kong",
    ],
    "Sake": [
        "dassai 45 hong kong",
        "kubota manju hong kong",
        "kamoshibito kuheiji hong kong",
        "hakkaisan sake hong kong",
        "juyondai hong kong",
        "born sake hong kong",
    ],
    "Whisky": [
        "macallan 12 hong kong",
        "yamazaki 12 hong kong",
        "hibiki harmony hong kong",
        "nikka from the barrel hong kong",
        "glenfiddich 12 hong kong",
        "ardbeg 10 hong kong",
    ],
    "Cognac": [
        "hennessy vsop hong kong",
        "martell cordon bleu hong kong",
        "remy martin vsop hong kong",
        "hennessy xo hong kong",
        "martell xo hong kong",
        "remy martin xo hong kong",
    ],
    "Brandy": [
        "brandy hong kong",
        "torres 10 hong kong",
        "st remy xo hong kong",
        "fundador brandy hong kong",
        "cardenal mendoza hong kong",
        "torres 20 hong kong",
    ],
    "Gin": [
        "roku gin hong kong",
        "hendricks gin hong kong",
        "two moons gin hong kong",
        "nip gin hong kong",
        "bombay sapphire hong kong",
        "monkey 47 hong kong",
    ],
    "Tequila & Agave Spirits": [
        "don julio 1942 hong kong",
        "casamigos reposado hong kong",
        "patron silver hong kong",
        "818 tequila hong kong",
        "mezcal hong kong",
        "codigo tequila hong kong",
    ],
    "Liqueur": [
        "baileys hong kong",
        "kahlua hong kong",
        "disaronno hong kong",
        "cointreau hong kong",
        "malibu rum liqueur hong kong",
        "sheridans hong kong",
    ],
    "Fruit Wine": [
        "plum wine hong kong",
        "umeshu hong kong",
        "choya umeshu hong kong",
        "yuzu wine hong kong",
        "peach wine hong kong",
        "lychee wine hong kong",
    ],
    "Baijiu": [
        "moutai hong kong",
        "wuliangye hong kong",
        "yanghe hong kong",
        "guojiao 1573 hong kong",
        "fenjiu hong kong",
        "xijiu hong kong",
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

    match = re.search(
        r"(?:HK\$|HKD|\$)\s*([0-9][0-9,]*(?:\.\d+)?)",
        text,
        re.I,
    )

    if not match:
        return None

    return float(match.group(1).replace(",", ""))


def shopping_search(query, max_results=8):
    url = (
        "https://www.google.com/search?udm=28&hl=en-HK&gl=HK&q="
        + urllib.parse.quote(query)
    )

    html = fetch(url)
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    results = []

    price_matches = list(
        re.finditer(
            r"(HK\$|HKD|\$)\s*[0-9][0-9,]*(?:\.\d+)?",
            text,
        )
    )

    for price_match in price_matches[:max_results]:
        start = max(0, price_match.start() - 140)
        end = min(len(text), price_match.end() + 180)

        snippet = text[start:end]
        price = money_to_float(price_match.group(0))

        if price:
            results.append(
                {
                    "query": query,
                    "competitor_title": snippet[:220],
                    "competitor_price": price,
                    "competitor_url": url,
                }
            )

    return results


def alcohood_search(query):
    url = (
        "https://www.google.com/search?hl=en-HK&gl=HK&q=site%3Aalcohood.com+"
        + urllib.parse.quote(query)
    )

    html = fetch(url)
    soup = BeautifulSoup(html, "html.parser")

    links = []

    for link_tag in soup.find_all("a", href=True):
        href = link_tag["href"]

        if "alcohood.com" in href and "/url?q=" in href:
            href = urllib.parse.parse_qs(
                urllib.parse.urlparse(href).query
            ).get("q", [""])[0]

        if "alcohood.com" in href and href.startswith("http"):
            links.append(href)

    links = list(dict.fromkeys(links))[:3]

    for link in links:
        html2 = fetch(link)
        soup2 = BeautifulSoup(html2, "html.parser")
        page_text = soup2.get_text(" ", strip=True)

        price = money_to_float(page_text)

        if soup2.title and soup2.title.string:
            title = soup2.title.string
        else:
            title = query

        if price:
            return {
                "alcohood_title": title,
                "alcohood_price": price,
                "alcohood_url": link,
            }

    return {
        "alcohood_title": "Not found",
        "alcohood_price": None,
        "alcohood_url": "",
    }


def build_report(selected_categories, limit):
    rows = []

    for category in selected_categories:
        for query in CATEGORIES[category][:limit]:
            competitor_results = shopping_search(query, 5)

            competitor_results_sorted = sorted(
                [
                    item
                    for item in competitor_results
                    if item.get("competitor_price")
                ],
                key=lambda x: x["competitor_price"],
            )

            cheapest = (
                competitor_results_sorted[0]
                if competitor_results_sorted
                else {}
            )

            own = alcohood_search(query)

            own_price = own.get("alcohood_price")
            competitor_price = cheapest.get("competitor_price")

            if own_price and competitor_price:
                difference = own_price - competitor_price

                if difference > 0:
                    suggested_price = competitor_price - 1
                    status = "Lower Price"
                else:
                    suggested_price = own_price
                    status = "Competitive"

            elif competitor_price and not own_price:
                difference = ""
                suggested_price = ""
                status = "Consider Listing / Alcohood not found"

            else:
                difference = ""
                suggested_price = ""
                status = "No reliable match"

            rows.append(
                {
                    "Date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "Category": category,
                    "Search / Trend Candidate": query,
                    "Alcohood Product": own.get("alcohood_title"),
                    "Alcohood Price": own_price,
                    "Alcohood URL": own.get("alcohood_url"),
                    "Cheapest Competitor Snippet": cheapest.get(
                        "competitor_title",
                        "",
                    ),
                    "Competitor Price": competitor_price,
                    "Competitor Link": cheapest.get("competitor_url", ""),
                    "Difference": difference,
                    "Suggested Price": suggested_price,
                    "Status": status,
                }
            )

            time.sleep(1)

    return pd.DataFrame(rows)


with st.sidebar:
    st.header("Settings")

    cats = st.multiselect(
        "Categories",
        list(CATEGORIES.keys()),
        default=list(CATEGORIES.keys()),
    )

    limit = st.slider(
        "Candidates per category",
        1,
        6,
        2,
    )

    run = st.button(
        "Run price monitor",
        type="primary",
    )


st.info(
    "第一版不需要你設定 API。按 Run 後會用公開 Google Shopping 搜尋頁 + Alcohood 公開頁面嘗試比價。"
    "Google 有機會封鎖或返回不完整資料，所以狀態會標記 No reliable match。"
)


if run:
    with st.spinner("Searching public web and building dashboard..."):
        df = build_report(cats, limit)

    st.success("Done")

    k1, k2, k3 = st.columns(3)

    k1.metric("Items checked", len(df))
    k2.metric("Need lower price", int((df["Status"] == "Lower Price").sum()))
    k3.metric(
        "Consider listing / no own price",
        int(df["Status"].str.contains("Consider", na=False).sum()),
    )

    st.subheader("Action Needed")

    action_needed = df[
        df["Status"].isin(
            [
                "Lower Price",
                "Consider Listing / Alcohood not found",
                "No reliable match",
            ]
        )
    ]

    st.dataframe(
        action_needed,
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
        "alcohood_price_monitor.csv",
        "text/csv",
    )

else:
    st.subheader("How to use")
    st.write(
        "1. 左邊選酒類。 2. 按 Run price monitor。 "
        "3. 下載 CSV 或直接睇 Action Needed。"
    )
