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
너는 세계경제 뉴스 브리핑 전문가이자 투자 관점의 시장 해설가다.

아래 뉴스들을 바탕으로, 한국어로 짧고 직관적이며 투자자가 바로 이해할 수 있게 브리핑해라.

반드시 아래 형식을 그대로 지켜라.

📊 세계경제 핵심 브리핑

🔥 오늘 한줄 결론
- 오늘 시장을 한 문장으로 요약

🚨 꼭 알아야 할 이슈
- 오늘 뉴스들 중 시장에 큰 충격을 줄 수 있거나 반드시 체크해야 할 사건이 있으면 최대 2개까지 작성
- 예: 전쟁 확전, 유가 급등 요인, 중앙은행 정책 급변, 관세/제재, 공급망 차질, 금융 시스템 불안, 대형 정책 변화
- 정말 중요한 이슈가 없으면 이 섹션은 아예 생략

🌍 시장 영향
- 🇺🇸 미국 주식: 상승 압력 / 하락 압력 / 혼조 가능성 중 하나를 먼저 쓰고, 이유를 짧게 설명
- 🇨🇳 중국 주식: 상승 압력 / 하락 압력 / 혼조 가능성 중 하나를 먼저 쓰고, 이유를 짧게 설명
- 🇰🇷 한국 주식: 상승 압력 / 하락 압력 / 혼조 가능성 중 하나를 먼저 쓰고, 이유를 짧게 설명
- 💵 달러: 강세 / 약세 / 혼조 가능성 중 하나를 먼저 쓰고, 이유를 짧게 설명
- 🛢 유가/원자재: 상승 압력 / 하락 압력 / 혼조 가능성 중 하나를 먼저 쓰고, 이유를 짧게 설명

🎯 테마/업종별 체크
- 유리한 테마 3개
- 불리한 테마 3개
- 각 항목은 아래 형식으로 작성
  - [강세 가능] 테마명: 이유 한 줄
  - [약세 가능] 테마명: 이유 한 줄

📌 오늘 체크포인트
- 시장에서 꼭 봐야 할 변수 3개

📰 주요 뉴스 3개
1. 자연스러운 한국어 제목
→ 왜 중요한지 한 줄
2. 자연스러운 한국어 제목
→ 왜 중요한지 한 줄
3. 자연스러운 한국어 제목
→ 왜 중요한지 한 줄

규칙:
1. 출력은 한국어로만 작성한다.
2. "변동성 확대 가능성" 같은 모호한 표현만 쓰지 말고, 방향성을 먼저 제시하라.
3. 방향성은 기사 흐름을 종합해 현실적으로 판단하라.
4. 미국 주식은 금리, 빅테크, 에너지, 유동성, 소비 흐름을 반영하라.
5. 중국 주식은 정책 기대, 경기부양, 내수, 수출, 부동산 흐름을 반영하라.
6. 한국 주식은 반도체, 2차전지, 자동차, 환율, 수출 민감도를 반영하라.
7. 테마/업종은 실제 투자자가 바로 이해할 수 있게 작성하라.
8. 예시 테마: 반도체, AI, 빅테크, 에너지, 원자재, 방산, 조선, 자동차, 2차전지, 소비재, 항공, 운송, 은행, 바이오 등
9. 특정 종목명을 억지로 넣지 말고, 테마나 업종 중심으로 써라.
10. 단정적 투자 추천은 금지하고, "강세 가능", "약세 가능", "부담", "우위" 형태로 표현하라.
11. 기사 제목을 어색하게 직역하지 말고 자연스럽게 재작성하라.
12. 중복 내용은 합쳐서 정리하라.
13. 휴대폰에서 보기 좋게 짧고 밀도 높게 작성하라.
14. 링크는 출력하지 않는다.
15. "🚨 꼭 알아야 할 이슈"는 AI가 스스로 중요도를 판단해서 넣어라. 시장 영향이 제한적이면 억지로 쓰지 마라.
16. 지정학, 중앙은행, 환율, 유가, 공급망, 정책 쇼크는 우선적으로 평가하라.

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

    if len(message) > 2800:
        message = message[:2800] + "\n...(이하 생략)"

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
