"""Local ISO 639-2 terminology codes; existing bibliographic/unknown codes stay intact.

This intentionally small catalog is an offline selection aid, not domain validation.
Names and terminology codes follow the Library of Congress ISO 639-2 code list.
"""

LANGUAGES = {
    "": "Unspecified",
    "afr": "Afrikaans",
    "sqi": "Albanian",
    "amh": "Amharic",
    "ara": "Arabic",
    "hye": "Armenian",
    "aze": "Azerbaijani",
    "eus": "Basque",
    "bel": "Belarusian",
    "ben": "Bengali",
    "bos": "Bosnian",
    "bul": "Bulgarian",
    "mya": "Burmese",
    "cat": "Catalan",
    "zho": "Chinese",
    "hrv": "Croatian",
    "ces": "Czech",
    "dan": "Danish",
    "nld": "Dutch",
    "eng": "English",
    "est": "Estonian",
    "fil": "Filipino",
    "fin": "Finnish",
    "fra": "French",
    "glg": "Galician",
    "kat": "Georgian",
    "deu": "German",
    "ell": "Greek",
    "guj": "Gujarati",
    "heb": "Hebrew",
    "hin": "Hindi",
    "hun": "Hungarian",
    "isl": "Icelandic",
    "ind": "Indonesian",
    "gle": "Irish",
    "ita": "Italian",
    "jpn": "Japanese",
    "kan": "Kannada",
    "kaz": "Kazakh",
    "khm": "Khmer",
    "kor": "Korean",
    "kur": "Kurdish",
    "lao": "Lao",
    "lat": "Latin",
    "lav": "Latvian",
    "lit": "Lithuanian",
    "mkd": "Macedonian",
    "msa": "Malay",
    "mal": "Malayalam",
    "mlt": "Maltese",
    "mar": "Marathi",
    "mon": "Mongolian",
    "nep": "Nepali",
    "nor": "Norwegian",
    "nob": "Norwegian Bokmal",
    "nno": "Norwegian Nynorsk",
    "fas": "Persian",
    "pol": "Polish",
    "por": "Portuguese",
    "pan": "Punjabi",
    "ron": "Romanian",
    "rus": "Russian",
    "srp": "Serbian",
    "sin": "Sinhala",
    "slk": "Slovak",
    "slv": "Slovenian",
    "som": "Somali",
    "spa": "Spanish",
    "swa": "Swahili",
    "swe": "Swedish",
    "tam": "Tamil",
    "tel": "Telugu",
    "tha": "Thai",
    "bod": "Tibetan",
    "tur": "Turkish",
    "ukr": "Ukrainian",
    "urd": "Urdu",
    "uzb": "Uzbek",
    "vie": "Vietnamese",
    "cym": "Welsh",
    "yid": "Yiddish",
    "zul": "Zulu",
    "und": "Undetermined",
    "mul": "Multiple languages",
}


def language_label(code: str) -> str:
    if code in LANGUAGES:
        return LANGUAGES[code] + (f" ({code})" if code else "")
    return f"Preserve original code ({code})"


def language_choices(query: str, original: str) -> list[tuple[str, str]]:
    choices = [(code, language_label(code)) for code in LANGUAGES]
    if original and original not in LANGUAGES:
        choices.append((original, language_label(original)))
    return sorted(
        (item for item in choices if query.casefold() in item[1].casefold()),
        key=lambda item: (bool(item[0]), item[1]),
    )
