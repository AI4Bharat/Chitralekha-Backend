import os
os.system("spacy download en_core_web_md")

import html
import spacy
nlp_en = spacy.load('en_core_web_md')

# Minimal set enough for sign language glosses
STOP_WORDS = {"the", "a", "an", "with", "of", "which",
              "in", "be", "do", "so", "at", "also", "to",
              ".", ",", "!", "?", "'",
              "'ve"}


def lemmatize(text: str, remove_stop_words: bool = True):
    doc = nlp_en(html.unescape(text.lower()))

    # TODO: Convert numbers to words, and normalize text (like '&' -> 'and')

    if remove_stop_words:
        words = [token.lemma_ for token in doc if token.lemma_ not in STOP_WORDS]
    else:
        words = [token.lemma_ for token in doc]
    
    return " ".join(words).upper()

if __name__ == "__main__":
    print(lemmatize("The dog saw a bigger dog and got afraid."))
