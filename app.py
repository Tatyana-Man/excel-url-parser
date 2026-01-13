import pandas as pd
import requests
from bs4 import BeautifulSoup
import time
import streamlit as st
from io import BytesIO


def extract_full_text(url: str, timeout=20) -> str:
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

        # удаляем мусор со всей страницы
        for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "aside"]):
            tag.decompose()

        text = soup.get_text(separator=" ", strip=True)
        text = " ".join(text.split())

        if not text:
            return "ERROR: empty text"

        return text

    except Exception as e:
        return f"ERROR: {str(e)}"


st.set_page_config(page_title="URL → full text → Excel", layout="centered")
st.title("Парсер URL из Excel (весь текст страницы)")

uploaded_file = st.file_uploader(
    "Загрузи XLS/XLSX файл (URL в первом столбце)",
    type=["xls", "xlsx"]
)

delay = st.slider("Пауза между запросами (сек)", 0.0, 5.0, 1.0, 0.5)

if uploaded_file is not None:
    df = pd.read_excel(uploaded_file, header=None)

    if df.shape[1] == 0:
        st.error("Файл пустой или не удалось прочитать первый столбец.")
        st.stop()

    urls = df.iloc[:, 0].dropna().astype(str).tolist()

    if not urls:
        st.warning("В первом столбце не найдено URL.")
        st.stop()

    st.write(f"Найдено URL: **{len(urls)}**")

    if st.button("Start"):
        results = []
        progress = st.progress(0)
        status = st.empty()

        for i, url in enumerate(urls, start=1):
            status.write(f"Парсим {i}/{len(urls)}: {url}")
            text = extract_full_text(url)
            results.append(text)

            progress.progress(i / len(urls))
            time.sleep(delay)

        out_df = pd.DataFrame({
            "URL": urls,
            "TEXT": results
        })

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
