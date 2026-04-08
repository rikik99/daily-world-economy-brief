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


def fetch_yahoo_chart(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {
        "range": "5d",
        "interval": "1d",
        "includePrePost": "false",
        "events": "div,splits"
    }

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

    result = data["chart"]["result"][0]
    meta = result.get("meta", {})
    closes = result["indicators"]["quote"][0].get("close", [])

    valid_closes = [c for c in closes if c is not None]
    if len(valid_closes) < 2:
        raise ValueError(f"{symbol} 종가 데이터 부족")

    current = valid_closes[-1]
    prev = valid_closes[-2]
    change_pct = ((current - prev) / prev) * 100 if prev else 0.0

    return {
        "symbol": symbol,
        "name": meta.get("symbol", symbol),
        "currency": meta.get("currency", ""),
        "current": round(current, 2),
        "prev_close": round(prev, 2),
        "change_pct": round(change_pct, 2),
    }


def get_market_snapshot():
    # Yahoo Finance commonly used symbols
    targets = {
        "미국(S&P500)": "^GSPC",
        "미국(나스닥)": "^IXIC",
        "중국(상하이종합)": "000001.SS",
        "한국(코스피)": "^KS11",
        "달러인덱스": "DX-Y.NYB",
        "WTI유가": "CL=F",
    }

    snapshot = {}

    for label, symbol in targets.items():
        try:
            snapshot[label] = fetch_yahoo_chart(symbol)
        except Exception as e:
            snapshot[label] = {
                "symbol": symbol,
                "error": str(e)
            }

    return snapshot


def build_market_stats_text(market_snapshot):
    lines = []
    for label, data in market_snapshot.items():
        if "error" in data:
            lines.append(f"- {label}: 데이터 조회 실패")
            continue

        sign = "+" if data["change_pct"] > 0 else ""
        lines.append(
            f"- {label}: {data['current']} ({sign}{data['change_pct']}%)"
        )
    return "\n".join(lines)


def build_prompt(news_list, market_snapshot):
    articles = []
    for i, article in enumerate(news_list, start=1):
        articles.append(
            f"[기사 {i}]\n"
            f"제목: {article['title']}\n"
            f"설명: {article['summary']}\n"
        )

    joined_news = "\n".join(articles)
    market_stats = build_market_stats_text(market_snapshot)

    prompt = f"""
너는 세계경제 뉴스 브리핑 전문가이자 투자 관점의 시장 해설가다.

아래 뉴스들과 실제 시장 지표를 함께 보고, 한국어로 짧고 직관적으로 브리핑해라.
중요한 원칙은 "뉴스 해석"과 "실제 시장 반응"을 구분해서 보는 것이다.

반드시 아래 형식을 그대로 지켜라.

📊 세계경제 핵심 브리핑

🔥 오늘 한줄 결론
- 뉴스와 실제 시장 반응을 종합한 한 문장

🚨 꼭 알아야 할 이슈
- 시장에 큰 영향을 줄 만한 사건이 있으면 최대 2개
- 정말 중요하지 않으면 이 섹션은 생략

📈 실제 시장 통계
- 🇺🇸 S&P500: 수치와 방향을 짧게
- 🇺🇸 나스닥: 수치와 방향을 짧게
- 🇨🇳 중국주식(상하이): 수치와 방향을 짧게
- 🇰🇷 한국주식(코스피): 수치와 방향을 짧게
- 💵 달러인덱스: 수치와 방향을 짧게
- 🛢 WTI유가: 수치와 방향을 짧게

🌍 시장 영향
- 🇺🇸 미국 주식: 상승 압력 / 하락 압력 / 혼조 가능성 중 하나를 먼저 쓰고, 실제 지표와 뉴스 흐름을 함께 반영해서 설명
- 🇨🇳 중국 주식: 상승 압력 / 하락 압력 / 혼조 가능성 중 하나를 먼저 쓰고, 실제 지표와 뉴스 흐름을 함께 반영해서 설명
- 🇰🇷 한국 주식: 상승 압력 / 하락 압력 / 혼조 가능성 중 하나를 먼저 쓰고, 실제 지표와 뉴스 흐름을 함께 반영해서 설명
- 💵 달러: 강세 / 약세 / 혼조 가능성 중 하나를 먼저 쓰고 설명
- 🛢 유가/원자재: 상승 압력 / 하락 압력 / 혼조 가능성 중 하나를 먼저 쓰고 설명

🎯 테마/업종별 체크
- 유리한 테마 3개
- 불리한 테마 3개
- 형식:
  - [강세 가능] 테마명: 이유 한 줄
  - [약세 가능] 테마명: 이유 한 줄

📌 오늘 체크포인트
- 오늘 꼭 봐야 할 변수 3개

📰 주요 뉴스 3개
1. 자연스러운 한국어 제목
→ 왜 중요한지 한 줄
2. 자연스러운 한국어 제목
→ 왜 중요한지 한 줄
3. 자연스러운 한국어 제목
→ 왜 중요한지 한 줄

규칙:
1. 한국어로만 작성한다.
2. 뉴스만 보고 방향을 단정하지 말고, 아래 실제 시장 통계도 함께 반영한다.
3. 실제 지표가 뉴스 해석과 다르면, 그 차이를 짧게 설명한다.
4. "변동성 확대" 같은 모호한 말만 하지 말고, 방향성을 먼저 제시한다.
5. 투자 추천처럼 단정하지 말고, "강세 가능", "약세 가능", "부담", "우위", "반등 가능성" 형태로 표현한다.
6. 미국 주식은 금리, 빅테크, 에너지, 유동성을 반영한다.
7. 중국 주식은 정책 기대, 경기 회복, 내수, 부동산 흐름을 반영한다.
8. 한국 주식은 반도체, 2차전지, 자동차, 환율, 수출 민감도를 반영한다.
9. 링크는 출력하지 않는다.
10. 휴대폰에서 읽기 좋게 짧고 밀도 높게 작성한다.

실제 시장 통계:
{market_stats}

기사 목록:
{joined_news}
""".strip()

    return prompt


def summarize_with_openai(news_list, market_snapshot):
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY_JUNS가 비어 있습니다.")

    prompt = build_prompt(news_list, market_snapshot)

    url = "https://api.openai.com/v1/responses"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "gpt-5.4-nano",
        "input": prompt,
        "max_output_tokens": 1000,
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
    market_snapshot = get_market_snapshot()

    print(f"가져온 뉴스 수: {len(news)}")
    print("=== 시장 스냅샷 ===")
    print(json.dumps(market_snapshot, ensure_ascii=False, indent=2))

    message = summarize_with_openai(news, market_snapshot)

    print("=== 전송 메시지 시작 ===")
    print(message)
    print("=== 전송 메시지 끝 ===")

    send_push(message)
    print("푸시 전송 완료")
