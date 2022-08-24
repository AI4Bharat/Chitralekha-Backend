# Indic Trans API supported languages
INDIC_TRANS_SUPPORTED_LANGUAGES = {
  "Assamese": "as",
  "English": "en",
  "Hindi": "hi",
  "Marathi": "mr",
  "Tamil": "ta",
  "Bengali": "bn",
  "Kannada": "kn",
  "Oriya": "or",
  "Telugu": "te",
  "Gujarati": "gu",
  "Malayalam": "ml",
  "Punjabi": "pa"
}

LANG_NAME_TO_CODE_ULCA = {
    "English": "en",
    "Assamese": "as",
    "Bhojpuri": "bho",
    "Bengali": "bn",
    "Bodo": "brx",
    "Dogri": "doi",
    "Dhivehi": "dv",
    "Konkani": "kok",
    "Gujarati": "gu",
    "Hindi": "hi",
    "Kannada": "kn",
    "Kashmiri": "ks",
    "Mizo": "lus",
    "Maithili": "mai",
    "Malayalam": "ml",
    "Manipuri": "mni",
    "Marathi": "mr",
    "Nepali": "ne",
    "Odia": "or",
    "Punjabi": "pa",
    "Sanskrit": "sa",
    "Santali": "sat",
    "Sindhi": "sd",
    "Sinhala": "si",
    "Tamil": "ta",
    "Telugu": "te",
    "Urdu": "ur",
}

LANG_CODE_TO_NAME_ULCA = {
    lang_code: lang_name for lang_name, lang_code in LANG_NAME_TO_CODE_ULCA.items()
}

LANG_TRANS_MODEL_CODES = {
    "Hindi-English": 100,
    "Bengali-English": 101,
    "Tamil-English": 102,
    "English-Hindi": 103,
    "English-Tamil": 104,
    "English-Assamese": 110,
    "English-Bengali": 112,
    "English-Gujarati": 114,
    "English-Kannada": 116,
    "English-Malayalam": 118,
    "English-Marathi": 120,
    "English-Odia": 122,
    "English-Punjabi": 124,
    "English-Telugu": 126,
    "Assamese-English": 128,
    "Gujarati-English": 130,
    "Kannada-English": 132,
    "Malayalam-English": 134,
    "Marathi-English": 136,
    "Odia-English": 138,
    "Punjabi-English": 140,
    "Telugu-English": 142,
}  # 144 for all the other  indic-indic translations

DEFAULT_ULCA_INDIC_TO_INDIC_MODEL_ID = 144
