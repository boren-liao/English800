#!/usr/bin/env python3
"""每日抓取美國商業／經濟新聞 RSS，轉成 English 800 的新聞課程 data/news.json。

只用 Python 標準函式庫，GitHub Actions 每天自動執行。
- 內容：新聞標題 + RSS 摘要（附來源與原文連結，僅供個人學習）
- 自動比對商務字彙表產生「關鍵片語」
- 嘗試自動翻譯成繁體中文（失敗時保留空白，App 會顯示翻譯連結）
"""
import datetime as dt
import email.utils
import hashlib
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


# 機器翻譯常見的中國用語／錯譯 → 台灣商業新聞用語
TW_FIX = [
    ("英偉達", "輝達"), ("管製", "管制"), ("製裁", "制裁"), ("控製", "控制"), ("限製", "限制"),
    ("地面停車", "全面停飛"), ("地面停留", "全面停飛"), ("地面停止", "全面停飛"),
    ("首席執行官", "執行長"), ("首席財務官", "財務長"), ("首席技術官", "技術長"), ("首席運營官", "營運長"),
    ("美聯儲", "聯準會"), ("美聯準", "聯準會"), ("聯邦儲備委員會", "聯準會"), ("聯邦儲備", "聯準會"),
    ("人工智能", "人工智慧"), ("芯片", "晶片"), ("半導體芯片", "半導體晶片"), ("服務器", "伺服器"),
    ("軟件", "軟體"), ("硬件", "硬體"), ("互聯網", "網際網路"), ("網絡", "網路"), ("信息", "資訊"),
    ("數據中心", "資料中心"), ("視頻", "影片"), ("質量", "品質"), ("項目", "專案"),
    ("用戶", "使用者"), ("程序", "程式"), ("在線", "線上"), ("默認", "預設"), ("支持", "支援"),
    ("德克薩斯州", "德州"), ("加利福尼亞州", "加州"), ("佛羅里達州", "佛州"), ("華盛頓特區", "華府"),
    ("納斯達克", "那斯達克"), ("標準普爾", "標普"), ("道瓊斯", "道瓊"), ("特朗普", "川普"),
    ("蘋果公司", "蘋果"), ("谷歌", "Google"), ("臉書", "Facebook"), ("亞馬遜公司", "亞馬遜"),
    ("星際飛船", "星艦"), ("星艦飛船", "星艦"), ("火箭的上級", "火箭的上節"), ("全國全面停飛", "全美停飛"), ("美國聯邦航空局", "美國聯邦航空總署（FAA）"),
    ("關稅壁壘", "關稅障礙"), ("出租車", "計程車"), ("公交", "公車"), ("短信", "簡訊"),
    ("黃仁勳的潛在回報", "黃仁勳可能回歸"), ("的潛在回報", "可能回歸"),
]


def tw_fix(text):
    for a, b in TW_FIX:
        text = text.replace(a, b)
    return text


def _claude(text):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("no ANTHROPIC_API_KEY")
    body = json.dumps({
        "model": os.environ.get("CLAUDE_MODEL", "claude-haiku-5-5"),
        "max_tokens": 1024,
        "system": ("你是台灣財經新聞編譯。把使用者給的英文新聞翻成自然、通順的台灣繁體中文，"
                   "使用台灣慣用譯名與用語（例：Nvidia→輝達、the Fed→聯準會、CEO→執行長、ground stop→全面停飛、Trump→川普）。"
                   "公司名、產品名若台灣慣用英文就保留英文。數字與金額照原文換算成中文習慣寫法。只輸出譯文，不要任何說明。"),
        "messages": [{"role": "user", "content": text}],
    }).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())
    return "".join(c.get("text", "") for c in data.get("content", []) if c.get("type") == "text")


def _translate_one(text):
    for fn in (_gtx, _mymemory):
        try:
            out = fn(text).strip()
            if out and re.search(r"[\u4e00-\u9fff]", out):
                return out
        except Exception as e:
            print(f"  translate via {fn.__name__} failed: {e}", file=sys.stderr)
    return ""


def translate(text, title=None):
    """優先用 Claude（有設定金鑰時），否則用免費翻譯＋台灣用語校正。標題與內文分開翻譯。"""
    if not TRANSLATE or not text:
        return ""
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            out = _claude(text).strip()
            if out:
                return tw_fix(out)
        except Exception as e:
            print(f"  translate via claude failed: {e}", file=sys.stderr)
    parts = [title.rstrip(".") + ".", text[len(title.rstrip(".")) + 1:].strip()] if title and text.startswith(title.rstrip(".")) else [text]
    out = []
    for p in parts:
        if not p:
            continue
        z = _translate_one(p)
        if not z:
            return ""
        out.append(z)
    return tw_fix("".join(out))


ZH_VERSION = 2 + (1 if os.environ.get("ANTHROPIC_API_KEY") else 0)


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


def news_id(date, title):
    """以日期＋標題雜湊產生唯一編號，同一天跑多次也不會重複。"""
    return f"N{date.replace('-', '')}-{hashlib.sha1(title.strip().lower().encode()).hexdigest()[:6]}"


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
            "id": news_id(today, p["title"]),
            "unit": "每日美國新聞",
            "date": today,
            "title": p["title"],
            "level": p["source"],
            "source": p["source"],
            "link": p["link"],
            "en": en,
            "zh": translate(en, p["title"]),
            "zh_v": ZH_VERSION,
            "notes": "新聞英文：先聽一次抓大意（誰、做了什麼、數字），再慢速聽細節，最後看關鍵片語。內容摘自 " + p["source"] + " RSS，完整報導請點原文連結。",
            "phrases": phrases,
        })

    cutoff = (now + dt.timedelta(hours=8) - dt.timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    kept, seen_ids = [], {x["id"] for x in new_items}
    for x in old.get("items", []):
        if x.get("date", "") < cutoff:
            continue
        x["id"] = news_id(x["date"], x["title"])  # 修正舊版重複編號
        if x["id"] in seen_ids:
            continue
        seen_ids.add(x["id"])
        kept.append(x)
    for x in kept:  # 舊新聞用新版翻譯重新翻（失敗或版本較舊者）
        if not x.get("zh") or x.get("zh_v", 1) < ZH_VERSION:
            z = translate(x["en"], x.get("title"))
            if z:
                x["zh"], x["zh_v"] = z, ZH_VERSION
    items = new_items + kept
    out = {"updated": now.isoformat(timespec="seconds"), "items": items}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"news.json: {len(new_items)} new, {len(items)} total")


if __name__ == "__main__":
    main()
