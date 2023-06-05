from translation.metadata import LANGUAGE_CHOICES


def get_language_label(target_language):
    for language in LANGUAGE_CHOICES:
        if target_language == language[1]:
            return language[0]
    return "-"
