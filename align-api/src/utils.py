from rich.console import Console
from rich.traceback import install
import re
import string
from indicnlp.normalize.indic_normalize import IndicNormalizerFactory

install()
console = Console()

def filter_text(text, language):
    
    factory = IndicNormalizerFactory()
    cleaned_text = re.sub("[%s]" % re.escape(string.punctuation + "।"), "", text)

    if language == "en":
        words = cleaned_text.split()
        new_text = " "
        for word in words:
            new_text += word.lower() + " "
        new_text = new_text.strip()
        return new_text

    else:
        normalizer = factory.get_normalizer(language, remove_nuktas=False)
        return normalizer.normalize(cleaned_text)

