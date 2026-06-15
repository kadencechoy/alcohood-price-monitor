def load_google_ads_csv(uploaded_file):
    try:
        raw = uploaded_file.getvalue()

        text = raw.decode("utf-8-sig", errors="ignore")
        lines = text.splitlines()

        header_index = None

        for i, line in enumerate(lines):
            if "搜尋字詞" in line and "點擊次數" in line:
                header_index = i
                break

            if "Search term" in line and "Clicks" in line:
                header_index = i
                break

        if header_index is None:
            st.error("Cannot find Google Ads header row. Please export the Search Terms report as CSV.")
            return pd.DataFrame()

        cleaned_text = "\n".join(lines[header_index:])

        from io import StringIO
        df = pd.read_csv(StringIO(cleaned_text))

    except Exception as error:
        st.error(f"Failed to read CSV: {error}")
        return pd.DataFrame()

    search_col = find_column(df, [
        "Search term",
        "Search Terms",
        "搜尋字詞",
        "搜索字詞",
    ])

    clicks_col = find_column(df, [
        "Clicks",
        "點擊次數",
        "點擊",
    ])

    cost_col = find_column(df, [
        "Cost",
        "成本",
    ])

    impressions_col = find_column(df, [
        "Impressions",
        "展示",
        "展示次數",
    ])

    if not search_col:
        st.error("Cannot find Search Term column. Please check your CSV export.")
        return pd.DataFrame()

    clean_df = pd.DataFrame()
    clean_df["Search Term"] = df[search_col].astype(str)

    clean_df["Clicks"] = (
        pd.to_numeric(df[clicks_col], errors="coerce").fillna(0)
        if clicks_col
        else 0
    )

    clean_df["Cost"] = df[cost_col] if cost_col else ""

    clean_df["Impressions"] = (
        pd.to_numeric(df[impressions_col], errors="coerce").fillna(0)
        if impressions_col
        else 0
    )

    clean_df = clean_df.dropna(subset=["Search Term"])
    clean_df = clean_df[clean_df["Search Term"].str.strip() != ""]
    clean_df = clean_df.drop_duplicates(subset=["Search Term"])

    return clean_df
