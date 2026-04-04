import os
import requests
import xml.etree.ElementTree as ET

NTFY_TOPIC = os.environ.get("NTFY_TOPIC")


KEYWORDS = {
    "금리/통화": ["rate", "fed", "interest", "inflation"],
    "에너지": ["oil", "gas", "energy"],
    "중국": ["china"],
    "미국": ["us", "america"],
    "유럽": ["europe", "ecb"],
}


def get_news():
    url = "https://news.google.com/rss/search?q=world+economy&hl=en-US&gl=US&ceid=US:en"
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    root = ET.fromstring(response.content)
    items = root.findall(".//item")

    news_list = []
    for item in items[:15]:
        title_elem = item.find("title")
        title = title_elem.text.strip().lower()

        news_list.append(title)

    return news_list


def categorize(news_list):
    result = {k: [] for k in KEYWORDS.keys()}

    for title in news_list:
        for category, words in KEYWORDS.items():
            if any(word in title for word in words):
                result[category].append(title)
                break

    return result


def make_summary(categorized):
    lines = ["📊 세계경제 핵심 브리핑"]

    for category, items in categorized.items():
        if items:
            lines.append(f"\n[{category}]")
            lines.append(f"- {items[0]}")

    return "\n".join(lines)


def send_push(message):
    url = f"https://ntfy.sh/{NTFY_TOPIC}"
    requests.post(url, data=message.encode("utf-8"), timeout=30)


if __name__ == "__main__":
    news = get_news()
    categorized = categorize(news)
    message = make_summary(categorized)
    send_push(message)
