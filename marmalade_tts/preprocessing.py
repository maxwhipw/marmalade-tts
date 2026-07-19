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

import html as _html
import os
import re

try:
    from num2words import num2words
except ImportError:
    num2words = None

try:
    import yaml
except ImportError:
    yaml = None

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
        "ex.": "for example",
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


def _emoji(_m: re.Match) -> str:
    """Strip emoji characters. Without this, espeak/phonemizer-backed engines
    verbalize them as their Unicode names ("loudly crying face", "rolling on
    the floor laughing", ...). Replaced with a single space; the final
    whitespace-collapse pass tidies up the result.

    NOT applied to the `emojivoice` engine: emojivoice consumes the emoji
    itself (it selects the emotional speaking style) and strips it later
    inside the engine.
    """
    return " "


# ── Markdown / HTML strippers ────────────────────────────────────────────────
# These are applied very early so downstream rules (url, email, number, …) see
# clean prose rather than syntax noise like "**" or "<p>". We do not attempt to
# be a full markdown parser — only the high-value cases that show up when a
# README or HTML snippet is piped into the engine.


# Image must come before link so ![alt](url) → alt (and not "!alt").
_MD_IMAGE      = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_MD_LINK       = re.compile(r"\[([^\]]+)\]\([^)]*\)")
# Bold/strike use **/__/~~ pairs. Italic with * or _ must avoid eating
# snake_case identifiers: require the underscore form to be at word
# boundaries and to wrap non-underscore content.
_MD_BOLD_STAR  = re.compile(r"\*\*([^*\n]+?)\*\*")
_MD_BOLD_UNDER = re.compile(r"(?<!\w)__([^_\n]+?)__(?!\w)")
_MD_STRIKE     = re.compile(r"~~([^~\n]+?)~~")
_MD_ITAL_STAR  = re.compile(r"(?<!\*)\*([^*\n]+?)\*(?!\*)")
_MD_ITAL_UNDER = re.compile(r"(?<!\w)_([^_\n]+?)_(?!\w)")

# Python dunder names — substituting them inside the bold-underscore rule
# would rewrite "__init__" to "init" in any README discussing dunders. The
# regex alone cannot distinguish "__init__" from "__hello__" markdown bold
# (same shape), so we keep a denylist of the well-known dunder identifiers.
# When the captured inner name is in this set, leave the whole "__name__"
# token alone.
_PYTHON_DUNDERS = frozenset({
    # Object protocol
    "init", "new", "del", "init_subclass", "subclasshook",
    "repr", "str", "bytes", "format", "hash", "bool", "dir", "sizeof",
    # Attribute access
    "getattr", "getattribute", "setattr", "delattr",
    # Class / module identity
    "class", "bases", "mro", "subclasses", "name", "qualname",
    "module", "doc", "dict", "slots", "weakref", "annotations",
    "package", "path", "file", "spec", "loader", "version", "author",
    "all", "main",
    # Comparison
    "eq", "ne", "lt", "le", "gt", "ge",
    # Numeric
    "add", "radd", "iadd", "sub", "rsub", "isub", "mul", "rmul", "imul",
    "truediv", "rtruediv", "itruediv", "floordiv", "rfloordiv", "ifloordiv",
    "mod", "rmod", "imod", "divmod", "rdivmod", "pow", "rpow", "ipow",
    "lshift", "rlshift", "ilshift", "rshift", "rrshift", "irshift",
    "and", "rand", "iand", "or", "ror", "ior", "xor", "rxor", "ixor",
    "neg", "pos", "abs", "invert", "round", "trunc", "floor", "ceil",
    "int", "float", "complex", "index",
    # Container / iterator
    "len", "length_hint", "getitem", "setitem", "delitem", "missing",
    "iter", "next", "reversed", "contains",
    # Callable / context / copy / pickle
    "call", "enter", "exit", "copy", "deepcopy",
    "reduce", "reduce_ex", "getstate", "setstate", "getnewargs",
    # Async
    "aiter", "anext", "aenter", "aexit", "await",
    # Descriptor
    "get", "set", "delete", "set_name",
})


def _bold_under_sub(m: "re.Match[str]") -> str:
    """Replacement for the bold-underscore rule. Leaves Python dunders
    (`__init__`, `__name__`, etc.) untouched; otherwise drops the wrapping
    `__` and returns the inner text."""
    inner = m.group(1)
    if inner in _PYTHON_DUNDERS:
        return m.group(0)
    return inner
# Triple-backtick fences (with or without language tag) — drop the fences,
# keep the content. Greedy across newlines.
_MD_FENCE      = re.compile(r"```[^\n`]*\n?(.*?)```", re.DOTALL)
_MD_CODE       = re.compile(r"`([^`\n]+?)`")
# Line-leading markers: headings, blockquotes, bullets.
_MD_HEADING    = re.compile(r"(?m)^[ \t]*#{1,6}[ \t]+")
_MD_BLOCKQUOTE = re.compile(r"(?m)^[ \t]*>[ \t]?")
_MD_BULLET     = re.compile(r"(?m)^[ \t]*[-*+][ \t]+")

_HTML_TAG      = re.compile(r"<[^>]+>")


def _markdown(text: str) -> str:
    """Strip markdown syntax, leaving the inner text. Not a full parser —
    handles the high-value cases that ruin TTS output when a README is piped
    in. Tolerant of unbalanced tokens."""
    # Images before links (![alt](url) would otherwise lose its leading "!").
    text = _MD_IMAGE.sub(r"\1", text)
    text = _MD_LINK.sub(r"\1", text)
    # Fenced code blocks before inline code so ``` doesn't get half-eaten by
    # the inline rule.
    text = _MD_FENCE.sub(r"\1", text)
    text = _MD_CODE.sub(r"\1", text)
    text = _MD_BOLD_STAR.sub(r"\1", text)
    text = _MD_BOLD_UNDER.sub(_bold_under_sub, text)
    text = _MD_STRIKE.sub(r"\1", text)
    text = _MD_ITAL_STAR.sub(r"\1", text)
    text = _MD_ITAL_UNDER.sub(r"\1", text)
    text = _MD_HEADING.sub("", text)
    text = _MD_BLOCKQUOTE.sub("", text)
    text = _MD_BULLET.sub("", text)
    return text


def _html_strip(text: str) -> str:
    """Strip HTML tags and decode entities. Tag-strip first (kills real tags),
    then unescape (handles literal &lt;, &amp;, &nbsp; etc. in the remaining
    text so they don't get round-tripped into a second strip pass)."""
    text = _HTML_TAG.sub(" ", text)
    text = _html.unescape(text)
    return text


# ── Pronunciation dictionary ─────────────────────────────────────────────────
# User-editable YAML at ~/.config/marmalade-tts/pronunciations.yaml. Loaded
# lazily on first use, cached for the rest of the process — restart marmalade
# to pick up edits.

PRONUNCIATIONS_PATH = os.path.expanduser(
    "~/.config/marmalade-tts/pronunciations.yaml"
)

_PRONUNCIATIONS: dict | None = None
_PRONOUNCE_RE: re.Pattern | None = None


def _load_pronunciations() -> tuple[dict, re.Pattern | None]:
    """Load the pronunciation dict and build the alternation regex once per
    process. Missing file, empty dict, or unavailable PyYAML → ({}, None) and
    the rule becomes a no-op."""
    global _PRONUNCIATIONS, _PRONOUNCE_RE
    if _PRONUNCIATIONS is not None:
        return _PRONUNCIATIONS, _PRONOUNCE_RE

    data: dict = {}
    if yaml is not None and os.path.isfile(PRONUNCIATIONS_PATH):
        try:
            with open(PRONUNCIATIONS_PATH) as f:
                loaded = yaml.safe_load(f) or {}
            if isinstance(loaded, dict):
                # Filter empty and non-string keys defensively. An empty
                # string key would compile to an alternation branch that
                # matches every zero-width position in the input, silently
                # garbling every utterance. PyYAML can also emit non-string
                # keys (ints, bools, None); coercing those with str() would
                # turn `None: foo` into a literal "None" substitution, which
                # the user almost certainly didn't intend.
                data = {
                    str(k): str(v)
                    for k, v in loaded.items()
                    if k and isinstance(k, str)
                }
        except Exception:
            data = {}

    _PRONUNCIATIONS = data
    if not data:
        _PRONOUNCE_RE = None
        return _PRONUNCIATIONS, _PRONOUNCE_RE

    # Sort longest-first so "marmalade-tts" wins over "marmalade".
    keys = sorted(data.keys(), key=len, reverse=True)
    alternation = "|".join(re.escape(k) for k in keys)
    # Boundaries widened from `\b` to `(?<![\w-])...(?![\w-])` so a key like
    # "marmalade-tts" doesn't match inside the compound "marmalade-tts-cli"
    # (Python's `\b` treats `-` as a non-word char and would otherwise
    # accept the boundary on both sides of the hyphen). Net effect: a
    # hyphenated key only substitutes when it stands alone as a whole
    # token. Users who want "kubectl-prod" or similar must add the longer
    # compound as its own key.
    _PRONOUNCE_RE = re.compile(
        rf"(?<![\w-])(?:{alternation})(?![\w-])", re.IGNORECASE
    )
    return _PRONUNCIATIONS, _PRONOUNCE_RE


def _pronounce(text: str) -> str:
    """Substitute whole-word, case-insensitive matches from the user
    pronunciation dictionary. Replacement is the dict value verbatim."""
    data, pattern = _load_pronunciations()
    if not pattern:
        return text
    lowered = {k.lower(): v for k, v in data.items()}

    def _replace(m: re.Match) -> str:
        return lowered.get(m.group(0).lower(), m.group(0))

    return pattern.sub(_replace, text)


# Emoji codepoint ranges, broad enough to catch faces, symbols, dingbats,
# flags (regional indicators), the zero-width joiner used in emoji sequences,
# variation selector-16, and the keycap combining mark.
_EMOJI_PATTERN = (
    "["
    "\U0001F300-\U0001FAFF"     # symbols & pictographs, emoticons, transport
    "☀-➿"             # misc symbols + dingbats
    "\U0001F1E6-\U0001F1FF"     # regional indicators (flag halves)
    "‍"                    # zero-width joiner (emoji sequences)
    "️"                    # variation selector-16
    "⃣"                    # combining enclosing keycap
    "]+"
)


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
    "abbreviation":  (r"\b(?:[A-Z]\.){2,}|\b(?:e\.g\.|i\.e\.|etc\.|vs\.|[Mm]r\.|[Mm]rs\.|[Mm]s\.|[Dd]r\.|[Ss]r\.|[Jj]r\.|[Ss]t\.|ft\.|lb\.|oz\.|ex\.)", _abbreviation,
                      "Expand abbreviations: U.S.A. → U S A, e.g. → for example"),
    "number":        (r"\b\d+(?:\.\d+)?\b", _number_to_words,
                      "Numbers to words: 42 → forty-two"),
    "math":          (r"(?<=\s)([+×÷=≠<>≤≥±])(?=\s)", _math_symbols,
                      "Math symbols to words: + → plus (only when standalone)"),
    "ampersand":     (r"\s&\s", _ampersand,
                      "Ampersand: & → and"),
    "hashtag":       (r"#(\w+)", _hashtag,
                      "Hashtags: #100 → number 100"),
    "emoji":         (_EMOJI_PATTERN, _emoji,
                      "Strip emojis (default on for every engine except emojivoice — "
                      "without this, espeak-backed engines verbalize them as "
                      "\"loudly crying face\" etc.)"),
    # Whole-text transforms. Pattern is None — dispatcher calls the function
    # directly with the full string instead of going through re.sub.
    "markdown":      (None, _markdown,
                      "Strip markdown formatting (bold/italic/code/link/heading/list/quote)"),
    "html":          (None, _html_strip,
                      "Strip HTML tags and decode entities (&amp; → &)"),
    "pronounce":     (None, _pronounce,
                      "User pronunciation dictionary "
                      "(~/.config/marmalade-tts/pronunciations.yaml)"),
}

# ── Engine default profiles ──────────────────────────────────────────────────
# Which rules each engine needs. Engines that already handle certain patterns
# internally should skip those rules.

ENGINE_PROFILES = {
    "kitten": [
        "markdown", "html",
        "currency", "percentage", "ordinal", "time", "date",
        "email", "url", "filename", "abbreviation", "number",
        "pronounce",
        "math", "ampersand", "hashtag", "emoji",
    ],
    "kokoro": [
        # Kokoro (via misaki) handles numbers, abbreviations, and some symbols natively
        "markdown", "html",
        "currency", "percentage", "time", "date",
        "email", "url", "filename",
        "pronounce",
        "math", "ampersand", "hashtag", "emoji",
    ],
    "piper": [
        # Piper handles almost nothing — needs everything
        "markdown", "html",
        "currency", "percentage", "ordinal", "time", "date",
        "email", "url", "filename", "abbreviation", "number",
        "pronounce",
        "math", "ampersand", "hashtag", "emoji",
    ],
    "coqui": [
        # Coqui handles basic numbers but not much else
        "markdown", "html",
        "currency", "percentage", "time", "date",
        "email", "url", "filename", "abbreviation",
        "pronounce",
        "math", "ampersand", "hashtag", "emoji",
    ],
    "pocket": [
        # Pocket doesn't handle any text normalization natively
        "markdown", "html",
        "currency", "percentage", "ordinal", "time", "date",
        "email", "url", "filename", "abbreviation", "number",
        "pronounce",
        "math", "ampersand", "hashtag", "emoji",
    ],
    "matcha": [
        # Matcha-TTS only phonemizes — it normalizes nothing, so apply everything.
        "markdown", "html",
        "currency", "percentage", "ordinal", "time", "date",
        "email", "url", "filename", "abbreviation", "number",
        "pronounce",
        "math", "ampersand", "hashtag", "emoji",
    ],
    "emojivoice": [
        # EmojiVoice runs on Matcha-TTS — also no native normalization.
        # NOTE: the "emoji" rule is INTENTIONALLY omitted — emojivoice consumes
        # the emotion emoji itself (parse_emoji in the engine maps it to the
        # speaker id and strips it). Stripping it here would force every
        # utterance to the neutral speaker.
        "markdown", "html",
        "currency", "percentage", "ordinal", "time", "date",
        "email", "url", "filename", "abbreviation", "number",
        "pronounce",
        "math", "ampersand", "hashtag",
    ],
    "api": [
        # Hosted models (Venice default = Kokoro) normalize numbers and
        # abbreviations natively — same profile as local kokoro.
        "markdown", "html",
        "currency", "percentage", "time", "date",
        "email", "url", "filename",
        "pronounce",
        "math", "ampersand", "hashtag", "emoji",
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
    # 0. Strip emoji first — they're disjoint from every other rule's regex
    #    range, but stripping early keeps later debug output readable.
    # 1. Markdown + HTML next — strip formatting before the URL rule sees a
    #    [text](https://example.com) link target, before the number rule
    #    chokes on `**2**`, etc.
    # 2. URLs and emails before filename rule eats dots
    # 3. Currency/percentage before numbers (so $100 isn't just "100")
    # 4. Numbers last (catch remaining bare numbers)
    priority = [
        "emoji",                                    # strip emoji first
        "markdown", "html",                       # strip formatting before URL/number rules
        "email", "url",                          # capture structured patterns first
        "currency", "percentage",                  # money/percent before generic numbers
        "time", "date", "ordinal",                 # temporal + ordinal before numbers
        "abbreviation",                             # abbreviations before filename (both have dots)
        "filename",                                 # filenames after abbreviations
        "number",                                   # bare numbers last
        "pronounce",                                # user dict — operates on already-normalized text
        "math", "ampersand", "hashtag",
    ]

    for rule_name in priority:
        if rule_name not in rules:
            continue
        if rule_name not in RULES:
            continue
        pattern, func, desc = RULES[rule_name]
        if pattern is None:
            # Whole-text transform (e.g. markdown, html) — func takes the
            # full string and returns the rewritten string.
            text = func(text)
        else:
            text = re.sub(pattern, func, text)

    # Collapse the runs of whitespace any rule (notably "emoji") may have
    # left behind. Idempotent and harmless when no rule produced extra spaces.
    text = re.sub(r"\s+", " ", text).strip()

    return text
