import re
import time
from io import BytesIO

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup


def clean_text(text: str) -> str:
    text = " ".join(text.split())

    # вырезаем большие JSON-похожие куски: [{...}] или {...}
    text = re.sub(r"\[\{.*?\}\]", " ", text, flags=re.DOTALL)
    text = re.sub(r"\{.*?\}", " ", text, flags=re.DOTALL)

    # убираем юникод-экранирование типа \u0418\u043c\u044f
    text = re.sub(r"\\u[0-9a-fA-F]{4}", " ", text)

    # убираем тех. ключи, которые часто встречаются в мусорном JSON
    bad_patterns = [
        r"\blid\b", r"\bli_type\b", r"\bli_ph\b", r"\bli_req\b", r"\bli_nm\b",
        r"\bloff\b", r"\bls\b", r"\bli_name\b", r"\bli_label\b"
    ]
    text = re.sub("|".join(bad_patterns), " ", text, flags=re.IGNORECASE)

    text = " ".join(text.split()).strip()
    return text


def get_title(soup: BeautifulSoup) -> str:
    if soup.title and soup.title.get_text(strip=True):
        return soup.title.get_text(strip=True)
    return ""


def get_description(soup: BeautifulSoup) -> str:
    # обычный meta description
    tag = soup.find("meta", attrs={"name": "description"})
    if tag and tag.get("content"):
        return tag.get("content").strip()

    # og:description (часто на сайтах)
    tag = soup.find("meta", attrs={"property": "og:description"})
    if tag and tag.get("content"):
        return tag.get("content").strip()

    return ""


def get_h1(soup: BeautifulSoup) -> str:
    h1 = soup.find("h1")
    if h1:
        txt = h1.get_text(separator=" ", strip=True)
        txt = " ".join(txt.split()).strip()
        return txt
    return ""


def extract_page_data(url: str, timeout=25) -> dict:
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            )
        }

        r = requests.get(url, headers=headers, timeout=timeout)
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "lxml")

        title = get_title(soup)
        description = get_description(soup)
        h1 = get_h1(soup)

        # ❌ удаляем мусорные теги
        for tag in soup([
            "script", "style", "noscript", "template",
            "svg", "canvas", "iframe", "form",
            "header", "footer", "nav", "aside"
        ]):
            tag.decompose()

        body = soup.body if soup.body else soup

        # иногда мусор лежит в элементах type="application/json"
        for tag in body.find_all(attrs={"type": "application/json"}):
            tag.decompose()

        text = body.get_text(separator=" ", strip=True)
        text = clean_text(text)

        if not text or len(text) < 30:
            text = "ERROR: пустой или слишком короткий текст (возможно сайт грузится через JS)"

        return {
            "TITLE": title,
            "DESCRIPTION": description,
            "H1": h1,
            "TEXT": text
        }

    except Exception as e:
        return {
            "TITLE": "",
            "DESCRIPTION": "",
            "H1": "",
            "TEXT": f"ERROR: {str(e)}"
        }


st.set_page_config(page_title="URL → Title/Desc/H1/Text → Excel", layout="centered")
st.title("Парсер URL из Excel (тайтл + дескрипшен + h1 + текст)")

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
        rows = []
        progress = st.progress(0)
        status = st.empty()

        for i, url in enumerate(urls, start=1):
            status.write(f"Парсим {i}/{len(urls)}: {url}")

            data = extract_page_data(url)
            rows.append({
                "URL": url,
                "TITLE": data["TITLE"],
                "DESCRIPTION": data["DESCRIPTION"],
                "H1": data["H1"],
                "TEXT": data["TEXT"]
            })

            progress.progress(i / len(urls))
            time.sleep(delay)

        out_df = pd.DataFrame(rows)

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
