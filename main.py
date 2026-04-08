import os
import re
import html
import json
import requests
import xml.etree.ElementTree as ET

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY_JUNS")
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
    for item in items[:10]:
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
너는 세계경제 뉴스 브리핑 에디터이자 투자 관점의 시장 분석가다.
아래 기사 목록을 읽고, 한국어로 짧고 밀도 높게 브리핑해라.

반드시 아래 형식을 지켜라.

📊 세계경제 핵심 브리핑

🔥 오늘 핵심 3줄
- 전체 흐름을 가장 중요한 3줄로만 요약

🌍 세계 시장 영향
- 글로벌 증시 영향
- 금리/달러/환율 영향
- 원자재/에너지 영향
각 항목은 짧고 명확하게 작성

💰 투자 관점 체크포인트
- 투자자가 오늘 특히 볼 포인트 3개
- 예: 위험자산, 달러강세, 유가, 금리민감주, 원자재, 중국 경기 등
- “상승 가능성”, “변동성 확대 가능성”, “부담”, “방어적 우위”처럼 투자 판단에 도움되게 작성

📰 주요 뉴스 3개
1. 자연스러운 한국어 제목
→ 왜 중요한지 한 줄
2. 자연스러운 한국어 제목
→ 왜 중요한지 한 줄
3. 자연스러운 한국어 제목
→ 왜 중요한지 한 줄

규칙:
1. 출력은 한국어로만 작성한다.
2. 기사 제목을 직역하지 말고 자연스럽게 재작성한다.
3. 중복 내용은 합쳐서 정리한다.
4. 불필요한 군더더기는 빼고 핵심만 쓴다.
5. 너무 길게 쓰지 말고, 휴대폰 푸시에서 읽기 좋게 압축한다.
6. 링크는 출력하지 않는다.
7. 확인되지 않은 내용을 단정하지 말고, "가능성", "압력", "우려", "기대"처럼 신중하게 표현한다.
8. 투자 조언처럼 단정하지 말고, 시장에 미칠 가능성과 체크포인트 중심으로 작성한다.

기사 목록:
{joined}
""".strip()

    return prompt


def summarize_with_openai(news_list):
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY_JUNS가 비어 있습니다.")

    prompt = build_prompt(news_list)

    url = "https://api.openai.com/v1/responses"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "gpt-5.4-nano",
        "input": prompt,
        "max_output_tokens": 900,
    }

    response = requests.post(url, headers=headers, json=payload, timeout=120)
    print("OpenAI 응답코드:", response.status_code)
    print("OpenAI 응답본문:", response.text[:1000])
    response.raise_for_status()

    result = response.json()

    if result.get("output_text"):
        return result["output_text"].strip()

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
