import requests
from uuid import UUID
import json
from rest_framework.response import Response
from rest_framework import status
import logging
from docx import *
from docx.shared import Inches
from django.http import HttpResponse, StreamingHttpResponse
from io import StringIO, BytesIO
import os
import datetime
from config import nmt_url, dhruva_key
from .metadata import LANG_CODE_TO_NAME, english_noise_tags, target_noise_tags
import math
from task.models import Task
import regex
from transcript.utils.timestamp import *


### Utility Functions ###
def validate_uuid4(val):
    try:
        UUID(str(val))
        return True
    except ValueError:
        return False


def valid_xml_char_ordinal(c):
    codepoint = ord(c)
    # conditions ordered by presumed frequency
    return (
        0x20 <= codepoint <= 0xD7FF
        or codepoint in (0x9, 0xA, 0xD)
        or 0xE000 <= codepoint <= 0xFFFD
        or 0x10000 <= codepoint <= 0x10FFFF
    )


def convert_to_docx(content):
    document = Document()
    cleaned_string = "".join(c for c in content if valid_xml_char_ordinal(c))
    paragraph = document.add_paragraph(cleaned_string)
    run = paragraph.add_run()
    # Prepare document for download
    # -----------------------------
    buffer = BytesIO()
    with open("temp_f.txt", "w") as out_f:
        out_f.write(content)

    buffer.write(open("temp_f.txt", "rb").read())
    print(buffer.seek(0))
    document.save(buffer)
    length = buffer.tell()
    buffer.seek(0)
    response = StreamingHttpResponse(
        streaming_content=buffer,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    response["Content-Disposition"] = "attachment; filename=" + "new_file_download"
    response["Content-Encoding"] = "UTF-8"
    response["Content-Length"] = length
    os.remove("temp_f.txt")
    return response


def convert_to_paragraph(lines):
    count = 0
    content = ""
    for line in lines:
        content = content + " " + line

    new_content = ""
    count = 0
    sentences_count = 0
    content = content.replace("\n", " ")
    for index, i in enumerate(content):
        count += 1
        if content[index] == "." and sentences_count == 5:
            content = content[: index + 1] + "\n" + "\n" + content[index + 1 :]
            sentences_count = 0
        if sentences_count < 5 and i == ".":
            sentences_count += 1

    return content


def convert_to_paragraph_monolingual(payload):
    lines = []
    content = ""
    translated_content = ""
    sentences_count = 0
    number_of_paragraphs = math.ceil(len(payload) / 5)
    count_paragraphs = 0
    for index, segment in enumerate(payload):
        if "text" in segment.keys():
            lines.append(segment["target_text"])
            translated_content = translated_content + " " + segment["target_text"]
            sentences_count += 1
            if sentences_count % 5 == 0:
                count_paragraphs += 1
                content = content + translated_content + "\n" + "\n"
                translated_content = ""

    if count_paragraphs < number_of_paragraphs:
        content = content + translated_content + "\n" + "\n"
    return content


def convert_to_paragraph_bilingual(payload):
    lines = []
    transcripted_lines = []
    content = ""
    transcripted_content = ""
    translated_content = ""
    sentences_count = 0
    number_of_paragraphs = math.ceil(len(payload) / 5)
    count_paragraphs = 0
    for index, segment in enumerate(payload):
        if "text" in segment.keys():
            lines.append(segment["target_text"])
            transcripted_lines.append(segment["text"])
            transcripted_content = (
                transcripted_content + " " + segment["text"].replace("\n", " ")
            )
            translated_content = translated_content + " " + segment["target_text"]
            sentences_count += 1
            if sentences_count % 5 == 0:
                count_paragraphs += 1
                content = (
                    content
                    + transcripted_content
                    + "\n"
                    + "\n"
                    + translated_content
                    + "\n"
                    + "\n"
                )
                transcripted_content = ""
                translated_content = ""

    if count_paragraphs < number_of_paragraphs:
        content = (
            content
            + transcripted_content
            + "\n"
            + "\n"
            + translated_content
            + "\n"
            + "\n"
        )
    return content


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
    source_language_name = LANG_CODE_TO_NAME[source_language]
    target_language_name = LANG_CODE_TO_NAME[target_language]

    # logging.info("source_language_name %s", source_language_name)
    logging.info("target_language_name %s", target_language_name)

    # Create the input sentences list
    input_sentences = [{"source": sentence} for sentence in sentence_list]

    json_data = {
        "input": input_sentences,
        "config": {
            "language": {
                "sourceLanguage": source_language,
                "targetLanguage": target_language,
            },
        },
    }
    try:
        response = requests.post(
            nmt_url,
            headers={"authorization": dhruva_key},
            json=json_data,
        )
        translations_output = response.json()["output"]
        # Collect the translated sentences
        return [translation["target"] for translation in translations_output]
    except Exception as e:
        logging.info("Error in generating translation Output")
        return str(e)


def generate_translation_payload(transcript, target_language, list_compare_sources):
    payloads = {}
    if "MACHINE_GENERATED" in list_compare_sources:
        try:
            translation_machine_generated = translation_mg(transcript, target_language)
        except:
            if transcript.language == "en":
                transcript.transcript_type = "ORIGINAL_SOURCE"
                transcript.save()
                translation_machine_generated = translation_mg(
                    transcript, target_language
                )
                transcript.transcript_type = "MACHINE_GENERATED"
                transcript.save()
        payloads["MACHINE_GENERATED"] = translation_machine_generated

    if "MANUALLY_CREATED" in list_compare_sources:
        payload = []
        for txt in transcript.payload["payload"]:
            txt["target_text"] = ""
            payload.append(txt)
        payloads["MANUALLY_CREATED"] = {"payload": payload}
    return payloads


def get_ratio_of_words(a):
    output = []
    percentage_per_sentence = {}
    pre_last_part = 0
    i = 0
    last = False
    total = 0
    while i < len(a):
        x = a[i]["text"].split(".")
        list = [len(x) - 1]
        # if last == False:
        #     percentage_per_sentence = {}
        percentage_per_sentence[i] = []
        # if(i == 0) handle for no dot and having dots.
        if x[-1] != "":
            first_part = len(x[-1].split())

            j = i + 1
            count_words = 0
            while j != len(a) and "." not in a[j]["text"]:
                count_words += len(a[j]["text"].split())
                j += 1
            last_part = 0
            if j != len(a):
                last_part = len(a[j]["text"].split(".")[0].split())
                # last = True
            pre_total = total
            total = first_part + count_words + last_part

            if len(x) == 1 and last == False:
                # data_tuple = data_tuple + 0 + first_part*100/total
                # list.append(0)
                percentage_per_sentence[i].append(first_part * 100 / total)
            else:
                if last == True:
                    # data_tuple = data_tuple + last_part*100/total + first_part*100/total
                    percentage_per_sentence[i].append(pre_last_part * 100 / pre_total)
                    list_1 = []
                    for l in range(len(x) - 2):
                        list_1.append(100)
                    if len(list_1) > 0:
                        percentage_per_sentence[i].extend(list_1)
                    percentage_per_sentence[i].append(first_part * 100 / total)
                    # output.append(percentage_per_sentence)
                    last = False
                else:
                    # data_tuple = data_tuple + 0 + first_part*100/total
                    # list.append(0)
                    list_1 = []
                    for l in range(len(x) - 1):
                        list_1.append(100)
                    if len(list_1) > 0:
                        percentage_per_sentence[i].extend(list_1)
                    percentage_per_sentence[i].append(first_part * 100 / total)
            # data_tuple = data_tuple + last_part*100/total
            # tuple_list.append(list)

            j = i + 1
            count_words = 0
            while j != len(a) and "." not in a[j]["text"]:
                percentage_per_sentence[j] = []
                count_words = len(a[j]["text"].split())
                percentage_per_sentence[j].append(count_words * 100 / total)
                j += 1

            if j != len(a):
                pre_last_part = len(a[j]["text"].split(".")[0].split())
                last = True

            i = j
        else:
            if last == False:
                list_1 = []
                for l in range(len(x) - 1):
                    list_1.append(100)
                # percentage_per_sentence[i] = []
                if len(list_1) > 0:
                    percentage_per_sentence[i].extend(list_1)
                # output.append(percentage_per_sentence)
            else:
                percentage_per_sentence[i].append(last_part * 100 / total)
                list_1 = []
                for l in range(len(x) - 2):
                    list_1.append(100)
                if len(list_1) > 0:
                    percentage_per_sentence[i].extend(list_1)
                # output.append(percentage_per_sentence)
                last = False
            i += 1
    return percentage_per_sentence


def translation_mg(transcript, target_language, batch_size=25):
    sentence_list = []
    delete_indices = []
    vtt_output = transcript.payload
    ratio_per_sentence = []

    if (
        transcript.language == "en"
        and transcript.transcript_type == "MACHINE_GENERATED"
    ):
        ratio_per_sentence = get_ratio_of_words(transcript.payload["payload"])
        full_transcript = ""
        for index, vtt_line in enumerate(vtt_output["payload"]):
            if "text" in vtt_line.keys():
                text = vtt_line["text"]
                full_transcript = full_transcript + text
        sentence_list = full_transcript.split(".")
        if sentence_list[-1] == "":
            sentence_list.pop()
    else:
        for index, vtt_line in enumerate(vtt_output["payload"]):
            if "text" in vtt_line.keys():
                text = vtt_line["text"]
                if transcript.language == "en":
                    for noise_tag in english_noise_tags:
                        text = text.replace(noise_tag, "")
                    sentence_list.append(text)
                else:
                    sentence_list.append(text)
            else:
                delete_indices.append(index)

    delete_indices.reverse()
    for ind in delete_indices:
        vtt_output["payload"].pop(ind)

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

    if type(ratio_per_sentence) == dict and len(ratio_per_sentence.keys()) > 0:
        sum = 0
        count_sentences = 0
        translated_sentences = {}
        current_sentence_ratio_list = []
        for id, list_ratio in ratio_per_sentence.items():
            for ratio in list_ratio:
                sum = sum + ratio
                current_sentence_ratio_list.append((id, ratio))
                if sum > 99:
                    length_translated_sentence = len(
                        all_translated_sentences[count_sentences]
                    )
                    cleaned_text = regex.sub(
                        r"[^\p{L}\s]", "", all_translated_sentences[count_sentences]
                    ).lower()
                    cleaned_text = regex.sub(
                        r"\s+", " ", cleaned_text
                    )  # for removing multiple blank spaces
                    length_translated_sentence = len(cleaned_text.split(" "))
                    previous_word_index = 0
                    for id, r in current_sentence_ratio_list:
                        number_of_words = math.ceil(
                            (r * length_translated_sentence) / 100
                        )
                        if (
                            previous_word_index + number_of_words
                            < length_translated_sentence
                        ):
                            target_text = " ".join(
                                all_translated_sentences[count_sentences].split(" ")[
                                    previous_word_index : previous_word_index
                                    + number_of_words
                                ]
                            )
                        else:
                            target_text = " ".join(
                                all_translated_sentences[count_sentences].split(" ")[
                                    previous_word_index:
                                ]
                            )

                        if id not in translated_sentences:
                            translated_sentences[id] = target_text
                        else:
                            translated_sentences[id] = (
                                translated_sentences[id] + " " + target_text
                            )
                        previous_word_index = previous_word_index + number_of_words
                    current_sentence_ratio_list = []
                    count_sentences += 1
                    sum = 0

        all_translated_sentences = translated_sentences.values()

    # Update the translation payload with the generated translations
    payload = []
    for (source, target) in zip(vtt_output["payload"], all_translated_sentences):
        start_time = datetime.datetime.strptime(source["start_time"], "%H:%M:%S.%f")
        unix_start_time = datetime.datetime.timestamp(start_time)
        end_time = datetime.datetime.strptime(source["end_time"], "%H:%M:%S.%f")
        unix_end_time = datetime.datetime.timestamp(end_time)

        try:
            if transcript.language == "en":
                noise_tags = list(set(source["text"].split()) & english_noise_tags)
                if noise_tags:
                    replace_noise_tag = target_noise_tags[target_language][
                        noise_tags[0].replace("[", "").replace("]", "")
                    ]
                    if replace_noise_tag != "nan":
                        target = "[" + replace_noise_tag + "] " + target

        except:
            logging.info("Error in replacing noise tags.")

        source["start_time"] = format_timestamp(source["start_time"])
        source["end_time"] = format_timestamp(source["end_time"])

        if "speaker_id" in source.keys():
            payload.append(
                {
                    "start_time": source["start_time"],
                    "end_time": source["end_time"],
                    "text": source["text"],
                    "speaker_id": source["speaker_id"],
                    "unix_start_time": unix_start_time,
                    "unix_end_time": unix_end_time,
                    "target_text": target if source["text"].strip() else source["text"],
                }
            )
        else:
            payload.append(
                {
                    "start_time": source["start_time"],
                    "end_time": source["end_time"],
                    "text": source["text"],
                    "speaker_id": "",
                    "unix_start_time": unix_start_time,
                    "unix_end_time": unix_end_time,
                    "target_text": target if source["text"].strip() else source["text"],
                }
            )
    return json.loads(json.dumps({"payload": payload}))


def set_fail_for_translation_task(task):
    translation_task = (
        Task.objects.filter(target_language=task.target_language)
        .filter(task_type="TRANSLATION_EDIT")
        .filter(video=task.video)
        .first()
    )
    if translation_task is not None:
        translation_task.status = "FAILED"
        translation_task.save()
