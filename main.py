import os
import requests
import xml.etree.ElementTree as ET
import html
import re
from deep_translator import GoogleTranslator

NTFY_TOPIC = os.environ.get("NTFY_TOPIC")

KEYWORDS = {
    "금리/통화": ["rate", "fed", "interest", "inflation", "central bank", "bond", "cpi"],
    "에너지": ["oil", "gas", "energy", "crude", "opec"],
    "중국": ["china", "beijing", "yuan"],
    "미국": ["u.s.", "us ", "america", "federal reserve", "treasury"],
    "유럽": ["europe", "ecb", "eu ", "eurozone", "boe"],
    "무역/공급망": ["trade", "tariff", "shipping", "supply chain", "export", "import"],
}

CATEGORY_ORDER = ["금리/통화", "에너지", "중국", "미국", "유럽", "무역/공급망", "기타"]


def clean_html(text):
    text = html.unescape(text or "")
    text = re.sub(r"<.*?>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_summary(desc):
    desc = clean_html(desc)
    if not desc:
        return ""
    parts = re.split(r"[.?!]", desc)
    first = parts[0].strip()
    return first if first else desc[:120]


def translate_text(text):
    text = (text or "").strip()
    if not text:
        return ""
    try:
        translated = GoogleTranslator(source="auto", target="ko").translate(text)
        translated = (translated or "").strip()
        return translated if translated else text
    except Exception:
        return text


def get_news():
    url = "https://news.google.com/rss/search?q=world+economy&hl=en-US&gl=US&ceid=US:en"
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    root = ET.fromstring(response.content)
    items = root.findall(".//item")

    news_list = []
    for item in items[:20]:
        title_elem = item.find("title")
        link_elem = item.find("link")
        desc_elem = item.find("description")

        title = title_elem.text.strip() if title_elem is not None and title_elem.text else ""
        link = link_elem.text.strip() if link_elem is not None and link_elem.text else ""
        desc = desc_elem.text if desc_elem is not None and desc_elem.text else ""

        if title:
            news_list.append({
                "title": title,
                "link": link,
                "summary": extract_summary(desc)
            })

    return news_list


def categorize_article(title):
    t = title.lower()
    for category, words in KEYWORDS.items():
        if any(word in t for word in words):
            return category
    return "기타"


def categorize_news(news_list):
    grouped = {category: [] for category in CATEGORY_ORDER}
    for article in news_list:
        grouped[categorize_article(article["title"])].append(article)
    return grouped


def make_summary(grouped):
    lines = ["📊 세계경제 핵심 브리핑", "번역 + 요약"]

    for category in CATEGORY_ORDER:
        articles = grouped.get(category, [])
        if not articles:
            continue

        lines.append(f"\n[{category}]")

        for idx, article in enumerate(articles[:3], start=1):
            translated_title = translate_text(article["title"])
            translated_summary = translate_text(article["summary"]) if article["summary"] else ""

            final_title = translated_title if translated_title else article["title"]
            lines.append(f"{idx}. {final_title}")

            if translated_summary:
                lines.append(f"→ {translated_summary}")

    message = "\n".join(lines).strip()

    if len(message) > 3500:
        message = message[:3500] + "\n...(이하 생략)"

    if not message:
        message = "오늘의 세계경제 뉴스가 비어 있습니다."

    return message


def send_push(message):
    if not NTFY_TOPIC:
        raise ValueError("NTFY_TOPIC이 비어 있습니다.")

    url = f"https://ntfy.sh/{NTFY_TOPIC}"
    headers = {
        "Title": "세계경제 뉴스 브리핑",
        "Priority": "default",
        "Tags": "chart_with_upwards_trend,newspaper"
    }

    response = requests.post(
        url,
        data=message.encode("utf-8"),
        headers=headers,
        timeout=30
    )
    response.raise_for_status()


if __name__ == "__main__":
    news = get_news()
    grouped = categorize_news(news)
    message = make_summary(grouped)

    print("=== 전송 메시지 시작 ===")
    print(message)
    print("=== 전송 메시지 끝 ===")

    send_push(message)
    print("푸시 전송 완료")
