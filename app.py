import re, time, urllib.parse
from datetime import datetime
import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup

st.set_page_config(page_title='Alcohood AI Pricing Monitor', layout='wide')
st.title('Alcohood AI Pricing Monitor')
st.caption('ChatGPT-made no-API prototype: Google Shopping public search + Alcohood public pages. Results depend on what public webpages return.')

CATEGORIES = {
    'Red wine': ['red wine hong kong', 'pinot noir hong kong', 'cabernet sauvignon hong kong', 'bourgogne rouge hong kong'],
    'White wine': ['white wine hong kong', 'chardonnay hong kong', 'sauvignon blanc hong kong', 'riesling hong kong'],
    'Sake': ['Dassai 45 hong kong', 'Kubota Manju hong kong', 'Kamoshibito Kuheiji hong kong', 'Hakkaisan sake hong kong'],
    'Cognac': ['Hennessy VSOP hong kong', 'Martell Cordon Bleu hong kong', 'Remy Martin VSOP hong kong'],
    'Champagne': ['Moet Chandon Brut hong kong', 'Veuve Clicquot hong kong', 'Dom Perignon hong kong'],
    'Gin': ['Roku Gin hong kong', 'Hendricks Gin hong kong', 'Two Moons Gin hong kong', 'NIP Gin hong kong']
}

HEADERS = {'User-Agent':'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/125 Safari/537.36', 'Accept-Language':'en-HK,en;q=0.9'}

@st.cache_data(ttl=3600)
def fetch(url):
    try:
        r=requests.get(url, headers=HEADERS, timeout=15)
        return r.text if r.status_code==200 else ''
    except Exception:
        return ''

def money_to_float(text):
    if not text: return None
    m=re.search(r'(?:HK\$|HKD|\$)\s*([0-9][0-9,]*(?:\.\d+)?)', text, re.I)
    if not m: return None
    return float(m.group(1).replace(',',''))

def shopping_search(query, max_results=8):
    url='https://www.google.com/search?udm=28&hl=en-HK&gl=HK&q='+urllib.parse.quote(query)
    html=fetch(url)
    soup=BeautifulSoup(html,'html.parser')
    results=[]
    text=soup.get_text(' ', strip=True)
    # Fallback extraction from visible snippets
    price_matches=list(re.finditer(r'(HK\$|HKD|\$)\s*[0-9][0-9,]*(?:\.\d+)?', text))
    for pm in price_matches[:max_results]:
        start=max(0, pm.start()-140); end=min(len(text), pm.end()+180)
        snippet=text[start:end]
        price=money_to_float(pm.group(0))
        if price:
            results.append({'query':query,'competitor_title':snippet[:220],'competitor_price':price,'competitor_url':url})
    return results

def alcohood_search(query):
    url='https://www.google.com/search?hl=en-HK&gl=HK&q=site%3Aalcohood.com+'+urllib.parse.quote(query)
    html=fetch(url)
    soup=BeautifulSoup(html,'html.parser')
    links=[]
    for a in soup.find_all('a', href=True):
        href=a['href']
        if 'alcohood.com' in href and '/url?q=' in href:
            href=urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get('q',[''])[0]
        if 'alcohood.com' in href and href.startswith('http'):
            links.append(href)
    links=list(dict.fromkeys(links))[:3]
    for link in links:
        html2=fetch(link)
        price=money_to_float(BeautifulSoup(html2,'html.parser').get_text(' ', strip=True))
        title=BeautifulSoup(html2,'html.parser').title.string if BeautifulSoup(html2,'html.parser').title else query
        if price:
            return {'alcohood_title':title,'alcohood_price':price,'alcohood_url':link}
    return {'alcohood_title':'Not found','alcohood_price':None,'alcohood_url':''}

def build_report(selected_categories, limit):
    rows=[]
    for cat in selected_categories:
        for q in CATEGORIES[cat][:limit]:
            comp=shopping_search(q, 5)
            comp_sorted=sorted([c for c in comp if c['competitor_price']], key=lambda x:x['competitor_price'])
            cheapest=comp_sorted[0] if comp_sorted else {}
            own=alcohood_search(q)
            own_price=own.get('alcohood_price')
            comp_price=cheapest.get('competitor_price')
            if own_price and comp_price:
                diff=own_price-comp_price
                suggested=comp_price-1 if diff>0 else own_price
                status='Lower Price' if diff>0 else 'Competitive'
            elif comp_price and not own_price:
                diff=''; suggested=''; status='Consider Listing / Alcohood not found'
            else:
                diff=''; suggested=''; status='No reliable match'
            rows.append({
                'Date': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'Category': cat,
                'Search / Trend Candidate': q,
                'Alcohood Product': own.get('alcohood_title'),
                'Alcohood Price': own_price,
                'Alcohood URL': own.get('alcohood_url'),
                'Cheapest Competitor Snippet': cheapest.get('competitor_title',''),
                'Competitor Price': comp_price,
                'Competitor Link': cheapest.get('competitor_url',''),
                'Difference': diff,
                'Suggested Price': suggested,
                'Status': status
            })
            time.sleep(1)
    return pd.DataFrame(rows)

with st.sidebar:
    st.header('Settings')
    cats=st.multiselect('Categories', list(CATEGORIES.keys()), default=list(CATEGORIES.keys()))
    limit=st.slider('Candidates per category', 1, 4, 2)
    run=st.button('Run price monitor', type='primary')

st.info('第一版不需要你設定 API。按 Run 後會用公開 Google Shopping 搜尋頁 + Alcohood 公開頁面嘗試比價。Google 有機會封鎖或返回不完整資料，所以狀態會標記 No reliable match。')

if run:
    with st.spinner('Searching public web and building dashboard...'):
        df=build_report(cats, limit)
    st.success('Done')
    k1,k2,k3=st.columns(3)
    k1.metric('Items checked', len(df))
    k2.metric('Need lower price', int((df['Status']=='Lower Price').sum()))
    k3.metric('Consider listing / no own price', int(df['Status'].str.contains('Consider', na=False).sum()))
    st.subheader('Action Needed')
    st.dataframe(df[df['Status'].isin(['Lower Price','Consider Listing / Alcohood not found','No reliable match'])], use_container_width=True)
    st.subheader('Full Dashboard')
    st.dataframe(df, use_container_width=True)
    st.download_button('Download CSV', df.to_csv(index=False).encode('utf-8-sig'), 'alcohood_price_monitor.csv', 'text/csv')
else:
    st.subheader('How to use')
    st.write('1. 左邊選酒類。 2. 按 Run price monitor。 3. 下載 CSV 或直接睇 Action Needed。')
