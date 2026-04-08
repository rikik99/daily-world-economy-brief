import os
import requests
import xml.etree.ElementTree as ET
import html
import re

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
    text = html.unescape(text)
    text = re.sub(r"<.*?>", "", text)
    return text.strip()


def extract_summary(desc):
    if not desc:
        return ""

    desc = clean_html(desc)

    # 문장 1개만 추출 (너무 길어지는 것 방지)
    parts = re.split(r"[.?!]", desc)
    return parts[0].strip()


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

        title = title_elem.text.strip() if title_elem is not None else ""
        link = link_elem.text.strip() if link_elem is not None else ""
        desc = desc_elem.text if desc_elem is not None else ""

        summary = extract_summary(desc)

        if title:
            news_list.append({
                "title": title,
                "link": link,
                "summary": summary
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
        category = categorize_article(article["title"])
        grouped[category].append(article)

    return grouped


def make_summary(grouped):
    lines = ["📊 세계경제 핵심 브리핑", "요약 + 주요 뉴스"]

    for category in CATEGORY_ORDER:
        articles = grouped.get(category, [])
        if not articles:
            continue

        lines.append(f"\n[{category}]")

        for idx, article in enumerate(articles[:3], start=1):
            lines.append(f"{idx}. {article['title']}")

            if article["summary"]:
                lines.append(f"→ {article['summary']}")

            if article["link"]:
                lines.append(article["link"])

    return "\n".join(lines[:50])  # 길이 제한


def send_push(message):
    if not NTFY_TOPIC:
        raise ValueError("NTFY_TOPIC이 비어 있습니다.")

    url = f"https://ntfy.sh/{NTFY_TOPIC}"
    response = requests.post(url, data=message.encode("utf-8"), timeout=30)
    response.raise_for_status()


if __name__ == "__main__":
    news = get_news()
    grouped = categorize_news(news)
    message = make_summary(grouped)
    send_push(message)
    print("푸시 전송 완료")
