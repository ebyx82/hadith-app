"""Скачивает Коран и сборники хадисов из открытых источников и строит базу SQLite.
Запуск: python build_db.py   (нужен интернет, только стандартная библиотека)
"""
import json, sqlite3, unicodedata, urllib.request

HADITH_CDN = "https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@1/editions/{}.json"
COLLECTIONS = {
    "bukhari": "Сахих аль-Бухари", "muslim": "Сахих Муслим",
    "abudawud": "Сунан Абу Дауда", "tirmidhi": "Джами ат-Тирмизи",
    "nasai": "Сунан ан-Насаи", "ibnmajah": "Сунан Ибн Маджа",
}
LANGS = ["rus", "eng", "ara"]
QURAN = {"ru": "ru.kuliev", "en": "en.sahih", "ar": "quran-uthmani"}  # api.alquran.cloud (ar идёт последним)
RU_NAMES = ("Аль-Фатиха|Аль-Бакара|Али Имран|Ан-Ниса|Аль-Маида|Аль-Анам|Аль-Араф|Аль-Анфаль|Ат-Тауба|Юнус|Худ|Юсуф|Ар-Раад|Ибрахим|Аль-Хиджр|Ан-Нахль|Аль-Исра|Аль-Кахф|Марьям|Та Ха|"
 "Аль-Анбийа|Аль-Хаджж|Аль-Муминун|Ан-Нур|Аль-Фуркан|Аш-Шуара|Ан-Намль|Аль-Касас|Аль-Анкабут|Ар-Рум|Лукман|Ас-Саджда|Аль-Ахзаб|Саба|Фатыр|Я Син|Ас-Саффат|Сад|Аз-Зумар|Гафир|"
 "Фуссылят|Аш-Шура|Аз-Зухруф|Ад-Духан|Аль-Джасия|Аль-Ахкаф|Мухаммад|Аль-Фатх|Аль-Худжурат|Каф|Аз-Зарийат|Ат-Тур|Ан-Наджм|Аль-Камар|Ар-Рахман|Аль-Вакиа|Аль-Хадид|Аль-Муджадала|"
 "Аль-Хашр|Аль-Мумтахана|Ас-Сафф|Аль-Джумуа|Аль-Мунафикун|Ат-Тагабун|Ат-Талак|Ат-Тахрим|Аль-Мульк|Аль-Калам|Аль-Хакка|Аль-Мааридж|Нух|Аль-Джинн|Аль-Музаммиль|Аль-Муддассир|"
 "Аль-Кыяма|Аль-Инсан|Аль-Мурсалят|Ан-Наба|Ан-Назиат|Абаса|Ат-Таквир|Аль-Инфитар|Аль-Мутаффифин|Аль-Иншикак|Аль-Бурудж|Ат-Тарик|Аль-Аля|Аль-Гашия|Аль-Фаджр|Аль-Баляд|"
 "Аш-Шамс|Аль-Лейль|Ад-Духа|Аш-Шарх|Ат-Тин|Аль-Алак|Аль-Кадр|Аль-Баййина|Аз-Залзаля|Аль-Адият|Аль-Кариа|Ат-Такясур|Аль-Аср|Аль-Хумаза|Аль-Филь|Курайш|Аль-Маун|Аль-Кавсар|"
 "Аль-Кафирун|Ан-Наср|Аль-Масад|Аль-Ихляс|Аль-Фалак|Ан-Нас").split("|")
assert len(RU_NAMES) == 114

def get(url):
    with urllib.request.urlopen(url, timeout=120) as r:
        return json.load(r)

db = sqlite3.connect("hadith.db")
db.executescript("""
DROP TABLE IF EXISTS docs; DROP TABLE IF EXISTS fts; DROP TABLE IF EXISTS surahs; DROP TABLE IF EXISTS sections;
CREATE TABLE docs(id INTEGER PRIMARY KEY, kind TEXT, source TEXT, ref TEXT, key TEXT, num REAL, sec INTEGER, lang TEXT, grade TEXT, text TEXT);
CREATE TABLE surahs(n INTEGER PRIMARY KEY, ar TEXT, ru TEXT, en TEXT, count INTEGER, type TEXT);
CREATE TABLE sections(source TEXT, lang TEXT, sec INTEGER, name TEXT);
CREATE VIRTUAL TABLE fts USING fts5(text, content='docs', content_rowid='id', tokenize='unicode61 remove_diacritics 2');
""")

def add(kind, source, ref, key, num, sec, lang, grade, text):
    if text and text.strip():
        db.execute("INSERT INTO docs(kind,source,ref,key,num,sec,lang,grade,text) VALUES(?,?,?,?,?,?,?,?,?)",
                   (kind, source, ref, key, num, sec, lang, grade, text.strip()))

def strip_bismillah(text):
    """В арабском тексте alquran.cloud басмала бывает приклеена к 1-му аяту суры. Убираем её."""
    plain = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn").replace("\u0671", "\u0627")
    words = text.split()
    if plain.split()[:4] == ["بسم", "الله", "الرحمن", "الرحيم"] and len(words) > 4:
        return " ".join(words[4:])
    return text

def parse_sections(data):
    """Названия глав и диапазоны номеров хадисов. Формат источника может отличаться, поэтому разбор терпимый."""
    meta = data.get("metadata") or {}
    names, ranges = {}, []
    sec = meta.get("section")
    if isinstance(sec, dict):
        for k, v in sec.items():
            if isinstance(v, str) and v.strip() and str(k).strip().isdigit():
                names[int(k)] = v.strip()
    det = meta.get("section_detail")
    if isinstance(det, dict):
        for k, d in det.items():
            try: ranges.append((int(k), float(d["hadithnumber_first"]), float(d["hadithnumber_last"])))
            except (KeyError, TypeError, ValueError): pass
    return names, ranges

for key, name in COLLECTIONS.items():
    for lang in LANGS:
        ed = f"{lang}-{key}"
        try:
            data = get(HADITH_CDN.format(ed))
        except Exception as e:
            print(f"  пропуск {ed}: {e}"); continue
        names, ranges = parse_sections(data)
        for k, v in names.items():
            db.execute("INSERT INTO sections VALUES(?,?,?,?)", (name, lang[:2], k, v))
        n = withsec = 0
        for h in data.get("hadiths", []):
            grades = "; ".join(f'{g.get("grade")} ({g.get("name")})' for g in h.get("grades", []))
            ref = f'№{h.get("hadithnumber")}'
            try: num = float(h.get("hadithnumber"))
            except (TypeError, ValueError): num = None
            sec = (h.get("reference") or {}).get("book")
            if not isinstance(sec, int) and num is not None:
                for s_, a_, b_ in ranges:
                    if a_ <= num <= b_: sec = s_; break
            if isinstance(sec, int): withsec += 1
            add("hadith", name, ref, ref, num, sec if isinstance(sec, int) else None, lang[:2], grades, h.get("text"))
            n += 1
        print(f"{ed}: {n} (глав с названиями: {len(names)}, хадисов с главой: {withsec})")

for lang, ed in QURAN.items():
    try:
        data = get(f"https://api.alquran.cloud/v1/quran/{ed}")["data"]["surahs"]
    except Exception as e:
        print(f"  пропуск Корана {ed}: {e}"); continue
    n = 0
    for s in data:
        db.execute("INSERT OR REPLACE INTO surahs VALUES(?,?,?,?,?,?)",
                   (s["number"], s["name"] if lang == "ar" else None, RU_NAMES[s["number"] - 1], s["englishName"], len(s["ayahs"]), s["revelationType"]))
        for a in s["ayahs"]:
            key = f'{s["number"]}:{a["numberInSurah"]}'
            txt = a["text"]
            if lang == "ar" and a["numberInSurah"] == 1 and s["number"] not in (1, 9):
                txt = strip_bismillah(txt)
            add("quran", "Коран", f'{key} ({s["englishName"]})', key, a["numberInSurah"], s["number"], lang, "", txt); n += 1
    print(f"Коран {ed}: {n}")

db.execute("INSERT INTO fts(rowid,text) SELECT id,text FROM docs")
db.execute("CREATE INDEX idx_key ON docs(kind,source,lang,key)")
db.execute("CREATE INDEX idx_sec ON docs(source,lang,sec,num)")
db.commit(); db.close()
print("Готово: hadith.db")
