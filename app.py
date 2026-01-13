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


def safe_join(parts, sep=" | "):
    parts = [str(p).strip() for p in parts if p and str(p).strip()]
    return sep.join(parts)


def get_title(soup: BeautifulSoup) -> str:
    if soup.title and soup.title.get_text(strip=True):
        return soup.title.get_text(strip=True)
    return ""


def get_description(soup: BeautifulSoup) -> str:
    tag = soup.find("meta", attrs={"name": "description"})
    if tag and tag.get("content"):
        return tag.get("content").strip()

    tag = soup.find("meta", attrs={"property": "og:description"})
    if tag and tag.get("content"):
        return tag.get("content").strip()

    return ""


def get_h1(soup: BeautifulSoup) -> str:
    h1 = soup.find("h1")
    if h1:
        txt = h1.get_text(separator=" ", strip=True)
        return " ".join(txt.split()).strip()
    return ""


def normalize_price_number(raw: str) -> str:
    raw = raw.replace("\xa0", " ")
    raw = raw.replace(",", " ")
    raw = re.sub(r"[^\d ]", "", raw)
    raw = raw.replace(" ", "")
    return raw.strip()


def find_prices_with_context(text: str, context_window: int = 60):
    """
    Возвращает:
    - price_main: первое совпадение
    - prices_found: список цен (строкой через ;)
    - contexts: список "цена + контекст" (строкой через \n)
    """
    if not text:
        return "", "", ""

    t = text.replace("\xa0", " ")
    t = " ".join(t.split())

    patterns = [
        # число + ₽/руб/RUB
        r"(?<!\d)(\d{1,3}(?:[ \u00a0]\d{3})+|\d{4,7})\s*(₽|руб\.?|р\.?|RUB)\b",
        # ₽ + число
        r"(₽)\s*(\d{1,3}(?:[ \u00a0]\d{3})+|\d{4,7})\b",
        # число + (в месяц / мес) (даже без ₽)
        r"(?<!\d)(\d{1,3}(?:[ \u00a0]\d{3})+|\d{3,7})\s*(?:₽|руб\.?|р\.?|RUB)?\s*/?\s*(?:мес\.?|в месяц|в мес)\b",
    ]

    matches = []

    for p in patterns:
        for m in re.finditer(p, t, flags=re.IGNORECASE):
            match_text = m.group(0).strip()

            # вытащим число для фильтра
            groups = [g for g in m.groups() if g]
            number_candidate = None
            for g in groups:
                if re.search(r"\d", g):
                    number_candidate = g
                    break

            if number_candidate:
                num = normalize_price_number(number_candidate)
                if num.isdigit():
                    value = int(num)
                    if 100 <= value <= 2_000_000:
                        start, end = m.span()

                        # контекст вокруг цены
                        left = max(0, start - context_window)
                        right = min(len(t), end + context_window)
                        context = t[left:right].strip()

                        # делаем читаемо
                        context = context.replace(match_text, f"👉 {match_text} 👈")

                        matches.append((match_text, context))

    # убираем дубли, сохраняя порядок
    unique_prices = []
    unique_contexts = []
    seen = set()

    for price, ctx in matches:
        key = price.lower()
        if key not in seen:
            seen.add(key)
            unique_prices.append(price)
            unique_contexts.append(ctx)

    price_main = unique_prices[0] if unique_prices else ""
    prices_found = "; ".join(unique_prices)
    price_contexts = "\n".join(unique_contexts)

    return price_main, prices_found, price_contexts


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

        full_text = safe_join([title, description, h1, text], sep=" | ")

        price_main, prices_found, price_contexts = find_prices_with_context(full_text, context_window=70)

        return {
            "TITLE": title,
            "DESCRIPTION": description,
            "H1": h1,
            "TEXT": text,
            "FULL_TEXT": full_text,
            "PRICE_MAIN": price_main,
            "PRICES_FOUND": prices_found,
            "PRICE_CONTEXTS": price_contexts
        }

    except Exception as e:
        err = f"ERROR: {str(e)}"
        return {
            "TITLE": "",
            "DESCRIPTION": "",
            "H1": "",
            "TEXT": err,
            "FULL_TEXT": err,
            "PRICE_MAIN": "",
            "PRICES_FOUND": "",
            "PRICE_CONTEXTS": ""
        }


st.set_page_config(page_title="URL → контент + цены → Excel", layout="centered")
st.title("Парсер URL из Excel (тайтл + дескрипшен + h1 + текст + цены с контекстом)")

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
                "TEXT": data["TEXT"],
                "FULL_TEXT": data["FULL_TEXT"],
                "PRICE_MAIN": data["PRICE_MAIN"],
                "PRICES_FOUND": data["PRICES_FOUND"],
                "PRICE_CONTEXTS": data["PRICE_CONTEXTS"],
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
