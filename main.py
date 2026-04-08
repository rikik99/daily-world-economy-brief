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
    return first if first else desc[:160]


def get_news():
    url = "https://news.google.com/rss/search?q=world+economy&hl=en-US&gl=US&ceid=US:en"
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    root = ET.fromstring(response.content)
    items = root.findall(".//item")

    news_list = []
    for item in items[:8]:
        title_elem = item.find("title")
        desc_elem = item.find("description")

        title = title_elem.text.strip() if title_elem is not None and title_elem.text else ""
        desc = desc_elem.text if desc_elem is not None and desc_elem.text else ""

        if title:
            news_list.append({
                "title": title,
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
너는 세계경제 뉴스 브리핑 전문가이자 투자 관점의 시장 분석가다.

아래 뉴스들을 기반으로, 한국어로 짧고 직관적이며 투자 판단에 도움이 되도록 정리해라.

출력 형식은 반드시 아래를 그대로 따른다.

📊 세계경제 핵심 브리핑

🔥 오늘 한줄 결론
- 전체 시장 분위기를 한 문장으로 요약

⚠️ 리스크 요인
- 최대 3개
- 시장에 부담이 되는 요소만 짧게

💡 기회 요인
- 최대 3개
- 상대적으로 수혜 가능성이 있는 흐름만 짧게

🌍 시장 영향
- 🇺🇸 미국 주식: 한 줄
- 🇨🇳 중국 주식: 한 줄
- 🇰🇷 한국 주식: 한 줄
- 💵 달러: 한 줄
- 🛢 유가/원자재: 한 줄

📌 오늘 체크포인트
- 최대 3개
- 투자자가 오늘 꼭 봐야 할 변수만 작성

📰 주요 뉴스 3개
1. 자연스러운 한국어 제목
→ 왜 중요한지 한 줄
2. 자연스러운 한국어 제목
→ 왜 중요한지 한 줄
3. 자연스러운 한국어 제목
→ 왜 중요한지 한 줄

규칙:
1. 출력은 한국어로만 작성한다.
2. 길게 설명하지 말고, 휴대폰에서 한눈에 읽히게 쓴다.
3. 기사 제목을 어색하게 직역하지 말고 자연스러운 한국어로 바꾼다.
4. 중복 내용은 합쳐서 정리한다.
5. 투자 조언처럼 단정하지 말고, "가능성", "압력", "우려", "기대", "변동성 확대" 같은 표현을 사용한다.
6. 미국 주식은 금리·빅테크·에너지·유동성 영향을 반영한다.
7. 중국 주식은 정책 기대·내수·부동산·경기 회복 흐름을 반영한다.
8. 한국 주식은 반도체·수출·환율·대외 민감도를 반영한다.
9. 달러와 유가/원자재는 별도로 한 줄씩 정리한다.
10. 너무 장황하면 안 된다. 핵심만 남겨라.
11. 링크는 출력하지 않는다.

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
        "max_output_tokens": 700,
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

    if len(message) > 2500:
        message = message[:2500] + "\n...(이하 생략)"

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
