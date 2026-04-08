import os
import requests
import xml.etree.ElementTree as ET
import html

NTFY_TOPIC = os.environ.get("NTFY_TOPIC")

KEYWORDS = {
    "금리/통화": ["rate", "fed", "interest", "inflation", "central bank"],
    "에너지": ["oil", "gas", "energy", "crude"],
    "중국": ["china", "beijing"],
    "미국": ["u.s.", "us ", "america", "federal reserve"],
    "유럽": ["europe", "ecb", "eu ", "eurozone"],
}


def get_news():
    url = "https://news.google.com/rss/search?q=world+economy&hl=en-US&gl=US&ceid=US:en"
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    root = ET.fromstring(response.content)
    items = root.findall(".//item")

    news_list = []
    for item in items[:10]:
        title_elem = item.find("title")
        link_elem = item.find("link")
        desc_elem = item.find("description")

        title = title_elem.text.strip() if title_elem is not None and title_elem.text else ""
        link = link_elem.text.strip() if link_elem is not None and link_elem.text else ""
        desc = desc_elem.text.strip() if desc_elem is not None and desc_elem.text else ""

        desc = html.unescape(desc)
        desc = desc.replace("<b>", "").replace("</b>", "")
        desc = desc.replace("<br>", " ").replace("<br/>", " ").replace("<br />", " ")

        if title:
            news_list.append({
                "title": title,
                "link": link,
                "desc": desc
            })

    return news_list


def categorize_article(title):
    t = title.lower()
    for category, words in KEYWORDS.items():
        if any(word in t for word in words):
            return category
    return "기타"


def make_summary(news_list):
    if not news_list:
        return "오늘 가져온 세계경제 뉴스가 없습니다."

    lines = ["📊 세계경제 실제 뉴스 브리핑"]

    used_categories = set()

    for article in news_list:
        category = categorize_article(article["title"])

        if category not in used_categories:
            lines.append(f"\n[{category}]")
            used_categories.add(category)

        lines.append(f"- {article['title']}")
        if article["link"]:
            lines.append(article["link"])

    return "\n".join(lines[:30])  # 너무 길어지는 것 방지


def send_push(message):
    if not NTFY_TOPIC:
        raise ValueError("NTFY_TOPIC이 비어 있습니다.")

    url = f"https://ntfy.sh/{NTFY_TOPIC}"
    response = requests.post(url, data=message.encode("utf-8"), timeout=30)
    response.raise_for_status()


if __name__ == "__main__":
    news = get_news()
    message = make_summary(news)
    send_push(message)
    print("푸시 전송 완료")
