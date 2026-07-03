"""İsimden cinsiyet tahmini — tamamen çevrimdışı.

İki kaynak, öncelik sırasıyla:
1. Paket içi Türkçe ek sözlük (``_SUPPLEMENT_K`` / ``_SUPPLEMENT_E``):
   gender_guesser'ın eski sözlüğünde olmayan modern isimler (Sude, Ecrin,
   Eymen...) ve yanlış bildiği isimler (Miraç) için elle derlenmiş liste.
2. ``gender_guesser`` paketi (Jörg Michael'ın uluslararası isim sözlüğü,
   'turkey' frekanslarıyla).

Öğrenci isimleri hiçbir zaman dışarı gönderilmez (harici API kullanılmaz).

Not: Python'un ``str.lower()``'ı Türkçe 'İ'yi 'i̇' (i + birleşik nokta)
yapar ve sözlük eşleşmesini bozar; bu yüzden ``tr_lower`` şart.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "AUTO_FILL_CONFIDENCE",
    "GenderGuess",
    "fill_missing_genders",
    "guess_gender",
    "tr_lower",
]

# Bu kesinliğin altındaki tahminler otomatik uygulanmaz; kullanıcıya sorulur.
AUTO_FILL_CONFIDENCE = 0.8


@dataclass(frozen=True)
class GenderGuess:
    gender: str  # "K" / "E" / "" (bilinmiyor ya da iki cinste de kullanılıyor)
    confidence: float  # 0.0–1.0
    source: str = ""  # "sözlük" / "gender_guesser" / ""

    @property
    def percent(self) -> str:
        return f"%{round(self.confidence * 100)}" if self.confidence else "—"


def tr_lower(s: str) -> str:
    """Türkçe'ye uygun küçük harf: İ→i, I→ı."""
    return s.replace("İ", "i").replace("I", "ı").lower()


# --------------------------------------------------------------------------
# Türkçe ek sözlük. Yalnız cinsiyeti Türkiye'de fiilen tek olan isimler
# eklenir; iki cinste de kullanılanlar (Deniz, Kayra...) _AMBIGUOUS'a gider.
# --------------------------------------------------------------------------

_SUPPLEMENT_K = {
    # modern / yeni kuşak
    "sude", "sudenaz", "ecrin", "tuana", "nisanur", "hiranur", "buğlem",
    "ikra", "esila", "asel", "duru", "miray", "mira", "lina", "öykü",
    "masal", "zümra", "elanur", "edanur", "eslem", "belinay", "aysima",
    "ceylin", "alya", "arya", "aybüke", "bengisu", "beril", "berra",
    "ebrar", "ravza", "serra", "sevde", "şevval", "vuslat", "nurbanu",
    "aleyna", "ilayda", "aylin", "alina", "eylül", "nehir", "nisan",
    "mina", "naz", "nazlı", "nilsu", "azra", "hüma", "liya", "melisa",
    "melis", "defne", "ela", "lara", "maya", "elifsu",
    "zeynepsu", "esmanur", "rümeysa", "rüveyda", "mihrimah", "simay",
    "tuğçe", "irmak", "pelinsu", "selin", "selen", "sıla", "sena",
    "senanur", "fatmanur", "zehranur", "eflin", "elvin", "alara",
    # klasik
    "hatice", "elif", "emine", "meryem", "zehra", "havva", "hilal",
    "kübra", "büşra", "esra", "betül", "şeyma", "sultan", "medine",
    "rabia", "nisa", "yasemin", "gamze", "gizem", "damla", "dilara",
    "cansu", "ceyda", "ecem", "eda", "feyza", "hazal", "helin", "ipek",
    "leyla", "melek", "meltem", "merve", "mihriban", "müberra", "nesibe",
    "neslihan", "nilay", "rana", "rüya", "sevgi", "sinem", "songül",
    "şule", "tuba", "tuğba", "hümeyra", "berfin", "buse", "beyza",
    "aslı", "asude", "bahar", "amine", "ayşegül", "aysel", "gül",
    "gülsüm", "hayrunnisa", "iclal", "kumsal", "beren", "ceren", "pelin",
    "pınar", "seda", "sedanur", "semanur", "sevil", "sevilay", "sibel",
    "simge", "tansu", "yaprak", "zeliha", "şükran", "saliha", "halime",
    "hanife", "fadime", "döndü", "dilek", "derya", "burcu", "aybike",
    "ırmak", "irmak", "gülzade", "safura", "reyhan", "sevcan", "nurcan",
    "gülcan", "irem", "nurhan", "gülhan", "neslişah",
    # gerçek listelerden eklenenler
    "hira", "kader", "maria", "nurseza", "sahra", "selinay", "duygu",
    # klasik (genişletme)
    "ayşe", "fatma", "zeynep", "hacer", "huriye", "şerife", "cemile",
    "naciye", "nazife", "nuriye", "sabriye", "safiye", "sakine", "satı",
    "selvi", "semiha", "sevim", "suna", "süheyla", "şadiye", "şenay",
    "şengül", "şermin", "türkan", "ümmühan", "vesile", "yeter", "zarife",
    "zekiye", "zübeyde", "zülal", "gülay", "gülbahar", "gülçin", "gülden",
    "güler", "gülfidan", "gülizar", "gülseren", "gülsen", "gülsün",
    "gülten", "gonca", "hale", "halide", "hamide", "hamiyet", "hazan",
    "hediye", "hicran", "inci", "kadriye", "kamile", "kevser", "kezban",
    "lale", "latife", "leman", "lütfiye", "makbule", "mediha", "melahat",
    "melda", "melike", "meral", "mesude", "muazzez", "mukaddes",
    "mübeccel", "müge", "münevver", "münire", "müzeyyen", "nadide",
    "nadire", "nagihan", "nalan", "naile", "nazan", "nazmiye", "nebahat",
    "necla", "necmiye", "nergis", "neriman", "nermin", "nevin", "nezahat",
    "nezaket", "nezihe", "nigar", "nihal", "nilgün", "nilüfer", "nimet",
    "nur", "nuran", "nuray", "nurdan", "nurhayat", "nursel", "nursen",
    "nurten", "oya", "perihan", "pembe", "pervin", "rahime", "raziye",
    "refika", "remziye", "rukiye", "saadet", "sabahat", "sabiha", "saime",
    "sanem", "saniye", "seçil", "seher", "selma", "sema", "semra",
    "serap", "serpil", "sevda", "sevinç", "sıdıka", "suzan", "sümeyye",
    "sümeyra", "şaziye", "şükriye", "tülay", "tülin", "ulviye", "vahide",
    "vildan", "yeliz", "yeşim", "yonca", "zahide", "zerrin", "zuhal",
    "zümrüt", "şirin", "berna", "belgin", "bengü", "berrin", "binnaz",
    "birsen", "buket", "canan", "çiçek", "çiğdem", "didem", "dilan",
    "dilay", "ebru", "elmas", "emel", "esin", "esma", "fahriye",
    "fatoş", "fazilet", "feride", "feriha", "fidan", "figen", "fikriye",
    "filiz", "firdevs", "fulya", "funda", "gaye", "güzide", "hülya",
    "işıl", "jale", "kıymet", "mine", "nazire", "özlem",
    # modern (genişletme)
    "cemre", "çisem", "ece", "efsun", "melisa", "melissa", "neva",
    "nefes", "umay", "yağmur", "asya", "almila", "elis", "karya",
    "lidya", "mislina", "talia", "yüsra", "zilan",
}

_SUPPLEMENT_E = {
    # modern / yeni kuşak
    "eymen", "miraç", "poyraz", "aras", "atlas", "kuzey", "çınar",
    "göktuğ", "alperen", "alparslan", "demir", "rüzgar", "yağız",
    "metehan", "tunahan", "batuhan", "berkay", "berke", "doruk",
    "egemen", "ensar", "asaf", "aybars", "boran", "buğra", "sarp",
    "atakan", "bartu", "gökay", "görkem", "doğukan", "muhammed",
    "muhammet", "emirhan", "emir", "yiğit", "kerem", "berat", "taha",
    "hamza", "bilal", "talha", "yasin", "enes", "furkan", "arda",
    "utku", "umutcan", "efekan",
    "erenay", "toprak", "aren", "ataberk", "kağan", "tuğra",
    # klasik
    "ismail", "ibrahim", "halil", "harun", "hüseyin", "hasan", "ahmet",
    "mehmet", "mustafa", "ömer", "osman", "ali", "veli", "yusuf",
    "yunus", "yakup", "yahya", "musa", "salih", "samet", "selim",
    "sinan", "süleyman", "recep", "ramazan", "kadir", "kaan", "kemal",
    "levent", "mahmut", "melih", "mert", "murat", "oğuz", "oğuzhan",
    "okan", "onur", "orhan", "ozan", "sefa", "serkan", "şahin",
    "tarık", "tolga", "tugay", "turan", "ufuk", "volkan", "yavuz",
    "zafer", "abdullah", "abdurrahman", "adem", "alp", "arif", "aykut",
    "baran", "barış", "bekir", "burak", "can", "caner", "cem", "cemal",
    "cengiz", "cihan", "davut", "emin", "emre", "eren", "erhan", "erdem",
    "erol", "ethem", "fatih", "ferhat", "hakan", "idris", "ilyas",
    "mikail", "necati", "nihat", "raşit", "sadık", "şevket", "türker",
    "ünal", "efe", "ege", "umut", "tuna", "batu", "koray", "serhat",
    "sercan", "gökhan", "gürkan", "hayati", "muhsin", "nurettin",
    "osama", "usame", "gültekin",
    # gerçek listelerden eklenenler
    "seymen", "keremcem",
    # klasik (genişletme)
    "adnan", "akif", "altan", "asım", "aslan", "ata", "atalay", "atilla",
    "aydın", "aziz", "bahadır", "bahri", "bayram", "behçet", "beytullah",
    "bora", "bülent", "burhan", "cafer", "cahit", "celal", "cemil",
    "cevdet", "cevat", "cihangir", "coşkun", "cumali", "çağatay",
    "çağlar", "çetin", "derviş", "doğan", "dursun", "ediz", "ekrem",
    "emrah", "emrullah", "engin", "enver", "ercan", "erdal", "erdinç",
    "erkan", "erkin", "erman", "ersin", "ertan", "ertuğrul", "esat",
    "eşref", "eyüp", "faruk", "fazıl", "fehmi", "ferdi", "feridun",
    "ferit", "fevzi", "fırat", "fikret", "fuat", "galip", "gazi",
    "göktürk", "gündüz", "güven", "habil", "hakkı", "halim", "halit",
    "haluk", "hamdi", "hamit", "haşim", "hayrettin", "haydar", "hayri",
    "hızır", "hilmi", "hüsamettin", "hüsnü", "ilhan", "ilhami", "irfan",
    "isa", "ishak", "izzet", "kamil", "kasım", "kenan", "kerim",
    "kubilay", "latif", "lokman", "lütfi", "mazlum", "mecit", "mesut",
    "mete", "mithat", "muammer", "muharrem", "muhittin", "murtaza",
    "musab", "mücahit", "müslüm", "naci", "nadir", "namık", "nazım",
    "necdet", "necip", "nedim", "nevzat", "niyazi", "numan", "nurullah",
    "oktay", "orçun", "öner", "özcan", "özkan", "polat", "rafet",
    "rahim", "rahmi", "ramiz", "rasim", "rauf", "refik", "remzi",
    "resul", "rıdvan", "rıfat", "rıza", "ruhi", "rüştü", "sabahattin",
    "sabri", "sadettin", "saffet", "sait", "salim", "savaş", "sedat",
    "selahattin", "selami", "semih", "seyfettin", "seyfi", "seyit",
    "sezai", "sıtkı", "suat", "şaban", "şakir", "şamil", "şenol",
    "şeref", "şevki", "şükrü", "tacettin", "tahir", "tahsin", "talat",
    "talip", "tamer", "tanju", "tarkan", "tayfun", "tekin", "temel",
    "tevfik", "tuncay", "tuncer", "turgay", "turgut", "uğur", "ulaş",
    "vedat", "vehbi", "veysel", "veysi", "yalçın", "yaman", "yılmaz",
    "zekeriya", "zeki", "ziya", "zübeyir", "adil", "akın", "bedri",
    "birol", "cemalettin", "ercüment", "erdi", "habib",
    # modern (genişletme)
    "alaz", "altay", "batıkan", "bertuğ", "çağan", "çağrı", "kutay",
    "onat", "taner", "timur", "tuğrul", "yamaç",
}

# Türkiye'de iki cinste de yaygın kullanılan isimler: tahmin verilmez,
# kesinlik 0.5 ile kullanıcıya bırakılır.
_AMBIGUOUS = {
    "deniz", "kayra", "derin", "doğa", "evren", "özgür", "iraz",
    "ezel", "ömür", "ilkay", "olcay", "günay", "hikmet", "yücel",
    "bilge", "gökçe", "esen", "devrim", "şafak",
    "aytaç", "beyhan", "göksel", "servet", "yüksel",
}

_GG_CONFIDENCE = {
    "female": ("K", 0.90),
    "male": ("E", 0.90),
    "mostly_female": ("K", 0.70),
    "mostly_male": ("E", 0.70),
    "andy": ("", 0.50),
    "unknown": ("", 0.0),
}

_detector = None


def _gg_detector():
    global _detector
    if _detector is None:
        import gender_guesser.detector as gg

        _detector = gg.Detector(case_sensitive=False)
    return _detector


# Bileşik isim ekleri: ada eklendiğinde cinsiyeti belirler
# ("ÇAĞLANUR" → K, "METEHAN" → E). Kök en az 2 harf olmalı ki "ONUR"
# gibi bağımsız isimler yanlışlıkla ayrıştırılmasın.
_FEMALE_SUFFIXES = ("nur", "naz", "gül", "su")
_MALE_SUFFIXES = ("han", "berk", "alp")


def _dict_lookup(t: str) -> GenderGuess:
    """Ek sözlük + gender_guesser (bileşik ayrıştırma yok)."""
    if t in _AMBIGUOUS:
        return GenderGuess("", 0.5, "sözlük")
    if t in _SUPPLEMENT_K:
        return GenderGuess("K", 0.95, "sözlük")
    if t in _SUPPLEMENT_E:
        return GenderGuess("E", 0.95, "sözlük")
    d = _gg_detector()
    # gender_guesser sözlüğü kendi anahtarlarını str.lower() ile küçültür;
    # Türkçe İ'li isimler orada 'i̇' (i + birleşik nokta) olarak durur.
    # Bu yüzden her iki küçültme de denenir.
    variants = [t]
    dotted = t.replace("i", "i̇")  # tr_lower(İREM)="irem" → sözlükte "i̇rem"
    if dotted != t:
        variants.append(dotted)
    ascii_i = t.replace("ı", "i")  # IRMAK: sözlükte ASCII "irmak" olabilir
    if ascii_i != t:
        variants.append(ascii_i)
    for v in variants:
        verdict = d.get_gender(v, "turkey")
        if verdict == "unknown":
            verdict = d.get_gender(v)  # ülke frekansı yoksa genel sözlük
        if verdict != "unknown":
            gender, conf = _GG_CONFIDENCE[verdict]
            return GenderGuess(gender, conf, "gender_guesser" if conf else "")
    return GenderGuess("", 0.0)


def _lookup(token: str) -> GenderGuess:
    """Tek bir ad için kaynaklara sırayla bakar."""
    t = tr_lower(token).strip(".-")
    if not t:
        return GenderGuess("", 0.0)
    g = _dict_lookup(t)
    if g.confidence:
        return g
    # bileşik isimler: ek + kök ayrıştırması
    for suf in _FEMALE_SUFFIXES:
        if t.endswith(suf) and len(t) - len(suf) >= 2:
            return GenderGuess("K", 0.85, "bileşik")
    for suf in _MALE_SUFFIXES:
        if t.endswith(suf) and len(t) - len(suf) >= 2:
            return GenderGuess("E", 0.75, "bileşik")
    if t.endswith("can") and len(t) > 5:
        root = _dict_lookup(t[:-3])
        if root.gender:  # MAHMUTCAN → mahmut → E; GÜLCAN → gül → K
            return GenderGuess(root.gender, 0.85, "bileşik")
        return GenderGuess("E", 0.6, "bileşik")  # -can çoğunlukla erkek
    # MUHAMMEDSAİT, MUHAMMETALİ, ABDULSAMET... → erkek bileşikleri
    for pre in ("muhammed", "muhammet", "abdul", "abdür", "mehmetali"):
        if t.startswith(pre) and len(t) > len(pre):
            return GenderGuess("E", 0.9, "bileşik")
    return GenderGuess("", 0.0)


def guess_gender(full_name: str) -> GenderGuess:
    """Ad soyaddan cinsiyet tahmini.

    Son kelime soyad sayılır; kalan ad kelimeleri sırayla denenir
    ("AYŞE NUR YILMAZ" → ayşe, nur, ayşenur). En güvenli sonuç döner.
    """
    tokens = [t for t in re.split(r"[\s\-]+", full_name.strip()) if t]
    if not tokens:
        return GenderGuess("", 0.0)
    given = tokens[:-1] if len(tokens) > 1 else tokens
    candidates = list(given)
    if len(given) > 1:
        candidates.append("".join(given))  # "nisa nur" → "nisanur" gibi
    best = GenderGuess("", 0.0)
    for i, cand in enumerate(candidates):
        g = _lookup(cand)
        if i > 0 and g.confidence:
            # ikincil adla eşleşme birincil kadar güvenilir değildir
            g = GenderGuess(g.gender, round(g.confidence * 0.95, 2), g.source)
        if g.confidence >= 0.9:
            return g
        if g.confidence > best.confidence:
            best = g
    return best


def fill_missing_genders(students, threshold: float = AUTO_FILL_CONFIDENCE):
    """Cinsiyeti boş öğrencileri tahminle doldurur (yerinde değiştirir).

    Dönüş: (doldurulanlar, kalanlar) — her ikisi de (öğrenci, tahmin)
    çiftleri. Kesinliği eşiğin altında kalanlar DOLDURULMAZ; kullanıcı
    girdisi beklenir.
    """
    filled, remaining = [], []
    for s in students:
        if s.gender:
            continue
        g = guess_gender(s.full_name)
        if g.gender and g.confidence >= threshold:
            s.gender = g.gender
            filled.append((s, g))
        else:
            remaining.append((s, g))
    return filled, remaining
