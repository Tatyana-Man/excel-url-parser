import pandas as pd
import requests
from bs4 import BeautifulSoup
import time
import streamlit as st
from io import BytesIO


def extract_main_text(url: str, timeout=20) -> str:
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            )
        }
        r = requests.get(url, headers=headers, timeout=timeout)
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "lxml")
        main_tag = soup.find("main")

        if not main_tag:
            return "ERROR: <main> tag not found"

        for tag in main_tag(["script", "style", "noscript"]):
            tag.decompose()

        text = main_tag.get_text(separator=" ", strip=True)
        text = " ".join(text.split())
        return text

    except Exception as e:
        return f"ERROR: {str(e)}"


st.set_page_config(page_title="URL → <main> text → Excel", layout="centered")
st.title("Парсер URL из Excel (только <main>)")

uploaded_file = st.file_uploader("Загрузи XLS/XLSX файл (URL в первом столбце)", type=["xls", "xlsx"])

delay = st.slider("Пауза между запросами (сек)", 0.0, 5.0, 1.0, 0.5)

if uploaded_file is not None:
    df = pd.read_excel(uploaded_file, header=None)
    urls = df.iloc[:, 0].dropna().astype(str).tolist()

    st.write(f"Найдено URL: **{len(urls)}**")

    if st.button("Start"):
        results = []
        progress = st.progress(0)
        status = st.empty()

        for i, url in enumerate(urls, start=1):
            status.write(f"Парсим {i}/{len(urls)}: {url}")
            text = extract_main_text(url)
            results.append(text)

            progress.progress(i / len(urls))
            time.sleep(delay)

        out_df = pd.DataFrame({"URL": urls, "MAIN_TEXT": results})

        buffer = BytesIO()
        out_df.to_excel(buffer, index=False)
        buffer.seek(0)

        st.success("Готово ✅")
        st.download_button(
            label="Скачать output.xlsx",
            data=buffer,
            file_name="output.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
