import re
import time
import json
import urllib.parse
from io import StringIO
from datetime import datetime

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
from openai import OpenAI


st.set_page_config(
    page_title="Alcohood AI Demand & Pricing Radar",
    layout="wide"
)

st.title("🍾 Alcohood AI Demand & Pricing Radar")
st.caption(
    "Google Ads Search Terms • AI Product Discovery • Product Page Filtering • Competitor Price Check"
)


def get_openai_client():
    try:
        return OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    except Exception:
        return None


client = get_openai_client()


ALCOHOOD_SEARCH_TEMPLATE = "https://www.alcohood.com/search?q={query}"

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


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/125 Safari/537.36"
    ),
    "Accept-Language": "en-HK,en;q=0.9,zh-HK;q=0.8",
}


BAD_URL_KEYWORDS = [
    "delivery",
    "shipping",
    "cart",
    "checkout",
    "account",
    "login",
    "register",
    "wishlist",
    "pages",
    "page/",
    "blogs",
    "blog",
    "news",
    "promotion",
    "promotions",
    "events",
    "service",
    "membership",
    "terms",
    "privacy",
    "contact",
    "about",
    "faq",
    "collection/all",
    "collections/all",
]


GOOD_URL_KEYWORDS = [
    "/products/",
    "/product/",
    "/goodsdetail/",
    "/goodsDetail/",
    "/item/",
    "/p/",
]


STOPWORDS = {
    "hong",
    "kong",
    "hk",
    "hkd",
    "price",
    "wine",
    "whisky",
    "whiskey",
    "sake",
    "gin",
    "champagne",
    "cognac",
    "brandy",
    "tequila",
    "liqueur",
    "online",
    "shop",
    "buy",
    "700ml",
    "720ml",
    "750ml",
    "1000ml",
    "1l",
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
    return template.replace("{query}", urllib.parse.quote_plus(str(query)))


def normalize_text(text):
    if not text:
        return ""

    text = str(text).lower()
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def important_tokens(query):
    text = normalize_text(query)
    tokens = []

    for token in text.split():
        if token in STOPWORDS:
            continue
        if len(token) <= 1:
            continue
        tokens.append(token)

    return tokens


def product_name_match_score(query, title, url=""):
    tokens = important_tokens(query)

    if not tokens:
        return 0

    combined = normalize_text(f"{title} {url}")
    matched = 0

    for token in tokens:
        if token in combined:
            matched += 1

    return matched / len(tokens)


def is_bad_url(url):
    lowered = str(url).lower()
    return any(keyword.lower() in lowered for keyword in BAD_URL_KEYWORDS)


def is_likely_product_url(url):
    lowered = str(url).lower()

    if is_bad_url(lowered):
        return False

    return any(keyword.lower() in lowered for keyword in GOOD_URL_KEYWORDS)


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

                if isinstance(offers, dict) and offers.get("price"):
                    return float(str(offers.get("price")).replace(",", ""))

                if isinstance(offers, list):
                    for offer in offers:
                        if offer.get("price"):
                            return float(str(offer.get("price")).replace(",", ""))

        except Exception:
            continue

    return None


def extract_meta_title(soup, fallback_url):
    title_candidates = []

    if soup.title and soup.title.string:
        title_candidates.append(soup.title.string.strip())

    meta_properties = [
        ("property", "og:title"),
        ("name", "title"),
        ("property", "twitter:title"),
    ]

    for attr, value in meta_properties:
        tag = soup.find("meta", attrs={attr: value})
        if tag and tag.get("content"):
            title_candidates.append(tag.get("content").strip())

    for title in title_candidates:
        if title:
            return title

    return fallback_url


def extract_links_from_search_page(html, base_url, allowed_domain=None):
    soup = BeautifulSoup(html, "html.parser")
    parsed_base = urllib.parse.urlparse(base_url)
    base_domain = parsed_base.netloc
    links = []

    for a in soup.find_all("a", href=True):
        href = a["href"]

        if href.startswith("/"):
            href = f"{parsed_base.scheme}://{base_domain}{href}"

        if not href.startswith("http"):
            continue

        lowered = href.lower()

        if allowed_domain and allowed_domain not in lowered:
            continue

        if is_bad_url(lowered):
            continue

        links.append(href)

    unique_links = list(dict.fromkeys(links))

    product_links = [
        link for link in unique_links
        if is_likely_product_url(link)
    ]

    if product_links:
        return product_links[:10]

    return unique_links[:10]


def extract_page_info(url, product_query=None):
    html = fetch(url)

    if not html:
        return {
            "price": None,
            "title": "",
            "url": url,
            "match_score": 0,
            "valid_product_page": False,
            "reason": "No response",
        }

    soup = BeautifulSoup(html, "html.parser")
    title = extract_meta_title(soup, url)
    page_text = soup.get_text(" ", strip=True)

    json_price = extract_json_ld_price(soup)
    text_price = money_to_float(page_text)
    price = json_price if json_price else text_price

    match_score = product_name_match_score(product_query or "", title, url)
    valid_product_page = is_likely_product_url(url)

    if product_query and match_score < 0.5:
        return {
            "price": None,
            "title": title,
            "url": url,
            "match_score": match_score,
            "valid_product_page": valid_product_page,
            "reason": "Product name does not match search term",
        }

    if not valid_product_page:
        return {
            "price": None,
            "title": title,
            "url": url,
            "match_score": match_score,
            "valid_product_page": False,
            "reason": "Not a valid product URL",
        }

    if not price:
        return {
            "price": None,
            "title": title,
            "url": url,
            "match_score": match_score,
            "valid_product_page": valid_product_page,
            "reason": "No price found on product page",
        }

    return {
        "price": price,
        "title": title,
        "url": url,
        "match_score": match_score,
        "valid_product_page": valid_product_page,
        "reason": "Valid product price found",
    }


def search_product_from_site(product_query, search_template, allowed_domain=None):
    search_url = build_search_url(search_template, product_query)
    html = fetch(search_url)
    debug_rows = []

    if not html:
        return {
            "title": "Search page blocked / no response",
            "price": None,
            "url": search_url,
            "match_score": 0,
            "reason": "Search page blocked / no response",
            "debug": debug_rows,
        }

    links = extract_links_from_search_page(
        html,
        search_url,
        allowed_domain=allowed_domain,
    )

    best_valid = None

    for link in links:
        result = extract_page_info(
            link,
            product_query=product_query,
        )

        debug_rows.append(
            {
                "Candidate URL": link,
                "Title": result.get("title"),
                "Price": result.get("price"),
                "Match Score": result.get("match_score"),
                "Valid Product Page": result.get("valid_product_page"),
                "Reason": result.get("reason"),
            }
        )

        if result.get("price"):
            best_valid = result
            break

    if best_valid:
        return {
            "title": best_valid["title"],
            "price": best_valid["price"],
            "url": best_valid["url"],
            "match_score": best_valid["match_score"],
            "reason": best_valid["reason"],
            "debug": debug_rows,
        }

    return {
        "title": "Not found",
        "price": None,
        "url": search_url,
        "match_score": 0,
        "reason": "No valid product price found",
        "debug": debug_rows,
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
        "alcohood_match_score": result["match_score"],
        "alcohood_reason": result["reason"],
        "debug": result["debug"],
    }


def search_competitor_product(product_query, competitor_name):
    template = COMPETITOR_SEARCH_URLS[competitor_name]
    domain = urllib.parse.urlparse(template).netloc.lower()

    result = search_product_from_site(
        product_query,
        template,
        allowed_domain=domain,
    )

    return {
        "competitor_name": competitor_name,
        "competitor_title": result["title"],
        "competitor_price": result["price"],
        "competitor_url": result["url"],
        "competitor_match_score": result["match_score"],
        "competitor_reason": result["reason"],
        "debug": result["debug"],
    }


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
        return {}


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
            messages=[{"role": "user", "content": prompt}],
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
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )

        data = safe_json_loads(response.choices[0].message.content)

        same_sku = bool(data.get("same_sku", False))
        confidence = int(data.get("confidence", 0) or 0)

        if same_sku and confidence >= 80:
            if alcohood_price > competitor_price:
                ai_action = "Lower Price"
                ai_suggested_price = competitor_price - 1
            else:
                ai_action = "Competitive"
                ai_suggested_price = alcohood_price
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


def find_column(df, possible_names):
    lower_map = {str(col).lower().strip(): col for col in df.columns}

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


def clean_number(value):
    if pd.isna(value):
        return 0

    text = str(value)
    text = text.replace(",", "")
    text = text.replace("HK$", "")
    text = text.replace("$", "")
    text = text.replace("%", "")
    text = text.strip()

    number_match = re.search(r"-?\d+(?:\.\d+)?", text)

    if not number_match:
        return 0

    try:
        return float(number_match.group(0))
    except Exception:
        return 0


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


def classify_ads_terms(ads_df, max_terms):
    rows = []

    working_df = ads_df.sort_values(by="Clicks", ascending=False).head(max_terms)

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

        time.sleep(0.3)

    return pd.DataFrame(rows)


def build_price_radar(product_df, selected_competitors):
    main_rows = []
    detail_rows = []
    debug_rows = []

    product_rows = product_df[
        product_df["AI Type"].isin(["PRODUCT", "BRAND", "GENERIC"])
    ]

    for _, row in product_rows.iterrows():
        search_term = row["Search Term"]

        if row["AI Type"] == "PRODUCT" and row["Normalized Product"]:
            product_query = row["Normalized Product"]
        else:
            product_query = search_term

        own = alcohood_search(product_query)
        own_price = own.get("alcohood_price")

        for debug in own.get("debug", []):
            debug_rows.append(
                {
                    "Site": "Alcohood",
                    "Search Term": search_term,
                    "Product Query": product_query,
                    **debug,
                }
            )

        competitor_results = []

        for competitor_name in selected_competitors:
            result = search_competitor_product(product_query, competitor_name)
            competitor_results.append(result)

            for debug in result.get("debug", []):
                debug_rows.append(
                    {
                        "Site": competitor_name,
                        "Search Term": search_term,
                        "Product Query": product_query,
                        **debug,
                    }
                )

            detail_rows.append(
                {
                    "Date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "Search Term": search_term,
                    "Product Query": product_query,
                    "Competitor": result.get("competitor_name"),
                    "Competitor Product": result.get("competitor_title"),
                    "Competitor Price": result.get("competitor_price"),
                    "Competitor URL": result.get("competitor_url"),
                    "Match Score": result.get("competitor_match_score"),
                    "Reason": result.get("competitor_reason"),
                }
            )

            time.sleep(0.4)

        valid_competitors = [
            item for item in competitor_results if item.get("competitor_price")
        ]

        cheapest = (
            sorted(valid_competitors, key=lambda x: x["competitor_price"])[0]
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
                status = "🟠 Lower Price"
                suggested_price = competitor_price - 1
            else:
                status = "🟢 Competitive"
                suggested_price = own_price

        elif competitor_price and not own_price:
            difference = ""
            suggested_price = ""
            status = "🟡 Consider Listing"

        elif not competitor_price and not own_price:
            difference = ""
            suggested_price = ""
            status = "🔵 Market Demand Only"

        else:
            difference = ""
            suggested_price = ""
            status = "🔴 No Reliable Match"

        if own_price and competitor_price:
            ai_match = ai_sku_match(
                product_query,
                own.get("alcohood_title"),
                own_price,
                competitor_name,
                competitor_title,
                competitor_price,
            )
        else:
            ai_match = {
                "same_sku": "",
                "confidence": "",
                "reason": "",
                "ai_action": "",
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
                "Alcohood Product": own.get("alcohood_title"),
                "Alcohood Price": own_price,
                "Alcohood URL": own.get("alcohood_url"),
                "Alcohood Match Score": own.get("alcohood_match_score"),
                "Alcohood Reason": own.get("alcohood_reason"),
                "Cheapest Competitor": competitor_name,
                "Competitor Product": competitor_title,
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

        time.sleep(0.4)

    return pd.DataFrame(main_rows), pd.DataFrame(detail_rows), pd.DataFrame(debug_rows)


with st.sidebar:
    st.header("Settings")

    uploaded_file = st.file_uploader(
        "Upload Google Ads Search Terms CSV",
        type=["csv", "txt"],
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

    max_terms = st.slider(
        "Max search terms to analyse",
        5,
        100,
        20,
    )

    run_classification = st.button(
        "1️⃣ Analyse Google Ads Terms",
        type="primary",
    )

    run_price_radar = st.button(
        "2️⃣ Run Price & Listing Radar",
    )

    test_ai = st.button(
        "Test OpenAI Connection",
    )


st.info(
    "Upload your Google Ads Search Terms CSV. AI will classify real customer searches into PRODUCT, BRAND, COMPETITOR, GENERIC, or IGNORE. "
    "This version filters out non-product pages such as delivery, shipping, collections, blog, and cart pages before using any price."
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


if uploaded_file:
    ads_df = load_google_ads_csv(uploaded_file)

    if not ads_df.empty:
        st.subheader("Uploaded Google Ads Search Terms")
        st.dataframe(ads_df.head(50), width="stretch")

        if run_classification:
            with st.spinner("AI is classifying Google Ads search terms..."):
                classified_df = classify_ads_terms(ads_df, max_terms)

            st.session_state["classified_df"] = classified_df

        if "classified_df" in st.session_state:
            classified_df = st.session_state["classified_df"]

            st.subheader("AI Search Term Classification")

            st.dataframe(classified_df, width="stretch")

            st.download_button(
                "Download AI Classification CSV",
                classified_df.to_csv(index=False).encode("utf-8-sig"),
                "alcohood_google_ads_ai_classification.csv",
                "text/csv",
            )

            c1, c2, c3, c4, c5 = st.columns(5)

            c1.metric("PRODUCT", int((classified_df["AI Type"] == "PRODUCT").sum()))
            c2.metric("BRAND", int((classified_df["AI Type"] == "BRAND").sum()))
            c3.metric("COMPETITOR", int((classified_df["AI Type"] == "COMPETITOR").sum()))
            c4.metric("GENERIC", int((classified_df["AI Type"] == "GENERIC").sum()))
            c5.metric("IGNORE", int((classified_df["AI Type"] == "IGNORE").sum()))

            st.subheader("Product Terms Selected for Price Radar")

            product_terms_df = classified_df[
                classified_df["AI Type"].isin(["PRODUCT", "BRAND", "GENERIC"])
            ]

            st.dataframe(product_terms_df, width="stretch")

            if run_price_radar:
                with st.spinner("Searching Alcohood and competitors with product-page filtering..."):
                    radar_df, detail_df, debug_df = build_price_radar(
                        product_terms_df,
                        selected_competitors,
                    )

                st.session_state["radar_df"] = radar_df
                st.session_state["detail_df"] = detail_df
                st.session_state["debug_df"] = debug_df

        if "radar_df" in st.session_state:
            radar_df = st.session_state["radar_df"]
            detail_df = st.session_state["detail_df"]
            debug_df = st.session_state["debug_df"]

            st.success("Price & Listing Radar completed")

            k1, k2, k3, k4 = st.columns(4)

            k1.metric("Items Checked", len(radar_df))
            k2.metric("Lower Price", int((radar_df["Status"] == "🟠 Lower Price").sum()))
            k3.metric("Consider Listing", int((radar_df["Status"] == "🟡 Consider Listing").sum()))
            k4.metric("Market Demand Only", int((radar_df["Status"] == "🔵 Market Demand Only").sum()))

            st.subheader("Price Actions / Review Needed")

            price_actions_df = radar_df[
                radar_df["Status"].isin(
                    [
                        "🟠 Lower Price",
                        "🟢 Competitive",
                        "🔴 No Reliable Match",
                    ]
                )
            ]

            st.dataframe(price_actions_df, width="stretch")

            st.subheader("All Items Needing Review")

            review_df = radar_df[
                radar_df["Status"].isin(
                    [
                        "🔴 No Reliable Match",
                        "🔵 Market Demand Only",
                        "🟡 Consider Listing",
                    ]
                )
            ]

            st.dataframe(review_df, width="stretch")

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

            st.subheader("Full Radar Dashboard")
            st.dataframe(radar_df, width="stretch")

            st.download_button(
                "Download Full Radar CSV",
                radar_df.to_csv(index=False).encode("utf-8-sig"),
                "alcohood_ai_demand_pricing_radar.csv",
                "text/csv",
            )

            st.subheader("Competitor Detail Report")
            st.dataframe(detail_df, width="stretch")

            st.download_button(
                "Download Competitor Detail CSV",
                detail_df.to_csv(index=False).encode("utf-8-sig"),
                "alcohood_competitor_detail_report.csv",
                "text/csv",
            )

            st.subheader("Debug: Candidate Pages Checked")
            st.caption(
                "Use this table to see why a page was rejected, e.g. not product URL, no price found, or product name mismatch."
            )

            st.dataframe(debug_df, width="stretch")

            st.download_button(
                "Download Debug CSV",
                debug_df.to_csv(index=False).encode("utf-8-sig"),
                "alcohood_debug_candidate_pages.csv",
                "text/csv",
            )

else:
    st.subheader("How to use")
    st.write(
        "1. Export Google Ads Search Terms CSV. "
        "2. Upload the CSV here. "
        "3. Click 1️⃣ Analyse Google Ads Terms. "
        "4. Review AI classification. "
        "5. Click 2️⃣ Run Price & Listing Radar. "
        "6. Check Price Actions / Review Needed, Listing Opportunities, and Debug table."
    )
