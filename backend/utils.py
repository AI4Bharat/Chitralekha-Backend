from translation.metadata import TRANSLATION_LANGUAGE_CHOICES


def get_language_label(target_language):
    for language in TRANSLATION_LANGUAGE_CHOICES:
        if target_language == language[1]:
            return language[0]
    return "-"
