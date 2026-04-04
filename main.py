import os
import requests
import xml.etree.ElementTree as ET

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC")


def get_news():
    url = "https://news.google.com/rss/search?q=world+economy&hl=en-US&gl=US&ceid=US:en"
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    root = ET.fromstring(response.content)
    items = root.findall(".//item")

    news_list = []
    for item in items[:10]:
        title_elem = item.find("title")
        if title_elem is not None and title_elem.text:
            news_list.append(title_elem.text.strip())

    return news_list


def summarize(news_list):
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY가 비어 있습니다.")

    if not news_list:
        return "오늘 가져온 세계경제 뉴스가 없습니다."

    news_text = "\n".join([f"- {title}" for title in news_list])

    prompt = f"""
아래 세계경제 뉴스 제목들을 바탕으로 한국어로 간단히 정리해줘.

형식:
1. 핵심 3줄 요약
2. 시장 영향 2줄

너무 길지 않게 작성하고, 중복 내용은 합쳐서 정리해.

뉴스 목록:
{news_text}
""".strip()

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ]
    }

    response = requests.post(url, headers=headers, json=payload, timeout=60)
    response.raise_for_status()

    result = response.json()
    print("Gemini 응답:", result)

    try:
        return result["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        raise RuntimeError(f"Gemini 응답 파싱 실패: {result}") from e


def send_push(message):
    if not NTFY_TOPIC:
        raise ValueError("NTFY_TOPIC이 비어 있습니다.")

    url = f"https://ntfy.sh/{NTFY_TOPIC}"
    response = requests.post(url, data=message.encode("utf-8"), timeout=30)
    response.raise_for_status()


if __name__ == "__main__":
    print("시작")
    print("GEMINI_API_KEY 존재 여부:", bool(GEMINI_API_KEY))
    print("NTFY_TOPIC 존재 여부:", bool(NTFY_TOPIC))

    news = get_news()
    print("뉴스 개수:", len(news))
    print("첫 뉴스:", news[0] if news else "없음")

    summary = summarize(news)
    print("요약 결과:", summary)

    send_push(summary)
    print("푸시 전송 완료")
