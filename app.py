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

NAME = {v: k for k, v in SLUG.items()}
NAME["quran"] = "Коран"

PAGE = 20

def search(q, lang, srcs, offset=0, limit=PAGE):
    m = fts_query(q)
    if not m: return 0, []
    names = [NAME[x] for x in srcs if x in NAME]
    where = "WHERE fts MATCH ? AND d.lang=?" + (f" AND d.source IN ({','.join('?'*len(names))})" if names else "")
    base = "FROM fts JOIN docs d ON d.id=fts.rowid " + where
    args = [m, lang] + names
    db = sqlite3.connect("hadith.db")
    total = db.execute("SELECT COUNT(*) " + base, args).fetchone()[0]
    rows = db.execute("SELECT d.kind,d.source,d.ref,d.grade,d.text,d.key " + base + " ORDER BY bm25(fts) LIMIT ? OFFSET ?",
                      args + [limit, offset]).fetchall()
    out = []
    for a, b, c, d, e, k in rows:
        item = dict(kind=a, source=b, ref=c, grade=d, text=e, url=make_url(a, b, c))
        if lang != "ar":
            ar = db.execute("SELECT text FROM docs WHERE kind=? AND source=? AND lang='ar' AND key=?", (a, b, k)).fetchone()
            if ar: item["ar"] = ar[0]
        out.append(item)
    db.close()
    return total, out

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/api/search":
            p = parse_qs(u.query)
            srcs = [x for x in p.get("src", [""])[0].split(",") if x]
            total, rows = search(p.get("q", [""])[0], p.get("lang", ["ru"])[0], srcs, int(p.get("offset", ["0"])[0]))
            res = {"total": total, "results": rows, "page_size": PAGE}
            body, ct = json.dumps(res, ensure_ascii=False).encode(), "application/json; charset=utf-8"
        else:
            body, ct = open("index.html" if os.path.exists("index.html") else "static/index.html", "rb").read(), "text/html; charset=utf-8"
        self.send_response(200); self.send_header("Content-Type", ct); self.end_headers(); self.wfile.write(body)
    def log_message(self, *a): pass

port = int(os.environ.get("PORT", 8000))
print(f"Сервер запущен на порту {port}")
HTTPServer(("0.0.0.0", port), H).serve_forever()
