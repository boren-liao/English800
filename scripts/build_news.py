#!/usr/bin/env python3
"""每日抓取美國商業／經濟新聞 RSS，轉成 English 800 的新聞課程 data/news.json。

只用 Python 標準函式庫，GitHub Actions 每天自動執行。
- 內容：新聞標題 + RSS 摘要（附來源與原文連結，僅供個人學習）
- 自動比對商務字彙表產生「關鍵片語」
- 嘗試自動翻譯成繁體中文（失敗時保留空白，App 會顯示翻譯連結）
"""
import datetime as dt
import email.utils
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "news.json")
UA = "Mozilla/5.0 (English800 study app; +https://github.com)"

FEEDS = [
    ("NPR Business", "https://feeds.npr.org/1006/rss.xml"),
    ("NPR Economy", "https://feeds.npr.org/1017/rss.xml"),
    ("CNBC", "https://www.cnbc.com/id/10001147/device/rss/rss.html"),
    ("CNBC Tech", "https://www.cnbc.com/id/19854910/device/rss/rss.html"),
    ("NYT Business", "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml"),
    ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
    ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
]
PER_DAY = int(os.environ.get("NEWS_PER_DAY", "8"))
KEEP_DAYS = int(os.environ.get("NEWS_KEEP_DAYS", "7"))
TRANSLATE = os.environ.get("NO_TRANSLATE") != "1"

# 商務新聞高頻字彙（英文小寫 → 中文）
GLOSSARY = {
    "tariff": "關稅", "tariffs": "關稅", "inflation": "通貨膨脹", "interest rate": "利率",
    "interest rates": "利率", "federal reserve": "聯準會", "the fed": "聯準會", "economy": "經濟",
    "economist": "經濟學家", "economists": "經濟學家", "recession": "經濟衰退", "earnings": "獲利；財報",
    "revenue": "營收", "profit": "利潤", "profits": "利潤", "forecast": "預測", "outlook": "展望",
    "investor": "投資人", "investors": "投資人", "shares": "股票", "stocks": "股票", "stock": "股票",
    "wall street": "華爾街", "rally": "上漲", "rallied": "上漲", "slump": "暴跌", "plunge": "重挫",
    "surge": "飆升", "surged": "飆升", "merger": "合併", "acquisition": "收購", "acquire": "收購",
    "deal": "交易", "regulator": "監管機關", "regulators": "監管機關", "antitrust": "反壟斷",
    "lawsuit": "訴訟", "layoffs": "裁員", "layoff": "裁員", "hiring": "招募", "jobs": "工作；就業",
    "unemployment": "失業", "wages": "工資", "consumer": "消費者", "consumers": "消費者",
    "spending": "支出", "retail": "零售", "retailers": "零售商", "supply chain": "供應鏈",
    "shortage": "短缺", "manufacturing": "製造業", "semiconductor": "半導體", "chips": "晶片",
    "chipmaker": "晶片製造商", "artificial intelligence": "人工智慧", "ai": "人工智慧",
    "data center": "資料中心", "data centers": "資料中心", "startup": "新創公司", "valuation": "估值",
    "ipo": "首次公開發行", "debt": "債務", "deficit": "赤字", "budget": "預算", "bond": "債券",
    "bonds": "債券", "yields": "殖利率", "treasury": "美國財政部；公債", "mortgage": "房貸",
    "housing": "住房", "oil": "石油", "prices": "價格", "price": "價格", "demand": "需求",
    "supply": "供給", "growth": "成長", "decline": "下滑", "quarter": "季度", "quarterly": "季度的",
    "annual": "年度的", "billion": "十億", "million": "百萬", "trillion": "兆", "ceo": "執行長",
    "executive": "主管", "executives": "主管", "board": "董事會", "shareholders": "股東",
    "dividend": "股利", "strike": "罷工", "union": "工會", "workers": "員工", "trade": "貿易",
    "exports": "出口", "imports": "進口", "sanctions": "制裁", "policy": "政策", "administration": "政府",
    "congress": "國會", "regulation": "法規", "electric vehicle": "電動車", "electric vehicles": "電動車",
    "automaker": "汽車製造商", "automakers": "汽車製造商", "airline": "航空公司", "airlines": "航空公司",
    "crypto": "加密貨幣", "bitcoin": "比特幣", "bank": "銀行", "banks": "銀行", "lender": "放款機構",
    "loan": "貸款", "loans": "貸款", "credit": "信用", "tax": "稅", "taxes": "稅",
    "subsidies": "補貼", "investment": "投資", "invest": "投資", "market": "市場", "markets": "市場",
    "sales": "銷售額", "customers": "顧客", "launch": "推出", "partnership": "合作關係",
    "competition": "競爭", "rival": "對手", "rivals": "對手", "cuts": "削減", "cut": "削減",
    "boost": "提振", "slowdown": "放緩", "volatility": "波動", "uncertainty": "不確定性",
}


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def clean(text):
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text


def first_sentences(text, max_words=55):
    sents = re.split(r"(?<=[.!?])\s+", text)
    out, n = [], 0
    for s in sents:
        w = len(s.split())
        if out and n + w > max_words:
            break
        out.append(s)
        n += w
    res = " ".join(out)
    words = res.split()
    if len(words) > max_words + 15:
        res = " ".join(words[:max_words]) + "…"
    return res


def parse_feed(source, raw):
    items = []
    root = ET.fromstring(raw)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    nodes = root.findall(".//item") or root.findall(".//atom:entry", ns)
    for it in nodes:
        def g(tag):
            el = it.find(tag)
            if el is None:
                el = it.find("atom:" + tag, ns)
            return el
        t = g("title")
        title = clean(t.text if t is not None else "")
        d = g("description")
        if d is None:
            d = g("summary")
        desc = clean(d.text if d is not None else "")
        l = g("link")
        link = ""
        if l is not None:
            link = (l.text or l.get("href") or "").strip()
        p = g("pubDate")
        if p is None:
            p = g("updated")
        pub = None
        if p is not None and p.text:
            try:
                pub = email.utils.parsedate_to_datetime(p.text)
            except Exception:
                try:
                    pub = dt.datetime.fromisoformat(p.text.replace("Z", "+00:00"))
                except Exception:
                    pub = None
        if not title or len(title.split()) < 4:
            continue
        items.append({"source": source, "title": title, "desc": desc, "link": link, "pub": pub})
    return items


def _gtx(text):
    q = urllib.parse.urlencode({"client": "gtx", "sl": "en", "tl": "zh-TW", "dt": "t", "q": text})
    data = json.loads(fetch("https://translate.googleapis.com/translate_a/single?" + q, timeout=15))
    return "".join(seg[0] for seg in data[0] if seg and seg[0])


def _mymemory(text):
    q = urllib.parse.urlencode({"q": text[:480], "langpair": "en|zh-TW"})
    data = json.loads(fetch("https://api.mymemory.translated.net/get?" + q, timeout=20))
    out = (data.get("responseData") or {}).get("translatedText") or ""
    if "MYMEMORY WARNING" in out.upper() or "QUERY LENGTH LIMIT" in out.upper():
        return ""
    return html.unescape(out)


def translate(text):
    """依序嘗試多個免費翻譯來源，全部失敗就回傳空字串。"""
    if not TRANSLATE or not text:
        return ""
    for fn in (_gtx, _mymemory):
        try:
            out = fn(text).strip()
            if out and re.search(r"[\u4e00-\u9fff]", out):
                return out
        except Exception as e:  # 翻譯失敗不影響主流程
            print(f"  translate via {fn.__name__} failed: {e}", file=sys.stderr)
    return ""


STOP = set("the a an of to in on for and with as at by is are was be from that this its it after over new says said will has have".split())


def topic_words(title):
    return {w[:5] for w in re.findall(r"[a-z]+", title.lower()) if len(w) > 2 and w not in STOP}  # 取字首5碼當簡易詞幹


def similar(a, b):
    x, y = topic_words(a), topic_words(b)
    return bool(x and y) and len(x & y) / min(len(x), len(y)) >= 0.4


def keywords(text, limit=5):
    low = " " + re.sub(r"[^a-z0-9 ]", " ", text.lower()) + " "
    found, seen = [], set()
    for k in sorted(GLOSSARY, key=len, reverse=True):
        if f" {k} " in low and GLOSSARY[k] not in seen:
            found.append([k, GLOSSARY[k]])
            seen.add(GLOSSARY[k])
            low = low.replace(f" {k} ", " ")
        if len(found) >= limit:
            break
    return found


def main():
    now = dt.datetime.now(dt.timezone.utc)
    today = (now + dt.timedelta(hours=8)).strftime("%Y-%m-%d")  # 以台灣日期歸檔
    pool = []
    for source, url in FEEDS:
        try:
            got = parse_feed(source, fetch(url))
            print(f"{source}: {len(got)} items")
            pool.extend(got)
        except Exception as e:
            print(f"{source}: FAILED {e}", file=sys.stderr)

    old = {"items": []}
    if os.path.exists(OUT):
        try:
            with open(OUT, encoding="utf-8") as f:
                old = json.load(f)
        except Exception:
            pass
    known_titles = {i["title"].lower() for i in old.get("items", [])}

    recent = [p for p in pool if p["pub"] is None or (now - p["pub"]).total_seconds() < 36 * 3600]
    recent.sort(key=lambda p: p["pub"] or now, reverse=True)
    picked, per_source = [], {}
    for p in recent:
        key = p["title"].lower()
        if key in known_titles or any(similar(p["title"], x["title"]) for x in picked):
            continue  # 同一事件只留一則
        if per_source.get(p["source"], 0) >= 2:  # 每個來源最多 2 則，增加多樣性
            continue
        picked.append(p)
        per_source[p["source"]] = per_source.get(p["source"], 0) + 1
        if len(picked) >= PER_DAY:
            break

    new_items = []
    for i, p in enumerate(picked):
        body = first_sentences(p["desc"]) if p["desc"] and p["desc"].lower() != p["title"].lower() else ""
        en = p["title"].rstrip(".") + "." + (" " + body if body else "")
        phrases = keywords(en)
        new_items.append({
            "id": f"N{today.replace('-', '')}-{i + 1:02d}",
            "unit": "每日美國新聞",
            "date": today,
            "title": p["title"],
            "level": p["source"],
            "source": p["source"],
            "link": p["link"],
            "en": en,
            "zh": translate(en),
            "notes": "新聞英文：先聽一次抓大意（誰、做了什麼、數字），再慢速聽細節，最後看關鍵片語。內容摘自 " + p["source"] + " RSS，完整報導請點原文連結。",
            "phrases": phrases,
        })

    cutoff = (now + dt.timedelta(hours=8) - dt.timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    kept = [x for x in old.get("items", []) if x.get("date", "") >= cutoff]
    for x in kept:  # 先前翻譯失敗的舊新聞補翻譯
        if not x.get("zh"):
            x["zh"] = translate(x["en"])
    items = new_items + kept
    out = {"updated": now.isoformat(timespec="seconds"), "items": items}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"news.json: {len(new_items)} new, {len(items)} total")


if __name__ == "__main__":
    main()
