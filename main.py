import requests
import os
from xml.etree import ElementTree

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC")

# 1. 뉴스 수집 (구글 뉴스 RSS)
def get_news():
    url = "https://news.google.com/rss/search?q=world+economy&hl=en-US&gl=US&ceid=US:en"
    res = requests.get(url)
    root = ElementTree.fromstring(res.content)

    items = root.findall(".//item")
    news_list = []

    for item in items[:10]:
        title = item.find("title").text
        news_list.append(title)

    return news_list

# 2. AI 요약 (Gemini)
def summarize(news_list):
    text = "\n".join(news_list)

    prompt = f"""
아래 세계경제 뉴스 제목들을 한국어로 요약해라.

형식:
1. 핵심 3줄 요약
2. 시장 영향 2줄

뉴스:
{text}
"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={GEMINI_API_KEY}"

    headers = {"Content-Type": "application/json"}

    data = {
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ]
    }

    res = requests.post(url, headers=headers, json=data)
    result = res.json()

    try:
        return result["candidates"][0]["content"]["parts"][0]["text"]
    except:
        return "요약 실패"

# 3. ntfy 푸시 전송
def send_push(message):
    url = f"https://ntfy.sh/{NTFY_TOPIC}"
    requests.post(url, data=message.encode("utf-8"))

if __name__ == "__main__":
    news = get_news()
    summary = summarize(news)
    send_push(summary)
