import requests
from uuid import UUID
from .metadata import (
    LANG_TRANS_MODEL_CODES,
    DEFAULT_ULCA_INDIC_TO_INDIC_MODEL_ID,
    LANG_CODE_TO_NAME_ULCA,
)

### Utility Functions ###
def validate_uuid4(val):
    try:
        UUID(str(val))
        return True
    except ValueError:
        return False


def get_batch_translations_using_indictrans_nmt_api(
    sentence_list,
    source_language,
    target_language,
):

    """Function to get the translation for the input sentences using the IndicTrans NMT API.
    Args:
        sentence_list (str): List of sentences to be translated.
        source_language (str): Original language of the sentence.
        target_language (str): Final language of the sentence.
    Returns:
        list: List of dictionaries containing the translated sentences.
    """

    # Convert language code to language text
    source_language_name = LANG_CODE_TO_NAME_ULCA[source_language]
    target_language_name = LANG_CODE_TO_NAME_ULCA[target_language]

    # Get the translation model ID
    model_id = LANG_TRANS_MODEL_CODES.get(
        f"{source_language_name}-{target_language_name}",
        DEFAULT_ULCA_INDIC_TO_INDIC_MODEL_ID,
    )

    # Create the input sentences list
    input_sentences = [{"source": sentence} for sentence in sentence_list]

    json_data = {
        "input": input_sentences,
        "config": {
            "modelId": model_id,
            "language": {
                "sourceLanguage": source_language,
                "targetLanguage": target_language,
            },
        },
    }

    try:
        response = requests.post(
            "https://nmt-models.ulcacontrib.org/aai4b-nmt-inference/v0/translate",
            json=json_data,
        )

        translations_output = response.json()["output"]

        # Collect the translated sentences
        return [translation["target"] for translation in translations_output]

    except Exception as e:
        return str(e)
