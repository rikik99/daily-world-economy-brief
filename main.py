import os
import re
import html
import json
import time
import requests
import xml.etree.ElementTree as ET

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY_JUNS")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC")
ALPHAVANTAGE_API_KEY = os.environ.get("ALPHAVANTAGE_API_KEY")


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
    return first if first else desc[:140]


def get_news():
    url = "https://news.google.com/rss/search?q=world+economy&hl=en-US&gl=US&ceid=US:en"
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    root = ET.fromstring(response.content)
    items = root.findall(".//item")

    news_list = []
    for item in items[:6]:
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


def fetch_alpha_daily_change(symbol, label):
    if not ALPHAVANTAGE_API_KEY:
        raise ValueError("ALPHAVANTAGE_API_KEY가 비어 있습니다.")

    url = "https://www.alphavantage.co/query"
    params = {
        "function": "TIME_SERIES_DAILY",
        "symbol": symbol,
        "apikey": ALPHAVANTAGE_API_KEY,
        "outputsize": "compact",
    }

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

    if "Note" in data:
        raise RuntimeError(f"{label} 호출 제한: {data['Note']}")
    if "Error Message" in data:
        raise RuntimeError(f"{label} 조회 실패: {data['Error Message']}")

    series = data.get("Time Series (Daily)")
    if not series:
        raise RuntimeError(f"{label} 일별 데이터 없음: {json.dumps(data)[:500]}")

    dates = sorted(series.keys())
    if len(dates) < 2:
        raise RuntimeError(f"{label} 데이터 부족")

    last_date = dates[-1]
    prev_date = dates[-2]

    last_close = float(series[last_date]["4. close"])
    prev_close = float(series[prev_date]["4. close"])
    change_pct = ((last_close - prev_close) / prev_close) * 100 if prev_close else 0.0

    return {
        "label": label,
        "symbol": symbol,
        "date": last_date,
        "price": round(last_close, 2),
        "prev_close": round(prev_close, 2),
        "change_pct": round(change_pct, 2),
    }


def get_market_snapshot():
    targets = [
        ("미국 대형주", "SPY"),
        ("미국 기술주", "QQQ"),
        ("중국 주식", "MCHI"),
        ("한국 주식", "EWY"),
        ("달러", "UUP"),
        ("유가", "USO"),
    ]

    snapshot = {}

    for label, symbol in targets:
        try:
            snapshot[label] = fetch_alpha_daily_change(symbol, label)
        except Exception as e:
            snapshot[label] = {
                "label": label,
                "symbol": symbol,
                "error": str(e),
            }
        time.sleep(12)

    return snapshot


def build_market_stats_text(market_snapshot):
    lines = []
    for label, data in market_snapshot.items():
        if "error" in data:
            lines.append(f"- {label}: 조회 실패")
            continue

        sign = "+" if data["change_pct"] > 0 else ""
        lines.append(f"- {label}: {sign}{data['change_pct']}%")
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

아래 뉴스와 시장 통계를 보고, 휴대폰에서 한눈에 읽히는 브리핑을 한국어로 작성해라.
핵심은 "뉴스 → 해석 → 시장" 흐름이 자연스럽게 보이게 만드는 것이다.

반드시 아래 형식을 그대로 지켜라.

📊 세계경제 브리핑

🧭 한줄
- 오늘 시장을 한 문장으로 요약

📰 핵심 뉴스
- 📰 자연스럽게 재작성된 제목
  → 핵심 요약 한 줄
- 📰 자연스럽게 재작성된 제목
  → 핵심 요약 한 줄

🚨 해석
- 위 뉴스들을 종합한 핵심 해석 1~2개
- 시장에 큰 영향을 주는 사건이 있으면 반드시 반영

🌍 시장
- 🇺🇸 미국: 상승 압력 / 하락 압력 / 혼조 중 하나를 먼저 쓰고 이유 한 줄
- 🇨🇳 중국: 상승 압력 / 하락 압력 / 혼조 중 하나를 먼저 쓰고 이유 한 줄
- 🇰🇷 한국: 상승 압력 / 하락 압력 / 혼조 중 하나를 먼저 쓰고 이유 한 줄
- 💵 달러: 강세 / 약세 / 혼조 중 하나를 먼저 쓰고 이유 한 줄
- 🛢 유가: 상승 압력 / 하락 압력 / 혼조 중 하나를 먼저 쓰고 이유 한 줄

🎯 테마
- 🟢 강세 2개
- 🔴 약세 2개
- 형식:
  - 🟢 테마명: 이유 한 줄
  - 🔴 테마명: 이유 한 줄

규칙:
1. 한국어로만 작성한다.
2. 반드시 뉴스 → 해석 → 시장 순서를 유지한다.
3. 뉴스는 2개만 쓴다.
4. 해석은 1~2개만 쓴다.
5. 강세 2개, 약세 2개만 쓴다.
6. 각 줄은 짧고 직관적으로 작성한다.
7. 숫자를 길게 나열하지 말고 방향성과 의미 중심으로 쓴다.
8. 실제 시장 통계와 뉴스 흐름을 함께 반영한다.
9. "변동성 확대 가능성" 같은 모호한 표현만 쓰지 말고 방향을 먼저 제시한다.
10. 투자 추천처럼 단정하지 말고 "압력", "우위", "부담", "반등 가능성" 형태로 표현한다.
11. 이모지 구조를 유지해서 가독성을 높인다.

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

    if len(message) > 2200:
        message = message[:2200] + "\n...(이하 생략)"

    url = f"https://ntfy.sh/{NTFY_TOPIC}"
    headers = {
        "Title": "World Market Briefing",
        "Tags": "chart_with_upwards_trend,newspaper,moneybag",
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
