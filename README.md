# Alcohood AI Pricing Monitor

No-API prototype dashboard.

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```

## What it does
- Uses public Google Shopping search (`udm=28`) for competitor snippets and prices.
- Searches public Alcohood pages via Google site search.
- Compares Alcohood price with the cheapest competitor price.
- If Alcohood is more expensive, suggested price = competitor price - HK$1.

## Important limitation
Google Shopping / Trends are dynamic and may block automated requests. For a business-grade dashboard, connect a proper search API later.
