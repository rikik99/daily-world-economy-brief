import os
import re
import html
import json
import requests
import xml.etree.ElementTree as ET

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC")


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
    return first if first else desc[:180]


def get_news():
    url = "https://news.google.com/rss/search?q=world+economy&hl=en-US&gl=US&ceid=US:en"
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    root = ET.fromstring(response.content)
    items = root.findall(".//item")

    news_list = []
    for item in items[:12]:  # 너무 많이 넣지 말고 12개 정도로 제한
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
                "summary": extract_summary(desc),
            })

    return news_list


def build_prompt(news_list):
    articles = []
    for i, article in enumerate(news_list, start=1):
        articles.append(
            f"[기사 {i}]\n"
            f"제목: {article['title']}\n"
            f"설명: {article['summary']}\n"
        )

    joined = "\n".join(articles)

    prompt = f"""
너는 세계경제 뉴스 브리핑 에디터다.
아래 기사 목록을 읽고, 한국어로 자연스럽고 짧게 요약/번역해라.

규칙:
1. 출력은 한국어로만 작성한다.
2. 어색한 직역을 하지 말고, 한국어 뉴스 브리핑처럼 자연스럽게 쓴다.
3. 맨 위에 "📊 세계경제 핵심 브리핑" 제목을 넣는다.
4. 그 다음 "🔥 오늘 핵심 3줄" 섹션을 만들고, 전체 흐름을 3줄로 요약한다.
5. 그 아래 카테고리를 나눠 정리한다.
6. 카테고리는 아래 중 필요한 것만 사용한다:
   - 금리/통화
   - 에너지
   - 중국
   - 미국
   - 유럽
   - 무역/공급망
   - 기타
7. 각 카테고리당 최대 3개까지만 넣는다.
8. 각 항목 형식은 아래처럼 맞춘다:
   번호. 자연스러운 한국어 제목
   → 1문장 요약
9. 링크는 출력하지 않는다.
10. 불필요한 군더더기 없이 읽기 좋게 정리한다.
11. 전체 길이는 너무 길지 않게, 푸시 알림 본문으로 읽을 수 있는 수준으로 유지한다.

기사 목록:
{joined}
""".strip()

    return prompt


def summarize_with_openai(news_list):
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY가 비어 있습니다.")

    prompt = build_prompt(news_list)

    url = "https://api.openai.com/v1/responses"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "gpt-5.4-nano",
        "input": prompt,
        "max_output_tokens": 1200,
    }

    response = requests.post(url, headers=headers, json=payload, timeout=120)
    response.raise_for_status()
    result = response.json()

    if result.get("output_text"):
        return result["output_text"].strip()

    # fallback 파싱
    output_text = ""
    for item in result.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                output_text += content.get("text", "")

    output_text = output_text.strip()
    if not output_text:
        raise RuntimeError(
            f"OpenAI 응답 파싱 실패: {json.dumps(result, ensure_ascii=False)[:2000]}"
        )

    return output_text


def send_push(message):
    if not NTFY_TOPIC:
        raise ValueError("NTFY_TOPIC이 비어 있습니다.")
    if not message:
        raise ValueError("전송할 메시지가 비어 있습니다.")

    # ntfy 본문 너무 길면 잘라냄
    if len(message) > 3500:
        message = message[:3500] + "\n...(이하 생략)"

    url = f"https://ntfy.sh/{NTFY_TOPIC}"
    headers = {
        "Title": "World Economy Briefing",
        "Tags": "chart_with_upwards_trend,newspaper",
    }

    response = requests.post(
        url,
        data=message.encode("utf-8"),
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()


if __name__ == "__main__":
    news = get_news()
    print(f"가져온 뉴스 수: {len(news)}")

    message = summarize_with_openai(news)

    print("=== 전송 메시지 시작 ===")
    print(message)
    print("=== 전송 메시지 끝 ===")

    send_push(message)
    print("푸시 전송 완료")
