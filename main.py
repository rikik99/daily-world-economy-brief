import os
import requests
import xml.etree.ElementTree as ET

NTFY_TOPIC = os.environ.get("NTFY_TOPIC")


def get_news():
    url = "https://news.google.com/rss/search?q=world+economy&hl=en-US&gl=US&ceid=US:en"
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    root = ET.fromstring(response.content)
    items = root.findall(".//item")

    news_list = []
    for item in items[:5]:
        title_elem = item.find("title")
        link_elem = item.find("link")

        title = title_elem.text.strip() if title_elem is not None and title_elem.text else ""
        link = link_elem.text.strip() if link_elem is not None and link_elem.text else ""

        if title:
            news_list.append((title, link))

    return news_list


def make_summary(news_list):
    if not news_list:
        return "오늘 가져온 세계경제 뉴스가 없습니다."

    lines = ["[오늘의 세계경제 뉴스]"]
    for i, (title, link) in enumerate(news_list, start=1):
        lines.append(f"{i}. {title}")
        if link:
            lines.append(link)

    return "\n".join(lines)


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
