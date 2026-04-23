import os
import re
import html
import json
import time
import requests
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY_JUNS")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC")
ALPHAVANTAGE_API_KEY = os.environ.get("ALPHAVANTAGE_API_KEY")

RSS_QUERIES = [
    ("세계경제", "world economy"),
    ("금리/인플레", "interest rates OR inflation OR central bank"),
    ("유가/원자재", "oil OR crude OR commodities"),
    ("중국경제", "China economy"),
    ("미국경제", "US economy OR Wall Street OR Federal Reserve"),
    ("무역/공급망", "trade OR tariff OR supply chain"),
]


def clean_html(text):
    text = html.unescape(text or "")
    text = re.sub(r"<.*?>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_title(title):
    title = clean_html(title).lower()
    title = re.sub(r"\s+", " ", title)
    title = re.sub(r"[^a-z0-9가-힣\s]", "", title)
    return title.strip()


def extract_summary(desc):
    desc = clean_html(desc)
    if not desc:
        return ""

    parts = re.split(r"[.?!]", desc)
    first = parts[0].strip()
    return first if first else desc[:140]


def parse_pubdate(pubdate_text):
    if not pubdate_text:
        return None
    try:
        return parsedate_to_datetime(pubdate_text)
    except Exception:
        return None


def fetch_rss_query(label, query):
    url = "https://news.google.com/rss/search"
    params = {
        "q": query,
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en",
    }

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()

    root = ET.fromstring(response.content)
    items = root.findall(".//item")

    results = []
    for item in items[:6]:
        title_elem = item.find("title")
        desc_elem = item.find("description")
        pub_elem = item.find("pubDate")

        title = title_elem.text.strip() if title_elem is not None and title_elem.text else ""
        desc = desc_elem.text if desc_elem is not None and desc_elem.text else ""
        pub_date = pub_elem.text.strip() if pub_elem is not None and pub_elem.text else ""

        dt = parse_pubdate(pub_date)

        if title:
            results.append({
                "source_label": label,
                "title": title,
                "summary": extract_summary(desc),
                "pub_date": pub_date,
                "pub_dt": dt,
                "norm_title": normalize_title(title),
            })

    return results


def get_news():
    all_news = []

    for label, query in RSS_QUERIES:
        try:
            all_news.extend(fetch_rss_query(label, query))
        except Exception as e:
            print(f"RSS 조회 실패 - {label}: {e}")

    dedup = {}
    for article in all_news:
        key = article["norm_title"]
        if not key:
            continue

        if key not in dedup:
            dedup[key] = article
        else:
            old_dt = dedup[key].get("pub_dt")
            new_dt = article.get("pub_dt")
            if new_dt and (not old_dt or new_dt > old_dt):
                dedup[key] = article

    unique_news = list(dedup.values())
    epoch = parsedate_to_datetime("Thu, 01 Jan 1970 00:00:00 GMT")
    unique_news.sort(
        key=lambda x: x["pub_dt"] if x["pub_dt"] is not None else epoch,
        reverse=True,
    )

    final_news = []
    used_labels = {}

    for article in unique_news:
        label = article["source_label"]
        used_labels[label] = used_labels.get(label, 0) + 1

        if used_labels[label] <= 2:
            final_news.append(article)

        if len(final_news) >= 10:
            break

    return final_news


def alpha_get(params, label):
    if not ALPHAVANTAGE_API_KEY:
        raise ValueError("ALPHAVANTAGE_API_KEY가 비어 있습니다.")

    url = "https://www.alphavantage.co/query"
    params = dict(params)
    params["apikey"] = ALPHAVANTAGE_API_KEY

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

    if "Note" in data:
        raise RuntimeError(f"{label} 호출 제한: {data['Note']}")
    if "Error Message" in data:
        raise RuntimeError(f"{label} 조회 실패: {data['Error Message']}")

    return data


def fetch_alpha_daily_change(symbol, label):
    data = alpha_get(
        {
            "function": "TIME_SERIES_DAILY",
            "symbol": symbol,
            "outputsize": "compact",
        },
        label,
    )

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


def fetch_latest_indicator(function_name, symbol, series_type="close", interval="daily", time_period=None):
    params = {
        "function": function_name,
        "symbol": symbol,
        "interval": interval,
    }
    if series_type:
        params["series_type"] = series_type
    if time_period is not None:
        params["time_period"] = str(time_period)

    data = alpha_get(params, f"{symbol} {function_name}")

    key = None
    for k in data.keys():
        if "Technical Analysis" in k:
            key = k
            break

    if not key:
        raise RuntimeError(f"{symbol} {function_name} 지표 데이터 없음: {json.dumps(data)[:500]}")

    series = data[key]
    dates = sorted(series.keys())
    if not dates:
        raise RuntimeError(f"{symbol} {function_name} 날짜 데이터 없음")

    latest = series[dates[-1]]
    return dates[-1], latest


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


def get_technical_snapshot():
    chart_targets = [
        ("미국", "SPY"),
        ("중국", "MCHI"),
        ("한국", "EWY"),
    ]

    technicals = {}
    for label, symbol in chart_targets:
        item = {"symbol": symbol}

        try:
            _, sma = fetch_latest_indicator("SMA", symbol, time_period=20)
            item["sma20"] = float(sma["SMA"])
        except Exception as e:
            item["sma20_error"] = str(e)
        time.sleep(12)

        try:
            _, rsi = fetch_latest_indicator("RSI", symbol, time_period=14)
            item["rsi14"] = float(rsi["RSI"])
        except Exception as e:
            item["rsi14_error"] = str(e)
        time.sleep(12)

        try:
            _, macd = fetch_latest_indicator("MACD", symbol)
            item["macd"] = float(macd["MACD"])
            item["macd_signal"] = float(macd["MACD_Signal"])
            item["macd_hist"] = float(macd["MACD_Hist"])
        except Exception as e:
            item["macd_error"] = str(e)
        time.sleep(12)

        technicals[label] = item

    return technicals


def build_market_stats_text(market_snapshot):
    lines = []
    for label, data in market_snapshot.items():
        if "error" in data:
            lines.append(f"- {label}: 조회 실패")
            continue

        sign = "+" if data["change_pct"] > 0 else ""
        lines.append(f"- {label}: {sign}{data['change_pct']}%")
    return "\n".join(lines)


def build_technical_text(technical_snapshot, market_snapshot):
    label_to_market = {
        "미국": "미국 대형주",
        "중국": "중국 주식",
        "한국": "한국 주식",
    }

    lines = []
    for label, tech in technical_snapshot.items():
        market_label = label_to_market[label]
        market_data = market_snapshot.get(market_label, {})
        price = market_data.get("price")

        parts = [f"[{label}]"]

        if price is not None:
            parts.append(f"가격={price}")

        if "sma20" in tech:
            parts.append(f"SMA20={round(tech['sma20'], 2)}")
        if "rsi14" in tech:
            parts.append(f"RSI14={round(tech['rsi14'], 2)}")
        if "macd" in tech and "macd_signal" in tech and "macd_hist" in tech:
            parts.append(
                f"MACD={round(tech['macd'], 4)}, Signal={round(tech['macd_signal'], 4)}, Hist={round(tech['macd_hist'], 4)}"
            )

        lines.append(" / ".join(parts))

    return "\n".join(lines)


def build_news_text(news_list):
    lines = []
    for i, article in enumerate(news_list, start=1):
        pub = article["pub_date"] or "시간 정보 없음"
        lines.append(
            f"[기사 {i}]\n"
            f"분류: {article['source_label']}\n"
            f"제목: {article['title']}\n"
            f"설명: {article['summary']}\n"
            f"발행시각: {pub}\n"
        )
    return "\n".join(lines)


def build_prompt(news_list, market_snapshot, technical_snapshot):
    joined_news = build_news_text(news_list)
    market_stats = build_market_stats_text(market_snapshot)
    technical_text = build_technical_text(technical_snapshot, market_snapshot)

    prompt = f"""
너는 세계경제 뉴스 브리핑 전문가이자 전문 주식 트레이더다.
뉴스 해석뿐 아니라 실제 차트 기술지표(SMA20, RSI14, MACD)까지 함께 보고 짧게 브리핑해라.

중요:
- 뉴스는 반드시 5개를 선정해서 보여라.
- 뉴스는 서로 비슷한 것 말고 최대한 다른 주제(금리/인플레, 유가/지정학, 중국, 미국, 무역/공급망 등)로 골라라.
- 차트 해석은 실제 제공된 기술지표를 근거로 하라.
- 1~3거래일 관점의 단기 흐름을 예상하라.
- 투자 추천처럼 단정하지 말고, "상승 우세", "하락 우세", "혼조 가능성" 형태로 표현하라.

반드시 아래 형식을 그대로 지켜라.

📊 세계경제 브리핑

🧭 한줄
- 오늘 뉴스 흐름과 시장 분위기를 한 문장으로 요약

📰 핵심 뉴스
- 총 5개
- 형식:
  - 📰 자연스럽게 재작성된 제목
    → 핵심 내용 한 줄

🚨 해석
- 위 뉴스들을 종합한 핵심 해석 2개
- 시장에 큰 변동성을 줄 사건이 있으면 반드시 반영

📉 차트 해석
- 🇺🇸 미국: SMA20/RSI/MACD를 근거로 한 줄
- 🇨🇳 중국: SMA20/RSI/MACD를 근거로 한 줄
- 🇰🇷 한국: SMA20/RSI/MACD를 근거로 한 줄

🌍 앞으로의 흐름(1~3거래일)
- 🇺🇸 미국: 상승 우세 / 하락 우세 / 혼조 가능성 중 하나를 먼저 쓰고 이유 한 줄
- 🇨🇳 중국: 상승 우세 / 하락 우세 / 혼조 가능성 중 하나를 먼저 쓰고 이유 한 줄
- 🇰🇷 한국: 상승 우세 / 하락 우세 / 혼조 가능성 중 하나를 먼저 쓰고 이유 한 줄

🎯 테마
- 🟢 강세 가능 2개
- 🔴 약세 가능 2개
- 형식:
  - 🟢 테마명: 이유 한 줄
  - 🔴 테마명: 이유 한 줄

규칙:
1. 한국어로만 작성한다.
2. 뉴스 비중을 높여라. 뉴스 5개는 반드시 포함한다.
3. 뉴스는 다양한 주제를 고르고, 중복/유사 뉴스는 피한다.
4. "뉴스 → 해석 → 차트 해석 → 앞으로의 흐름" 순서를 유지한다.
5. 실제 시장 통계와 뉴스 흐름, 차트 지표를 함께 반영한다.
6. 차트 해석은 제공된 기술지표를 근거로만 작성한다.
7. 예를 들어 RSI가 높으면 과열 가능성, 낮으면 과매도 가능성, 가격이 SMA20 위면 단기 추세 우위, MACD가 signal 위면 모멘텀 개선 가능성처럼 해석할 수 있다.
8. 숫자를 길게 나열하지 말고 의미 중심으로 풀어라.
9. 휴대폰에서 읽기 좋게 짧고 직관적으로 작성하라.

실제 시장 통계:
{market_stats}

기술지표:
{technical_text}

기사 목록:
{joined_news}
""".strip()

    return prompt


def summarize_with_openai(news_list, market_snapshot, technical_snapshot):
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY_JUNS가 비어 있습니다.")

    prompt = build_prompt(news_list, market_snapshot, technical_snapshot)

    url = "https://api.openai.com/v1/responses"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "gpt-5.4-nano",
        "input": prompt,
        "max_output_tokens": 950,
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
    technical_snapshot = get_technical_snapshot()

    print(f"가져온 뉴스 수: {len(news)}")
    print("=== 뉴스 목록 ===")
    print(json.dumps(news, ensure_ascii=False, indent=2, default=str))
    print("=== 시장 스냅샷 ===")
    print(json.dumps(market_snapshot, ensure_ascii=False, indent=2, default=str))
    print("=== 기술지표 스냅샷 ===")
    print(json.dumps(technical_snapshot, ensure_ascii=False, indent=2, default=str))

    message = summarize_with_openai(news, market_snapshot, technical_snapshot)

    print("=== 전송 메시지 시작 ===")
    print(message)
    print("=== 전송 메시지 끝 ===")

    send_push(message)
    print("푸시 전송 완료")
