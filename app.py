import re
import time
import json
import urllib.parse
from datetime import datetime

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
from openai import OpenAI


st.set_page_config(
    page_title="Alcohood AI Pricing Agent",
    layout="wide"
)

st.title("🍾 Alcohood AI Pricing Agent")
st.caption(
    "Alcohood Search • Competitor Search • AI SKU Matching • Suggested Pricing"
)


# =========================
# OpenAI Client
# =========================

def get_openai_client():
    try:
        api_key = st.secrets["OPENAI_API_KEY"]
        return OpenAI(api_key=api_key)
    except Exception:
        return None


client = get_openai_client()


# =========================
# Search URL Settings
# =========================

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


# =========================
# Basic Web Helpers
# =========================

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
                price = float(str(match).replace(",", ""))

                if 20 <= price <= 100000:
                    prices.append(price)

            except Exception:
                pass

    if not prices:
        return None

    return min(prices)


def extract_json_ld_price(soup):
    scripts = soup.find_all(
        "script",
        type="application/ld+json",
    )

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


def extract_page_info(url):
    html = fetch(url)

    if not html:
        return None, "", url

    soup = BeautifulSoup(html, "html.parser")

    title = (
        soup.title.string.strip()
        if soup.title and soup.title.string
        else url
    )

    json_price = extract_json_ld_price(soup)
    text_price = money_to_float(
        soup.get_text(" ", strip=True)
    )

    price = json_price if json_price else text_price

    return price, title, url


def search_product_from_site(product_query, search_template, allowed_domain=None):
    search_url = build_search_url(
        search_template,
        product_query,
    )

    html = fetch(search_url)

    if not html:
        return {
            "title": "Search page blocked / no response",
            "price": None,
            "url": search_url,
        }

    soup = BeautifulSoup(html, "html.parser")
    search_text = soup.get_text(" ", strip=True)
    search_price = money_to_float(search_text)

    links = extract_links_from_search_page(
        html,
        search_url,
        allowed_domain=allowed_domain,
    )

    for link in links:
        price, title, product_url = extract_page_info(link)

        if price:
            return {
                "title": title,
                "price": price,
                "url": product_url,
            }

    if search_price:
        return {
            "title": "Price found on search results page",
            "price": search_price,
            "url": search_url,
        }

    return {
        "title": "Not found",
        "price": None,
        "url": search_url,
    }


# =========================
# Competitor + Alcohood Search
# =========================

def search_competitor_product(product_query, competitor_name):
    search_template = COMPETITOR_SEARCH_URLS[competitor_name]
    domain = urllib.parse.urlparse(search_template).netloc.lower()

    result = search_product_from_site(
        product_query,
        search_template,
        allowed_domain=domain,
    )

    return {
        "competitor_name": competitor_name,
        "competitor_title": result["title"],
        "competitor_price": result["price"],
        "competitor_url": result["url"],
    }


def alcohood_search(product_query):
    result = search_product_from_site(
        product_query,
        ALCOHOOD_SEARCH_TEMPLATE,
        allowed_domain="alcohood.com",
    )

    return {
        "alcohood_title": result["title"],
        "alcohood_price": result["price"],
        "alcohood_url": result["url"],
    }


# =========================
# AI SKU Matching
# =========================

def safe_json_loads(text):
    try:
        return json.loads(text)
    except Exception:
        pass

    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        return json.loads(text[start:end])
    except Exception:
        return {
            "same_sku": False,
            "confidence": 0,
            "reason": "AI response could not be parsed.",
            "ai_suggested_price": None,
            "ai_action": "Manual Review",
        }


def ai_sku_match(
    search_term,
    alcohood_name,
    alcohood_price,
    competitor_name,
    competitor_product,
    competitor_price,
):
    if client is None:
        return {
            "same_sku": False,
            "confidence": 0,
            "reason": "OpenAI API key is not connected.",
            "ai_suggested_price": None,
            "ai_action": "API Not Connected",
        }

    if not alcohood_name or not competitor_product:
        return {
            "same_sku": False,
            "confidence": 0,
            "reason": "Missing product name.",
            "ai_suggested_price": None,
            "ai_action": "Manual Review",
        }

    if not alcohood_price or not competitor_price:
        return {
            "same_sku": False,
            "confidence": 0,
            "reason": "Missing price data.",
            "ai_suggested_price": None,
            "ai_action": "Manual Review",
        }

    prompt = f"""
You are an alcohol e-commerce pricing analyst for Alcohood Hong Kong.

Your job is to decide whether the Alcohood product and competitor product are the SAME SKU.

Check carefully:
- brand
- product name
- alcohol category
- age statement, e.g. 12 years / 18 years
- edition, e.g. Double Cask / Sherry Oak / Harmony
- bottle size, e.g. 700ml / 720ml / 750ml / 1L
- vintage year for wine and champagne
- sake grade if applicable
- cognac grade if applicable, e.g. VSOP / XO

Search term:
{search_term}

Alcohood product:
{alcohood_name}
Alcohood price:
HK${alcohood_price}

Competitor:
{competitor_name}

Competitor product:
{competitor_product}
Competitor price:
HK${competitor_price}

Pricing rule:
If they are the same SKU and Alcohood is more expensive, suggested price = competitor price - 1.
If they are not the same SKU, do not suggest a new price.
If confidence is below 80, mark as Manual Review.

Return JSON only in this exact format:
{{
  "same_sku": true,
  "confidence": 95,
  "reason": "Short reason here",
  "ai_suggested_price": 667,
  "ai_action": "Lower Price"
}}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            temperature=0,
        )

        content = response.choices[0].message.content
        result = safe_json_loads(content)

        same_sku = bool(result.get("same_sku", False))
        confidence = int(result.get("confidence", 0) or 0)

        if same_sku and confidence >= 80:
            if alcohood_price > competitor_price:
                ai_suggested_price = competitor_price - 1
                ai_action = "Lower Price"
            else:
                ai_suggested_price = alcohood_price
                ai_action = "Competitive"
        else:
            ai_suggested_price = None
            ai_action = "Manual Review"

        return {
            "same_sku": same_sku,
            "confidence": confidence,
            "reason": result.get("reason", ""),
            "ai_suggested_price": ai_suggested_price,
            "ai_action": ai_action,
        }

    except Exception as error:
        return {
            "same_sku": False,
            "confidence": 0,
            "reason": f"AI error: {error}",
            "ai_suggested_price": None,
            "ai_action": "AI Error",
        }


# =========================
# Report Builder
# =========================

def build_report(
    selected_categories,
    selected_competitors,
    limit,
    use_ai,
):
    main_rows = []
    detail_rows = []

    for category in selected_categories:
        product_queries = CATEGORIES[category][:limit]

        for product_query in product_queries:
            own = alcohood_search(product_query)
            own_price = own.get("alcohood_price")

            competitor_results = []

            for competitor_name in selected_competitors:
                result = search_competitor_product(
                    product_query,
                    competitor_name,
                )

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
                item
                for item in competitor_results
                if item.get("competitor_price")
            ]

            cheapest = (
                sorted(
                    valid_competitors,
                    key=lambda x: x["competitor_price"],
                )[0]
                if valid_competitors
                else {}
            )

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

            if use_ai:
                ai_result = ai_sku_match(
                    product_query,
                    own.get("alcohood_title"),
                    own_price,
                    competitor_name,
                    competitor_title,
                    competitor_price,
                )
            else:
                ai_result = {
                    "same_sku": "",
                    "confidence": "",
                    "reason": "",
                    "ai_suggested_price": "",
                    "ai_action": "",
                }

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
                    "AI Same SKU": ai_result.get("same_sku"),
                    "AI Confidence": ai_result.get("confidence"),
                    "AI Reason": ai_result.get("reason"),
                    "AI Suggested Price": ai_result.get("ai_suggested_price"),
                    "AI Action": ai_result.get("ai_action"),
                }
            )

            time.sleep(0.5)

    return pd.DataFrame(main_rows), pd.DataFrame(detail_rows)


# =========================
# Sidebar
# =========================

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
        list(COMPETITOR_SEARCH_URLS.keys()),
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
        2,
    )

    use_ai = st.checkbox(
        "Use AI SKU Matching",
        value=True,
    )

    test_ai = st.button(
        "Test OpenAI Connection",
    )

    run = st.button(
        "Run AI Pricing Agent",
        type="primary",
    )


# =========================
# Main UI
# =========================

st.info(
    "This version searches Alcohood and competitor sites directly, then uses OpenAI to judge whether products are the same SKU. "
    "AI checks brand, age statement, edition, bottle size, vintage, and category before suggesting a price."
)


if test_ai:
    if client is None:
        st.error("OpenAI API key is not connected. Please add OPENAI_API_KEY in Streamlit Secrets.")
    else:
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": "Say: Alcohood AI is connected.",
                    }
                ],
                temperature=0,
            )
            st.success(response.choices[0].message.content)
        except Exception as error:
            st.error(f"OpenAI test failed: {error}")


if run:
    with st.spinner(
        "Searching competitor websites, checking Alcohood, and running AI SKU matching..."
    ):
        df, detail_df = build_report(
            selected_categories,
            selected_competitors,
            limit,
            use_ai,
        )

    st.success("Done")

    k1, k2, k3, k4 = st.columns(4)

    k1.metric(
        "Products Checked",
        len(df),
    )

    k2.metric(
        "Price Opportunities",
        int((df["Status"] == "🟠 Lower Price").sum()),
    )

    k3.metric(
        "AI Lower Price",
        int((df["AI Action"] == "Lower Price").sum())
        if "AI Action" in df.columns
        else 0,
    )

    k4.metric(
        "Manual Review",
        int((df["AI Action"] == "Manual Review").sum())
        if "AI Action" in df.columns
        else 0,
    )

    st.subheader("AI Action Needed")

    ai_action_needed = df[
        df["AI Action"].isin(
            [
                "Lower Price",
                "Manual Review",
                "AI Error",
                "API Not Connected",
            ]
        )
    ]

    st.dataframe(
        ai_action_needed,
        use_container_width=True,
    )

    st.subheader("Full Dashboard")

    st.dataframe(
        df,
        use_container_width=True,
    )

    st.download_button(
        "Download AI Dashboard CSV",
        df.to_csv(index=False).encode("utf-8-sig"),
        "alcohood_ai_pricing_agent.csv",
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
    st.subheader("How this AI agent works")
    st.write(
        "1. Select categories and competitors. "
        "2. The app searches Alcohood and competitor websites directly. "
        "3. It extracts product names, prices, and links. "
        "4. OpenAI checks whether the products are the same SKU. "
        "5. If same SKU and Alcohood is more expensive, AI suggested price = competitor price - HK$1. "
        "6. If confidence is below 80, it marks Manual Review."
    )
