import re
import time
import json
import os
import urllib.parse
from io import StringIO
from datetime import datetime

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
from openai import OpenAI


try:
    from browser_agent import (
        browser_test,
        search_watsons,
        search_winecouple,
        search_cellarmaster,
        search_myicellar,
        search_ponti,
        search_rng,
        search_onexcel,
        search_waishing,
        search_alcohood,
    )
except Exception:
    browser_test = None
    search_watsons = None
    search_winecouple = None
    search_cellarmaster = None
    search_myicellar = None
    search_ponti = None
    search_rng = None
    search_onexcel = None
    search_waishing = None
    search_alcohood = None


st.set_page_config(
    page_title="Alcohood AI Demand & Pricing Agent",
    layout="wide"
)

st.title("🍾 Alcohood AI Demand & Pricing Agent")
st.caption(
    "Google Ads Search Terms • Browser Agent Search • AI Product Extraction • SKU Matching • Pricing Action"
)


def get_openai_client():
    try:
        api_key = os.environ.get("OPENAI_API_KEY")

        if not api_key:
            api_key = st.secrets.get("OPENAI_API_KEY")

        if not api_key:
            return None

        return OpenAI(api_key=api_key)

    except Exception:
        return None


client = get_openai_client()


BROWSER_SEARCH_FUNCTIONS = {
    "Watson's Wine": search_watsons,
    "Wine Couple": search_winecouple,
    "Cellarmaster": search_cellarmaster,
    "MyiCellar": search_myicellar,
    "Ponti Wine Cellars": search_ponti,
    "RNG Wine": search_rng,
    "Onexcel Wine": search_onexcel,
    "偉成洋酒": search_waishing,
}


FALLBACK_SEARCH_URLS = {
    "Watson's Wine": "https://www.watsonswine.com/en/search?text={query}&useDefaultSearch=false&brandRedirect=true",
    "Wine Couple": "https://www.winecouple.hk/products?query={query}",
    "Cellarmaster": "https://cellarmasterwines.com/search?q={query}&options%5Bprefix%5D=last",
    "MyiCellar": "https://shop.myicellar.com/search?q={query}",
    "Ponti Wine Cellars": "https://www.pontiwinecellars.com.hk/products?query={query}",
    "RNG Wine": "https://www.rngwine.com/products?query={query}",
    "Onexcel Wine": "https://www.onexcel-wine.com/ProductAdvanceSearch?ProductName={query}",
    "偉成洋酒": "https://www.waishingwine.com.hk/products?query={query}",
    "Alcohood": "https://www.alcohood.com/search?q={query}",
}


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/125 Safari/537.36"
    ),
    "Accept-Language": "en-HK,en;q=0.9,zh-HK;q=0.8",
}


# =========================
# Basic Helpers
# =========================

def build_search_url(template, query):
    return template.replace("{query}", urllib.parse.quote_plus(str(query)))


@st.cache_data(ttl=3600)
def fetch(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=20)
        if response.status_code == 200:
            return response.text
        return ""
    except Exception:
        return ""


def safe_json_loads(text):
    if not text:
        return {}

    try:
        return json.loads(text)
    except Exception:
        pass

    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        return json.loads(text[start:end])
    except Exception:
        return {}


def clean_number(value):
    if pd.isna(value):
        return 0

    text = str(value)
    text = text.replace(",", "")
    text = text.replace("HK$", "")
    text = text.replace("$", "")
    text = text.replace("%", "")
    text = text.strip()

    match = re.search(r"-?\d+(?:\.\d+)?", text)

    if not match:
        return 0

    try:
        return float(match.group(0))
    except Exception:
        return 0


def money_to_float(text):
    if not text:
        return None

    patterns = [
        r"(?:HK\$|HKD|\$)\s*([0-9][0-9,]*(?:\.\d+)?)",
        r"([0-9][0-9,]*(?:\.\d+)?)\s*(?:HKD|港幣|港元)",
    ]

    prices = []

    for pattern in patterns:
        for match in re.findall(pattern, text, re.I):
            try:
                price = float(str(match).replace(",", ""))
                if 20 <= price <= 100000:
                    prices.append(price)
            except Exception:
                pass

    return min(prices) if prices else None


def html_to_clean_text(html, max_chars=12000):
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.extract()

    text = soup.get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text)

    return text[:max_chars]


def extract_links_from_html(html, base_url=None, allowed_domain=None, max_links=20):
    soup = BeautifulSoup(html or "", "html.parser")
    links = []

    parsed_base = urllib.parse.urlparse(base_url) if base_url else None
    base_domain = parsed_base.netloc if parsed_base else ""

    for a in soup.find_all("a", href=True):
        href = a["href"]

        if href.startswith("/") and parsed_base:
            href = f"{parsed_base.scheme}://{base_domain}{href}"

        if not href.startswith("http"):
            continue

        lowered = href.lower()

        if allowed_domain and allowed_domain not in lowered:
            continue

        if any(skip in lowered for skip in [
            "cart", "checkout", "account", "login", "register",
            "wishlist", "facebook", "instagram", "whatsapp",
            "mailto", "tel:", "privacy", "terms"
        ]):
            continue

        links.append(href)

    return list(dict.fromkeys(links))[:max_links]


# =========================
# Google Ads CSV Handling
# =========================

def find_column(df, possible_names):
    lower_map = {
        str(col).lower().strip(): col
        for col in df.columns
    }

    for name in possible_names:
        if name.lower() in lower_map:
            return lower_map[name.lower()]

    for col in df.columns:
        col_lower = str(col).lower()

        for name in possible_names:
            if name.lower() in col_lower:
                return col

    return None


def smart_read_uploaded_text(uploaded_file):
    raw = uploaded_file.getvalue()

    encodings = [
        "utf-8-sig",
        "utf-8",
        "big5",
        "cp950",
        "latin1",
    ]

    for enc in encodings:
        try:
            return raw.decode(enc)
        except Exception:
            continue

    return raw.decode("utf-8", errors="ignore")


def detect_header_index(lines):
    header_keywords = [
        "搜尋字詞",
        "Search term",
        "Search Term",
        "搜索字詞",
        "Clicks",
        "點擊次數",
    ]

    for i, line in enumerate(lines):
        score = 0

        for keyword in header_keywords:
            if keyword in line:
                score += 1

        if score >= 2:
            return i

    for i, line in enumerate(lines):
        if "," in line or "\t" in line:
            return i

    return 0


def read_table_from_text(text):
    lines = text.splitlines()
    header_index = detect_header_index(lines)
    cleaned_text = "\n".join(lines[header_index:])

    attempts = [
        {"sep": None, "engine": "python"},
        {"sep": "\t", "engine": "python"},
        {"sep": ",", "engine": "python"},
        {"sep": ";", "engine": "python"},
    ]

    for kwargs in attempts:
        try:
            df = pd.read_csv(
                StringIO(cleaned_text),
                **kwargs,
                on_bad_lines="skip",
            )

            if len(df.columns) >= 2:
                return df

        except Exception:
            continue

    return pd.DataFrame()


def load_google_ads_csv(uploaded_file):
    try:
        text = smart_read_uploaded_text(uploaded_file)
        df = read_table_from_text(text)

    except Exception as error:
        st.error(f"Failed to read uploaded file: {error}")
        return pd.DataFrame()

    if df.empty:
        st.error("Unable to read the Google Ads file. Please export Search Terms as CSV.")
        return pd.DataFrame()

    search_col = find_column(
        df,
        [
            "Search term",
            "Search Terms",
            "搜尋字詞",
            "搜索字詞",
            "搜尋字詞 ",
        ],
    )

    clicks_col = find_column(
        df,
        [
            "Clicks",
            "點擊次數",
            "點擊",
        ],
    )

    cost_col = find_column(
        df,
        [
            "Cost",
            "成本",
            "費用",
        ],
    )

    impressions_col = find_column(
        df,
        [
            "Impressions",
            "展示",
            "展示次數",
        ],
    )

    if not search_col:
        st.error("Cannot find Search Term column. Please check your CSV export.")
        st.write("Detected columns:")
        st.write(list(df.columns))
        return pd.DataFrame()

    clean_df = pd.DataFrame()
    clean_df["Search Term"] = df[search_col].astype(str)

    clean_df["Clicks"] = (
        df[clicks_col].apply(clean_number)
        if clicks_col
        else 0
    )

    clean_df["Cost"] = (
        df[cost_col].astype(str)
        if cost_col
        else ""
    )

    clean_df["Impressions"] = (
        df[impressions_col].apply(clean_number)
        if impressions_col
        else 0
    )

    clean_df = clean_df.dropna(subset=["Search Term"])
    clean_df = clean_df[clean_df["Search Term"].str.strip() != ""]
    clean_df = clean_df[
        ~clean_df["Search Term"].str.contains(
            "Total|總計|已移除",
            case=False,
            na=False,
        )
    ]

    clean_df = clean_df.drop_duplicates(subset=["Search Term"])

    return clean_df


# =========================
# AI Logic
# =========================

def ai_classify_search_term(term):
    if client is None:
        return {
            "type": "API_NOT_CONNECTED",
            "normalized_product": "",
            "category": "",
            "reason": "OpenAI API is not connected.",
        }

    prompt = f"""
You are an alcohol e-commerce analyst for Alcohood Hong Kong.

Classify this Google Ads search term.

Search term:
{term}

Classification options:
- PRODUCT: specific sellable alcohol product, e.g. Macallan 12, Dassai 45, Hennessy XO
- BRAND: brand only, e.g. Macallan, Hennessy, Dassai
- COMPETITOR: shop name or competitor name, e.g. Watson Wine, Wine Couple
- GENERIC: broad category, e.g. red wine, sake, whisky, champagne
- IGNORE: unrelated or too vague

Return JSON only:
{{
  "type": "PRODUCT",
  "normalized_product": "Macallan 12",
  "category": "Whisky",
  "reason": "Specific product search"
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

        data = safe_json_loads(response.choices[0].message.content)

        return {
            "type": data.get("type", "IGNORE"),
            "normalized_product": data.get("normalized_product", ""),
            "category": data.get("category", ""),
            "reason": data.get("reason", ""),
        }

    except Exception as error:
        return {
            "type": "AI_ERROR",
            "normalized_product": "",
            "category": "",
            "reason": str(error),
        }


def ai_extract_product_from_page(search_term, site_name, page_text, candidate_links):
    if client is None:
        return {
            "found": False,
            "product_name": "",
            "price": None,
            "currency": "",
            "url": "",
            "confidence": 0,
            "reason": "OpenAI API is not connected.",
        }

    prompt = f"""
You are an alcohol ecommerce research agent.

Task:
From the rendered website text below, find the best matching alcohol product for the search term.

Search term:
{search_term}

Website:
{site_name}

Rules:
- Only return a result if it is a real product listing.
- Do not use delivery fee, shipping fee, membership fee, event fee, deposit, or coupon value as product price.
- Prefer exact SKU match.
- Check brand, age statement, edition, bottle size, vintage, grade.
- If the page does not clearly show a matching product and price, return found=false.
- Price must be in HKD if possible.
- Use candidate links only if they seem related to the product.

Rendered page text:
{page_text[:10000]}

Candidate links:
{candidate_links[:20]}

Return JSON only:
{{
  "found": true,
  "product_name": "The Macallan 12 Years Old Double Cask 700ml",
  "price": 497,
  "currency": "HKD",
  "url": "https://example.com/product-url",
  "confidence": 92,
  "reason": "Best visible matching product with HKD price"
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

        data = safe_json_loads(response.choices[0].message.content)

        return {
            "found": bool(data.get("found", False)),
            "product_name": data.get("product_name", ""),
            "price": data.get("price"),
            "currency": data.get("currency", ""),
            "url": data.get("url", ""),
            "confidence": data.get("confidence", 0),
            "reason": data.get("reason", ""),
        }

    except Exception as error:
        return {
            "found": False,
            "product_name": "",
            "price": None,
            "currency": "",
            "url": "",
            "confidence": 0,
            "reason": f"AI extraction error: {error}",
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
            "reason": "OpenAI API is not connected.",
            "ai_action": "API Not Connected",
            "ai_suggested_price": None,
        }

    if not alcohood_price or not competitor_price:
        return {
            "same_sku": False,
            "confidence": 0,
            "reason": "Missing Alcohood or competitor price.",
            "ai_action": "Manual Review",
            "ai_suggested_price": None,
        }

    prompt = f"""
You are an alcohol e-commerce pricing analyst for Alcohood Hong Kong.

Decide whether the Alcohood product and competitor product are the SAME SKU.

Check:
- brand
- product name
- category
- age statement
- edition, e.g. Double Cask / Sherry Oak
- bottle size, e.g. 700ml / 720ml / 750ml / 1L
- vintage for wine/champagne
- sake grade
- cognac grade

Search term:
{search_term}

Alcohood:
{alcohood_name}
Price: HK${alcohood_price}

Competitor:
{competitor_name}
{competitor_product}
Price: HK${competitor_price}

Rule:
If same SKU and Alcohood is more expensive, suggested price = competitor price - 1.
If not same SKU or confidence below 80, action = Manual Review.

Return JSON only:
{{
  "same_sku": true,
  "confidence": 95,
  "reason": "Same product, same age and edition.",
  "ai_action": "Lower Price",
  "ai_suggested_price": 667
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

        data = safe_json_loads(response.choices[0].message.content)

        same_sku = bool(data.get("same_sku", False))
        confidence = int(data.get("confidence", 0) or 0)

        if same_sku and confidence >= 80:
            if float(alcohood_price) > float(competitor_price):
                ai_action = "Lower Price"
                ai_suggested_price = float(competitor_price) - 1
            else:
                ai_action = "Competitive"
                ai_suggested_price = float(alcohood_price)
        else:
            ai_action = "Manual Review"
            ai_suggested_price = None

        return {
            "same_sku": same_sku,
            "confidence": confidence,
            "reason": data.get("reason", ""),
            "ai_action": ai_action,
            "ai_suggested_price": ai_suggested_price,
        }

    except Exception as error:
        return {
            "same_sku": False,
            "confidence": 0,
            "reason": f"AI error: {error}",
            "ai_action": "AI Error",
            "ai_suggested_price": None,
        }


# =========================
# Browser Search Agent
# =========================

def get_rendered_html_for_site(site_name, product_query):
    search_func = BROWSER_SEARCH_FUNCTIONS.get(site_name)

    if search_func is None:
        return ""

    try:
        return search_func(product_query)
    except Exception as error:
        return f"__BROWSER_ERROR__: {error}"


def fallback_fetch_html(site_name, product_query):
    template = FALLBACK_SEARCH_URLS.get(site_name)

    if not template:
        return ""

    url = build_search_url(template, product_query)
    return fetch(url)


def extract_site_product(site_name, product_query):
    html = get_rendered_html_for_site(site_name, product_query)
    method = "Playwright Browser"

    if not html or html.startswith("__BROWSER_ERROR__"):
        error_msg = html
        html = fallback_fetch_html(site_name, product_query)
        method = f"Fallback requests after browser error: {error_msg}"

    search_url = build_search_url(
        FALLBACK_SEARCH_URLS.get(site_name, ""),
        product_query,
    )

    page_text = html_to_clean_text(html)
    candidate_links = extract_links_from_html(
        html,
        base_url=search_url,
    )

    ai_result = ai_extract_product_from_page(
        product_query,
        site_name,
        page_text,
        candidate_links,
    )

    price = ai_result.get("price")

    try:
        if price is not None and price != "":
            price = float(str(price).replace(",", ""))
        else:
            price = None
    except Exception:
        price = None

    return {
        "site": site_name,
        "method": method,
        "found": ai_result.get("found"),
        "product_name": ai_result.get("product_name"),
        "price": price,
        "currency": ai_result.get("currency"),
        "url": ai_result.get("url") or search_url,
        "confidence": ai_result.get("confidence"),
        "reason": ai_result.get("reason"),
        "page_text_preview": page_text[:1000],
    }


def extract_alcohood_product(product_query):
    html = ""

    if search_alcohood:
        try:
            html = search_alcohood(product_query)
        except Exception as error:
            html = f"__BROWSER_ERROR__: {error}"

    method = "Playwright Browser"

    if not html or html.startswith("__BROWSER_ERROR__"):
        error_msg = html
        html = fallback_fetch_html("Alcohood", product_query)
        method = f"Fallback requests after browser error: {error_msg}"

    search_url = build_search_url(
        FALLBACK_SEARCH_URLS.get("Alcohood", ""),
        product_query,
    )

    page_text = html_to_clean_text(html)
    candidate_links = extract_links_from_html(
        html,
        base_url=search_url,
        allowed_domain="alcohood.com",
    )

    ai_result = ai_extract_product_from_page(
        product_query,
        "Alcohood",
        page_text,
        candidate_links,
    )

    price = ai_result.get("price")

    try:
        if price is not None and price != "":
            price = float(str(price).replace(",", ""))
        else:
            price = None
    except Exception:
        price = None

    return {
        "site": "Alcohood",
        "method": method,
        "found": ai_result.get("found"),
        "product_name": ai_result.get("product_name"),
        "price": price,
        "currency": ai_result.get("currency"),
        "url": ai_result.get("url") or search_url,
        "confidence": ai_result.get("confidence"),
        "reason": ai_result.get("reason"),
        "page_text_preview": page_text[:1000],
    }


# =========================
# Report Builders
# =========================

def classify_ads_terms(ads_df, max_terms):
    rows = []

    working_df = ads_df.sort_values(
        by="Clicks",
        ascending=False,
    ).head(max_terms)

    for _, row in working_df.iterrows():
        term = row["Search Term"]
        ai = ai_classify_search_term(term)

        rows.append(
            {
                "Search Term": term,
                "Clicks": row.get("Clicks", 0),
                "Impressions": row.get("Impressions", 0),
                "Cost": row.get("Cost", ""),
                "AI Type": ai.get("type"),
                "Normalized Product": ai.get("normalized_product"),
                "AI Category": ai.get("category"),
                "AI Reason": ai.get("reason"),
            }
        )

        time.sleep(0.2)

    return pd.DataFrame(rows)


def build_browser_price_radar(product_df, selected_competitors):
    main_rows = []
    detail_rows = []

    product_rows = product_df[
        product_df["AI Type"].isin(
            [
                "PRODUCT",
                "BRAND",
                "GENERIC",
            ]
        )
    ]

    for _, row in product_rows.iterrows():
        search_term = row["Search Term"]

        if row["AI Type"] == "PRODUCT" and row["Normalized Product"]:
            product_query = row["Normalized Product"]
        else:
            product_query = search_term

        alcohood_result = extract_alcohood_product(product_query)
        alcohood_price = alcohood_result.get("price")

        competitor_results = []

        for competitor_name in selected_competitors:
            result = extract_site_product(
                competitor_name,
                product_query,
            )

            competitor_results.append(result)

            detail_rows.append(
                {
                    "Date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "Search Term": search_term,
                    "Product Query": product_query,
                    "Site": competitor_name,
                    "Method": result.get("method"),
                    "Found": result.get("found"),
                    "Product Name": result.get("product_name"),
                    "Price": result.get("price"),
                    "Currency": result.get("currency"),
                    "URL": result.get("url"),
                    "Confidence": result.get("confidence"),
                    "Reason": result.get("reason"),
                    "Text Preview": result.get("page_text_preview"),
                }
            )

            time.sleep(0.5)

        valid_competitors = [
            item
            for item in competitor_results
            if item.get("found") and item.get("price")
        ]

        cheapest = (
            sorted(
                valid_competitors,
                key=lambda x: x["price"],
            )[0]
            if valid_competitors
            else {}
        )

        competitor_price = cheapest.get("price")
        competitor_name = cheapest.get("site", "")
        competitor_product = cheapest.get("product_name", "")
        competitor_url = cheapest.get("url", "")

        if alcohood_price and competitor_price:
            difference = alcohood_price - competitor_price

            ai_match = ai_sku_match(
                product_query,
                alcohood_result.get("product_name"),
                alcohood_price,
                competitor_name,
                competitor_product,
                competitor_price,
            )

            if ai_match.get("ai_action") == "Lower Price":
                status = "🟠 Lower Price"
                suggested_price = ai_match.get("ai_suggested_price")
            elif ai_match.get("ai_action") == "Competitive":
                status = "🟢 Competitive"
                suggested_price = alcohood_price
            else:
                status = "🔴 Manual Review"
                suggested_price = ""

        elif competitor_price and not alcohood_price:
            difference = ""
            suggested_price = ""
            status = "🟡 Consider Listing"
            ai_match = {
                "same_sku": "",
                "confidence": "",
                "reason": "Alcohood product not found, competitor has product.",
                "ai_action": "Consider Listing",
                "ai_suggested_price": "",
            }

        elif not competitor_price and not alcohood_price:
            difference = ""
            suggested_price = ""
            status = "🔵 Market Demand Only"
            ai_match = {
                "same_sku": "",
                "confidence": "",
                "reason": "No Alcohood or competitor price found.",
                "ai_action": "Market Demand Only",
                "ai_suggested_price": "",
            }

        else:
            difference = ""
            suggested_price = ""
            status = "🔴 No Reliable Match"
            ai_match = {
                "same_sku": "",
                "confidence": "",
                "reason": "Alcohood found but competitor not found.",
                "ai_action": "Manual Review",
                "ai_suggested_price": "",
            }

        main_rows.append(
            {
                "Date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "Search Term": search_term,
                "Clicks": row.get("Clicks", 0),
                "Impressions": row.get("Impressions", 0),
                "AI Type": row.get("AI Type"),
                "Product Query": product_query,
                "Alcohood Found": alcohood_result.get("found"),
                "Alcohood Product": alcohood_result.get("product_name"),
                "Alcohood Price": alcohood_price,
                "Alcohood URL": alcohood_result.get("url"),
                "Alcohood Confidence": alcohood_result.get("confidence"),
                "Alcohood Reason": alcohood_result.get("reason"),
                "Cheapest Competitor": competitor_name,
                "Competitor Product": competitor_product,
                "Competitor Price": competitor_price,
                "Competitor URL": competitor_url,
                "Difference": difference,
                "Suggested Price": suggested_price,
                "Status": status,
                "AI Same SKU": ai_match.get("same_sku"),
                "AI Confidence": ai_match.get("confidence"),
                "AI Reason": ai_match.get("reason"),
                "AI Action": ai_match.get("ai_action"),
                "AI Suggested Price": ai_match.get("ai_suggested_price"),
            }
        )

        time.sleep(0.5)

    return pd.DataFrame(main_rows), pd.DataFrame(detail_rows)


# =========================
# Sidebar
# =========================

with st.sidebar:
    st.header("Settings")

    uploaded_file = st.file_uploader(
        "Upload Google Ads Search Terms CSV",
        type=["csv", "txt"],
    )

    selected_competitors = st.multiselect(
        "Competitors",
        list(BROWSER_SEARCH_FUNCTIONS.keys()),
        default=[
            "Watson's Wine",
            "Wine Couple",
            "Cellarmaster",
            "MyiCellar",
            "Ponti Wine Cellars",
        ],
    )

    max_terms = st.slider(
        "Max search terms to analyse",
        5,
        50,
        10,
    )

    run_classification = st.button(
        "1️⃣ Analyse Google Ads Terms",
        type="primary",
    )

    run_price_radar = st.button(
        "2️⃣ Run Browser AI Price Radar",
    )

    test_ai = st.button(
        "Test OpenAI Connection",
    )

    test_browser = st.button(
        "Test Browser Agent",
    )

    test_watsons = st.button(
        "Test Watson's Wine Search",
    )


# =========================
# Main UI
# =========================

st.info(
    "This version uses a real browser via Playwright on Render, then uses OpenAI to extract the best matching product, price, and link from rendered website pages."
)


if test_ai:
    if client is None:
        st.error("OpenAI API key is not connected.")
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


if test_browser:
    if browser_test is None:
        st.error("browser_agent.py is not imported correctly.")
    else:
        try:
            result = browser_test()
            st.success(f"Browser is working: {result}")
        except Exception as error:
            st.error(f"Browser test failed: {error}")


if test_watsons:
    if search_watsons is None:
        st.error("search_watsons is not imported correctly.")
    else:
        try:
            html = search_watsons("macallan 12")
            text = html_to_clean_text(html, max_chars=5000)
            st.success("Watson's Wine page loaded.")
            st.text(text)
        except Exception as error:
            st.error(f"Watson's Wine search failed: {error}")


if uploaded_file:
    ads_df = load_google_ads_csv(uploaded_file)

    if not ads_df.empty:
        st.subheader("Uploaded Google Ads Search Terms")
        st.dataframe(
            ads_df.head(50),
            width="stretch",
        )

        if run_classification:
            with st.spinner("AI is classifying Google Ads search terms..."):
                classified_df = classify_ads_terms(
                    ads_df,
                    max_terms,
                )

            st.session_state["classified_df"] = classified_df

        if "classified_df" in st.session_state:
            classified_df = st.session_state["classified_df"]

            st.subheader("AI Search Term Classification")

            st.dataframe(
                classified_df,
                width="stretch",
            )

            st.download_button(
                "Download AI Classification CSV",
                classified_df.to_csv(index=False).encode("utf-8-sig"),
                "alcohood_google_ads_ai_classification.csv",
                "text/csv",
            )

            c1, c2, c3, c4, c5 = st.columns(5)

            c1.metric(
                "PRODUCT",
                int((classified_df["AI Type"] == "PRODUCT").sum()),
            )
            c2.metric(
                "BRAND",
                int((classified_df["AI Type"] == "BRAND").sum()),
            )
            c3.metric(
                "COMPETITOR",
                int((classified_df["AI Type"] == "COMPETITOR").sum()),
            )
            c4.metric(
                "GENERIC",
                int((classified_df["AI Type"] == "GENERIC").sum()),
            )
            c5.metric(
                "IGNORE",
                int((classified_df["AI Type"] == "IGNORE").sum()),
            )

            product_terms_df = classified_df[
                classified_df["AI Type"].isin(
                    [
                        "PRODUCT",
                        "BRAND",
                        "GENERIC",
                    ]
                )
            ]

            st.subheader("Product Terms Selected for Browser Price Radar")
            st.dataframe(
                product_terms_df,
                width="stretch",
            )

            if run_price_radar:
                with st.spinner("Browser Agent is searching competitor websites and OpenAI is extracting prices..."):
                    radar_df, detail_df = build_browser_price_radar(
                        product_terms_df,
                        selected_competitors,
                    )

                st.session_state["radar_df"] = radar_df
                st.session_state["detail_df"] = detail_df

        if "radar_df" in st.session_state:
            radar_df = st.session_state["radar_df"]
            detail_df = st.session_state["detail_df"]

            st.success("Browser AI Price Radar completed")

            k1, k2, k3, k4 = st.columns(4)

            k1.metric(
                "Items Checked",
                len(radar_df),
            )
            k2.metric(
                "Lower Price",
                int((radar_df["Status"] == "🟠 Lower Price").sum()),
            )
            k3.metric(
                "Consider Listing",
                int((radar_df["Status"] == "🟡 Consider Listing").sum()),
            )
            k4.metric(
                "Market Demand Only",
                int((radar_df["Status"] == "🔵 Market Demand Only").sum()),
            )

            st.subheader("Price Actions / Review Needed")

            st.dataframe(
                radar_df[
                    radar_df["Status"].isin(
                        [
                            "🟠 Lower Price",
                            "🟢 Competitive",
                            "🔴 Manual Review",
                            "🔴 No Reliable Match",
                        ]
                    )
                ],
                width="stretch",
            )

            st.subheader("Listing Opportunities")

            st.dataframe(
                radar_df[
                    radar_df["Status"].isin(
                        [
                            "🟡 Consider Listing",
                            "🔵 Market Demand Only",
                        ]
                    )
                ],
                width="stretch",
            )

            st.subheader("Full Browser AI Radar Dashboard")

            st.dataframe(
                radar_df,
                width="stretch",
            )

            st.download_button(
                "Download Browser AI Radar CSV",
                radar_df.to_csv(index=False).encode("utf-8-sig"),
                "alcohood_browser_ai_radar.csv",
                "text/csv",
            )

            st.subheader("Competitor Search Detail Report")

            st.dataframe(
                detail_df,
                width="stretch",
            )

            st.download_button(
                "Download Detail CSV",
                detail_df.to_csv(index=False).encode("utf-8-sig"),
                "alcohood_browser_ai_detail.csv",
                "text/csv",
            )

else:
    st.subheader("How to use")
    st.write(
        "1. Upload Google Ads Search Terms CSV. "
        "2. Click Test Browser Agent first. "
        "3. Click Test Watson's Wine Search. "
        "4. Click 1️⃣ Analyse Google Ads Terms. "
        "5. Click 2️⃣ Run Browser AI Price Radar."
    )
