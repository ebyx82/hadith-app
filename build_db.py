"""Скачивает Коран и сборники хадисов из открытых источников и строит базу SQLite.
Запуск: python build_db.py   (нужен интернет, только стандартная библиотека)
"""
import json, sqlite3, unicodedata, urllib.request

HADITH_CDN = "https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@1/editions/{}.json"
# Источник данных: github.com/fawazahmed0/hadith-api (список изданий: editions.json).
# Если издания на нужном языке нет - оно будет пропущено. Добавляй свои.
COLLECTIONS = {
    "bukhari": "Сахих аль-Бухари", "muslim": "Сахих Муслим",
    "abudawud": "Сунан Абу Дауда", "tirmidhi": "Джами ат-Тирмизи",
    "nasai": "Сунан ан-Насаи", "ibnmajah": "Сунан Ибн Маджа",
}
LANGS = ["rus", "eng", "ara"]
QURAN = {"ru": "ru.kuliev", "en": "en.sahih", "ar": "quran-uthmani"}  # api.alquran.cloud

def get(url):
    with urllib.request.urlopen(url, timeout=120) as r:
        return json.load(r)

db = sqlite3.connect("hadith.db")
db.executescript("""
DROP TABLE IF EXISTS docs; DROP TABLE IF EXISTS fts;
CREATE TABLE docs(id INTEGER PRIMARY KEY, kind TEXT, source TEXT, ref TEXT, key TEXT, lang TEXT, grade TEXT, text TEXT);
CREATE VIRTUAL TABLE fts USING fts5(text, content='docs', content_rowid='id', tokenize='unicode61 remove_diacritics 2');
""")

def add(kind, source, ref, key, lang, grade, text):
    if text and text.strip():
        db.execute("INSERT INTO docs(kind,source,ref,key,lang,grade,text) VALUES(?,?,?,?,?,?,?)",
                   (kind, source, ref, key, lang, grade, text.strip()))

def strip_bismillah(text):
    """В арабском тексте alquran.cloud басмала бывает приклеена к 1-му аяту суры. Убираем её."""
    plain = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn").replace("\u0671", "\u0627")
    words = text.split()
    if plain.split()[:4] == ["بسم", "الله", "الرحمن", "الرحيم"] and len(words) > 4:
        return " ".join(words[4:])
    return text

for key, name in COLLECTIONS.items():
    for lang in LANGS:
        ed = f"{lang}-{key}"
        try:
            data = get(HADITH_CDN.format(ed))
        except Exception as e:
            print(f"  пропуск {ed}: {e}"); continue
        n = 0
        for h in data.get("hadiths", []):
            grades = "; ".join(f'{g.get("grade")} ({g.get("name")})' for g in h.get("grades", []))
            ref = f'№{h.get("hadithnumber")}'
            add("hadith", name, ref, ref, lang[:2], grades, h.get("text"))
            n += 1
        print(f"{ed}: {n}")

for lang, ed in QURAN.items():
    try:
        data = get(f"https://api.alquran.cloud/v1/quran/{ed}")["data"]["surahs"]
    except Exception as e:
        print(f"  пропуск Корана {ed}: {e}"); continue
    n = 0
    for s in data:
        for a in s["ayahs"]:
            key = f'{s["number"]}:{a["numberInSurah"]}'
            txt = a["text"]
            if lang == "ar" and a["numberInSurah"] == 1 and s["number"] not in (1, 9):
                txt = strip_bismillah(txt)
            add("quran", "Коран", f'{key} ({s["englishName"]})', key, lang, "", txt); n += 1
    print(f"Коран {ed}: {n}")

db.execute("INSERT INTO fts(rowid,text) SELECT id,text FROM docs")
db.execute("CREATE INDEX idx_key ON docs(kind,source,lang,key)")
db.commit(); db.close()
print("Готово: hadith.db")
