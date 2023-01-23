import requests
from uuid import UUID
import json

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


def generate_translation_payload(transcript, target_language, list_compare_sources):
    payloads = {}
    if "MACHINE_GENERATED" in list_compare_sources:
        translation_machine_generated = translation_mg(transcript, target_language)
        payloads["MACHINE_GENERATED"] = translation_machine_generated

    if "MANUALLY_CREATED" in list_compare_sources:
        payload = []
        for txt in transcript.payload["payload"]:
            txt["target_text"] = ""
            payload.append(txt)
        payloads["MANUALLY_CREATED"] = {"payload": payload}
    return payloads


def translation_mg(transcript, target_language, batch_size=75):
    sentence_list = []
    vtt_output = transcript.payload
    for vtt_line in vtt_output["payload"]:
        sentence_list.append(vtt_line["text"])

    all_translated_sentences = []  # List to store all the translated sentences

    # Iterate over the sentences in batch format and send them to the Translation API
    for i in range(0, len(sentence_list), batch_size):
        batch_of_input_sentences = sentence_list[i : i + batch_size]

        # Get the translation using the Indictrans NMT API
        translations_output = get_batch_translations_using_indictrans_nmt_api(
            sentence_list=batch_of_input_sentences,
            source_language=transcript.language,
            target_language=target_language,
        )

        # Check if translations output doesn't return a string error
        if isinstance(translations_output, str):
            return Response(
                {"message": translations_output}, status=status.HTTP_400_BAD_REQUEST
            )
        else:
            # Add the translated sentences to the list
            all_translated_sentences.extend(translations_output)

    # Check if the length of the translated sentences is equal to the length of the input sentences
    if len(all_translated_sentences) != len(sentence_list):
        return Response(
            {"message": "Error while generating translation."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Update the translation payload with the generated translations
    payload = []
    for (source, target) in zip(vtt_output["payload"], all_translated_sentences):
        payload.append(
            {
                "start_time": source["start_time"],
                "end_time": source["end_time"],
                "text": source["text"],
                "target_text": target if source["text"].strip() else source["text"],
            }
        )
    return json.loads(json.dumps({"payload": payload}))
