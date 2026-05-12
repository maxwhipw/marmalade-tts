"""
TTS text preprocessing — normalize text for spoken synthesis.

Each rule is a named regex transformation. Rules are composed into profiles
per engine, so engines that handle certain patterns natively can skip those rules.

Architecture:
  - Rules are defined once (regex + replacement function)
  - Engine profiles list which rules to apply
  - Config can override per-engine: engines.<name>.preprocessing: [rule1, rule2, ...]
  - Global toggle: --preprocessing / --no-preprocessing
  - Default: enabled, using engine-specific profile

Uses num2words (already installed as a dep of kittentts) for number verbalization.
"""

import re

try:
    from num2words import num2words
except ImportError:
    num2words = None

# ── Rule definitions ─────────────────────────────────────────────────────────
# Each rule: (name, description, regex_pattern, replacement_function)
# replacement_function takes a re.Match and returns a string.

def _currency(m: re.Match) -> str:
    """$100 → 100 dollars, $3.50 → 3 dollars and 50 cents, £42 → 42 pounds."""
    symbols = {"$": ("dollar", "cent"), "£": ("pound", "penny"), "€": ("euro", "cent"), "¥": ("yen", "")}
    sym = m.group(1)
    amount = m.group(2)
    major_name, minor_name = symbols.get(sym, ("units", ""))

    if "." in amount:
        major, minor = amount.split(".", 1)
        major = int(major) if major else 0
        minor = int(minor) if minor else 0
        parts = []
        if major:
            parts.append(f"{major} {major_name}{'s' if major != 1 else ''}")
        if minor and minor_name:
            parts.append(f"{minor} {minor_name}{'s' if minor != 1 else ''}")
        return " and ".join(parts) if parts else amount
    else:
        n = int(amount)
        return f"{n} {major_name}{'s' if n != 1 else ''}"


def _number_to_words(m: re.Match) -> str:
    """42 → forty-two, 1000 → one thousand. Uses num2words if available."""
    num_str = m.group(0)
    if num2words is None:
        return num_str
    try:
        if "." in num_str:
            # Verbalize decimal: "99.5" → "ninety-nine point five"
            whole, frac = num_str.split(".", 1)
            whole_w = num2words(int(whole)) if whole else "zero"
            frac_w = " ".join(num2words(int(d)) for d in frac)
            return f"{whole_w} point {frac_w}"
        n = int(num_str)
        # Don't verbalize years (4-digit numbers 1900-2099) when standalone
        if 1900 <= n <= 2099:
            return num_str
        return num2words(n)
    except Exception:
        return num_str


def _ordinal(m: re.Match) -> str:
    """1st → first, 2nd → second, 23rd → twenty-third."""
    num = int(m.group(1))
    if num2words is None:
        return m.group(0)
    try:
        return num2words(num, to="ordinal")
    except Exception:
        return m.group(0)


def _percentage(m: re.Match) -> str:
    """50% → 50 percent."""
    return m.group(1) + " percent"


def _filename(m: re.Match) -> str:
    """example.txt → example dot T X T, config.yaml → config dot Y A M L.
    Only matches when the extension looks like a real file extension."""
    name, ext = m.group(1), m.group(2)
    # Skip if it looks like a decimal number or abbreviation
    if name.isdigit():
        return m.group(0)
    # Common file extensions
    known_exts = {
        "txt", "pdf", "doc", "docx", "xls", "xlsx", "csv", "json", "yaml", "yml",
        "xml", "html", "htm", "css", "js", "ts", "py", "rb", "go", "rs", "java",
        "cpp", "hpp", "c", "h", "sh", "bash", "zsh", "fish", "bat", "ps1",
        "md", "rst", "tex", "log", "conf", "cfg", "ini", "toml",
        "png", "jpg", "jpeg", "gif", "svg", "webp", "bmp", "ico",
        "mp3", "wav", "ogg", "flac", "aac", "m4a",
        "mp4", "mkv", "avi", "mov", "webm",
        "zip", "tar", "gz", "bz2", "xz", "rar", "7z",
        "exe", "msi", "deb", "rpm", "apk", "dmg",
        "sql", "db", "sqlite",
        "onnx", "pt", "bin", "safetensors",
    }
    if ext.lower() not in known_exts:
        return m.group(0)
    spelled = " ".join(ext.upper())
    return f"{name} dot {spelled}"


def _abbreviation(m: re.Match) -> str:
    """U.S.A. → U S A, e.g. → for example."""
    text = m.group(0)
    common = {
        "e.g.": "for example", "i.e.": "that is", "etc.": "et cetera",
        "vs.": "versus", "mr.": "mister", "mrs.": "missus", "ms.": "miss",
        "dr.": "doctor", "sr.": "senior", "jr.": "junior",
        "st.": "saint", "ft.": "feet", "lb.": "pounds", "oz.": "ounces",
    }
    lower = text.lower()
    if lower in common:
        return common[lower]
    # Spell out dot-separated abbreviations: U.S.A. → U S A
    letters = text.replace(".", "")
    if letters.isupper() and len(letters) <= 6:
        return " ".join(letters)
    return text


def _time(m: re.Match) -> str:
    """10:30 → ten thirty, 3:00 PM → three PM, 14:00 → fourteen hundred."""
    hour = int(m.group(1))
    minute = int(m.group(2))
    suffix = (m.group(3) or "").strip()

    if num2words is None:
        return m.group(0)

    try:
        h = num2words(hour)
        if minute == 0:
            if suffix:
                return f"{h} {suffix}"
            if hour >= 13:
                return f"{h} hundred"
            return f"{h} o'clock"
        if minute < 10:
            mi = "oh " + num2words(minute)
        else:
            mi = num2words(minute)
        return f"{h} {mi}" + (f" {suffix}" if suffix else "")
    except Exception:
        return m.group(0)


def _date_slash(m: re.Match) -> str:
    """01/15/2025 → January fifteenth, 2025."""
    months = ["January", "February", "March", "April", "May", "June",
              "July", "August", "September", "October", "November", "December"]
    month = int(m.group(1))
    day = int(m.group(2))
    year = m.group(3)  # keep year as digits
    if 1 <= month <= 12:
        month_name = months[month - 1]
        if num2words:
            day_str = num2words(day, to="ordinal")
        else:
            day_str = str(day)
        return f"{month_name} {day_str}, {year}"
    return m.group(0)


def _url(m: re.Match) -> str:
    """https://example.com → example dot com."""
    domain = m.group(2)
    parts = domain.split(".")
    return " dot ".join(parts)


def _email(m: re.Match) -> str:
    """user@example.com → user at example dot com."""
    user, domain = m.group(1), m.group(2)
    domain_spoken = " dot ".join(domain.split("."))
    return f"{user} at {domain_spoken}"


def _math_symbols(m: re.Match) -> str:
    """Replace standalone math symbols with words.
    Only matches when surrounded by spaces or at string boundaries
    to avoid mangling hyphens in compound words like 'ninety-nine'."""
    symbols = {"+": "plus", "×": "times", "÷": "divided by",
               "=": "equals", "≠": "not equal to", "<": "less than",
               ">": "greater than", "≤": "less than or equal to",
               "≥": "greater than or equal to", "±": "plus or minus"}
    return symbols.get(m.group(1), m.group(1))


def _ampersand(m: re.Match) -> str:
    """& → and."""
    return " and "


def _hashtag(m: re.Match) -> str:
    """#100 → number 100, #hello → hashtag hello."""
    text = m.group(1)
    if text.isdigit():
        return f"number {text}"
    return f"hashtag {text}"


# ── Rule registry ────────────────────────────────────────────────────────────

RULES = {
    "currency":      (r"([$£€¥])(\d+(?:\.\d{1,2})?)", _currency,
                      "Expand currency: $100 → 100 dollars"),
    "percentage":    (r"(\d+(?:\.\d+)?)%", _percentage,
                      "Expand percent: 50% → 50 percent"),
    "ordinal":       (r"\b(\d+)(?:st|nd|rd|th)\b", _ordinal,
                      "Expand ordinals: 1st → first"),
    "time":          (r"\b(\d{1,2}):(\d{2})\s*(AM|PM|am|pm|a\.m\.|p\.m\.)?\b", _time,
                      "Expand times: 10:30 → ten thirty"),
    "date":          (r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", _date_slash,
                      "Expand dates: 01/15/2025 → January 15th, 2025"),
    "email":         (r"\b([a-zA-Z0-9_.+-]+)@([a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)\b", _email,
                      "Expand emails: user@example.com → user at example dot com"),
    "url":           (r"https?://(www\.)?([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})[^\s]*", _url,
                      "Expand URLs: https://example.com → example dot com"),
    "filename":      (r"\b(\w+)\.([a-zA-Z]{1,5})\b", _filename,
                      "Expand filenames: example.txt → example dot T X T"),
    "abbreviation":  (r"\b(?:[A-Z]\.){2,}|(?:e\.g\.|i\.e\.|etc\.|vs\.|[Mm]r\.|[Mm]rs\.|[Mm]s\.|[Dd]r\.|[Ss]r\.|[Jj]r\.|[Ss]t\.|ft\.|lb\.|oz\.)", _abbreviation,
                      "Expand abbreviations: U.S.A. → U S A, e.g. → for example"),
    "number":        (r"\b\d+(?:\.\d+)?\b", _number_to_words,
                      "Numbers to words: 42 → forty-two"),
    "math":          (r"(?<=\s)([+×÷=≠<>≤≥±])(?=\s)", _math_symbols,
                      "Math symbols to words: + → plus (only when standalone)"),
    "ampersand":     (r"\s&\s", _ampersand,
                      "Ampersand: & → and"),
    "hashtag":       (r"#(\w+)", _hashtag,
                      "Hashtags: #100 → number 100"),
}

# ── Engine default profiles ──────────────────────────────────────────────────
# Which rules each engine needs. Engines that already handle certain patterns
# internally should skip those rules.

ENGINE_PROFILES = {
    "kitten": [
        "currency", "percentage", "ordinal", "time", "date",
        "email", "url", "filename", "abbreviation", "number",
        "math", "ampersand", "hashtag",
    ],
    "kokoro": [
        # Kokoro (via misaki) handles numbers, abbreviations, and some symbols natively
        "currency", "percentage", "time", "date",
        "email", "url", "filename",
        "math", "ampersand", "hashtag",
    ],
    "piper": [
        # Piper handles almost nothing — needs everything
        "currency", "percentage", "ordinal", "time", "date",
        "email", "url", "filename", "abbreviation", "number",
        "math", "ampersand", "hashtag",
    ],
    "coqui": [
        # Coqui handles basic numbers but not much else
        "currency", "percentage", "time", "date",
        "email", "url", "filename", "abbreviation",
        "math", "ampersand", "hashtag",
    ],
    "pocket": [
        # Pocket doesn't handle any text normalization natively
        "currency", "percentage", "ordinal", "time", "date",
        "email", "url", "filename", "abbreviation", "number",
        "math", "ampersand", "hashtag",
    ],
}


# ── Public API ───────────────────────────────────────────────────────────────

def list_rules():
    """Print all available preprocessing rules."""
    for name, (pattern, func, desc) in RULES.items():
        print(f"  {name:15s} — {desc}")


def preprocess(text: str, engine: str = None, rules: list = None) -> str:
    """Apply preprocessing rules to text.

    Args:
        text: Input text.
        engine: Engine name — selects the default profile.
        rules: Explicit list of rule names (overrides engine profile).

    Returns:
        Normalized text.
    """
    if rules is None:
        rules = ENGINE_PROFILES.get(engine, ENGINE_PROFILES["kitten"])

    # Apply rules in order. Order matters:
    # 1. URLs and emails first (before filename rule eats dots)
    # 2. Currency/percentage before numbers (so $100 isn't just "100")
    # 3. Numbers last (catch remaining bare numbers)
    priority = [
        "email", "url",                          # capture structured patterns first
        "currency", "percentage",                  # money/percent before generic numbers
        "time", "date", "ordinal",                 # temporal + ordinal before numbers
        "abbreviation",                             # abbreviations before filename (both have dots)
        "filename",                                 # filenames after abbreviations
        "number",                                   # bare numbers last
        "math", "ampersand", "hashtag",
    ]

    for rule_name in priority:
        if rule_name not in rules:
            continue
        if rule_name not in RULES:
            continue
        pattern, func, desc = RULES[rule_name]
        text = re.sub(pattern, func, text)

    return text
