"""Локальный сервер поиска. Запуск: python app.py  ->  http://localhost:8000"""
import json, os, re, sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

def fts_query(q):
    terms = []
    for w in re.findall(r"\w+", q.lower()):
        if len(w) < 3: continue
        if re.search("[а-яё]", w) and len(w) > 5: w = w[:-2]   # грубое «усечение окончаний»
        terms.append(f'"{w}"*')
    return " OR ".join(terms)

SLUG = {"Сахих аль-Бухари": "bukhari", "Сахих Муслим": "muslim", "Сунан Абу Дауда": "abudawud",
        "Джами ат-Тирмизи": "tirmidhi", "Сунан ан-Насаи": "nasai", "Сунан Ибн Маджа": "ibnmajah"}

def make_url(kind, source, ref):
    if kind == "quran":
        m = re.match(r"(\d+):(\d+)", ref)
        return f"https://quran.com/{m.group(1)}/{m.group(2)}" if m else ""
    slug = SLUG.get(source)
    if not slug: return ""
    m = re.fullmatch(r"№(\d+)", ref)
    return f"https://sunnah.com/{slug}:{m.group(1)}" if m else f"https://sunnah.com/{slug}"

def search(q, lang, kind, limit=40):
    m = fts_query(q)
    if not m: return []
    sql = ("SELECT d.kind,d.source,d.ref,d.grade,d.text FROM fts JOIN docs d ON d.id=fts.rowid "
           "WHERE fts MATCH ? AND d.lang=?" + (" AND d.kind=?" if kind else "") + " ORDER BY bm25(fts) LIMIT ?")
    args = [m, lang] + ([kind] if kind else []) + [limit]
    db = sqlite3.connect("hadith.db")
    rows = db.execute(sql, args).fetchall(); db.close()
    return [dict(kind=a, source=b, ref=c, grade=d, text=e, url=make_url(a, b, c)) for a, b, c, d, e in rows]

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/api/search":
            p = parse_qs(u.query)
            res = search(p.get("q", [""])[0], p.get("lang", ["ru"])[0], p.get("kind", [""])[0])
            body, ct = json.dumps(res, ensure_ascii=False).encode(), "application/json; charset=utf-8"
        else:
            body, ct = open("index.html" if os.path.exists("index.html") else "static/index.html", "rb").read(), "text/html; charset=utf-8"
        self.send_response(200); self.send_header("Content-Type", ct); self.end_headers(); self.wfile.write(body)
    def log_message(self, *a): pass

port = int(os.environ.get("PORT", 8000))
print(f"Сервер запущен на порту {port}")
HTTPServer(("0.0.0.0", port), H).serve_forever()
