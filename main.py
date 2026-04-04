import os
import requests
import xml.etree.ElementTree as ET
import traceback

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC")


def get_news():
    print("[1] 뉴스 가져오기 시작")
    url = "https://news.google.com/rss/search?q=world+economy&hl=en-US&gl=US&ceid=US:en"
    response = requests.get(url, timeout=30)
    print(f"[1] 뉴스 응답코드: {response.status_code}")
    response.raise_for_status()

    root = ET.fromstring(response.content)
    items = root.findall(".//item")

    news_list = []
    for item in items[:10]:
        title_elem = item.find("title")
        if title_elem is not None and title_elem.text:
            news_list.append(title_elem.text.strip())

    print(f"[1] 뉴스 개수: {len(news_list)}")
    if news_list:
        print(f"[1] 첫 뉴스: {news_list[0]}")
    return news_list


def summarize(news_list):
    print("[2] 요약 시작")

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
    print(f"[2] Gemini 응답코드: {response.status_code}")
    print(f"[2] Gemini 응답본문: {response.text[:1000]}")
    response.raise_for_status()

    result = response.json()

    try:
        text = result["candidates"][0]["content"]["parts"][0]["text"]
        print("[2] 요약 성공")
        return text
    except Exception:
        raise RuntimeError(f"Gemini 응답 파싱 실패: {result}")


def send_push(message):
    print("[3] 푸시 전송 시작")

    if not NTFY_TOPIC:
        raise ValueError("NTFY_TOPIC이 비어 있습니다.")

    url = f"https://ntfy.sh/{NTFY_TOPIC}"
    response = requests.post(url, data=message.encode("utf-8"), timeout=30)
    print(f"[3] ntfy 응답코드: {response.status_code}")
    print(f"[3] ntfy 응답본문: {response.text[:500]}")
    response.raise_for_status()

    print("[3] 푸시 전송 성공")


if __name__ == "__main__":
    try:
        print("=== 시작 ===")
        print("GEMINI_API_KEY 존재 여부:", bool(GEMINI_API_KEY))
        print("NTFY_TOPIC 존재 여부:", bool(NTFY_TOPIC))

        news = get_news()
        summary = summarize(news)
        print("[요약 결과]")
        print(summary)

        send_push(summary)
        print("=== 완료 ===")

    except Exception as e:
        print("=== 오류 발생 ===")
        print(str(e))
        traceback.print_exc()
        raise
