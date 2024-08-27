import os

# https://pypi.org/project/openai/
# import openai
# from django.http import JsonResponse
# from transformers import AutoTokenizer, AutoModelForSeq2SeqLM


# def generate_response_from_gpt(gpt_prompt):
#     messages = []
#     for prompt in gpt_prompt:
#         messages.append({"role": "user", "content": prompt})
#     organisation_key = os.getenv("organisation_key")
#     openai.api_key = os.getenv("api_key_gpt_3.5")
#     client = OpenAI(api_key=openai.api_key, organization=organisation_key)
#     response = client.chat.completions.create(
#         model="gpt-3.5-turbo",
#         messages=messages
#     )
#     return response.choices[0].message.content.strip()


# import langdetect
#
# def check_language_consistency(texts, target_language):
#     """
#     Checks if all paragraphs/sentences in the given text are in the same language.
#
#     Args:
#         texts (list): A list of paragraphs or sentences to check.
#         target_language (str): The language code to check against (e.g., 'en', 'fr', 'es').
#
#     Returns:
#         bool: True if all texts are in the target language, False otherwise.
#     """
#     try:
#         detected_languages = set(langdetect.detect(text) for text in texts)
#         return len(detected_languages) == 1 and target_language in detected_languages
#     except langdetect.lang_detect_exception.LangDetectException:
#         return False


import os
import openai
import requests


def process_history(history):
    messages = []
    for turn in history:
        user_side = {"role": "user", "content": turn["prompt"]}
        messages.append(user_side)
        system_side = {"role": "assistant", "content": turn["output"]}
        messages.append(system_side)
    return messages


def get_gpt4_output(system_prompt=None, user_prompt=None, history = None):
    openai.api_type = os.getenv("LLM_INTERACTIONS_OPENAI_API_TYPE")
    openai.api_base = os.getenv("LLM_INTERACTIONS_OPENAI_API_BASE")
    openai.api_version = os.getenv("LLM_INTERACTIONS_OPENAI_API_VERSION")
    openai.api_key = os.getenv("OPENAI_API_KEY")
    engine = "prompt-chat-gpt4"

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if history:
        messages.extend(process_history(history))
    messages.append({"role": "user", "content": user_prompt})

    response = openai.ChatCompletion.create(
        engine=engine,
        messages=messages,
        temperature=0.7,
        max_tokens=700,
        top_p=0.95,
        frequency_penalty=0,
        presence_penalty=0,
        stop=None,
    )

    return response["choices"][0]["message"]["content"].strip()


def get_gpt3_output(system_prompt=None, user_prompt=None, history=None):
    openai.api_type = os.getenv("LLM_INTERACTIONS_OPENAI_API_TYPE")
    openai.api_base = os.getenv("LLM_INTERACTIONS_OPENAI_API_BASE")
    openai.api_version = os.getenv("LLM_INTERACTIONS_OPENAI_API_VERSION")
    openai.api_key = os.getenv("OPENAI_API_KEY")
    engine = "prompt-chat-gpt35"

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if history:
        messages.extend(process_history(history))
    
    
    messages.append({"role": "user", "content": user_prompt})

    response = openai.ChatCompletion.create(
        engine=engine,
        messages=messages,
        temperature=0.7,
        max_tokens=700,
        top_p=0.95,
        frequency_penalty=0,
        presence_penalty=0,
        stop=None,
    )

    return response["choices"][0]["message"]["content"].strip()


def get_llama2_output(system_prompt=None, conv_history = None, user_prompt=None):
    api_base = os.getenv("LLM_INTERACTION_LLAMA2_API_BASE")
    token = os.getenv("LLM_INTERACTION_LLAMA2_API_TOKEN")
    url = f"{api_base}/chat/completions"

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if conv_history:
        messages = process_history(conv_history)
    

    messages.append({"role": "user", "content": user_prompt})

    body = {
        "model": "meta-llama/Llama-2-70b-chat-hf",
        "messages": messages,
        "temperature": 0.2,
        "max_new_tokens": 500,
        "top_p": 1,
    }
    s = requests.Session()
    result = s.post(url, headers={"Authorization": f"Bearer {token}"}, json=body)
    return result.json()["choices"][0]["message"]["content"].strip()


def get_model_output(user_prompt, system_prompt=os.getenv("LLM_INTERACTIONS_SYSTEM_PROMPT"),  history=None, model="GPT3.5"):
    # Assume that translation happens outside (and the prompt is already translated)
    out = ""
    if model == "GPT3.5":
        out = get_gpt3_output(system_prompt, user_prompt, history)
    elif model == "GPT4":
        out = get_gpt4_output(system_prompt, user_prompt, history)
    elif model == "LLAMA2":
        out = get_llama2_output(system_prompt, history, user_prompt)
    return out
