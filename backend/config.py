## SECRETS ##
import os
from dotenv import load_dotenv

dhruva_key = os.getenv("DHRUVA_KEY")
english_asr_url = os.getenv("ENGLISH_ASR_API_URL")
indic_asr_url = os.getenv("INDIC_ASR_API_URL")
misc_tts_url = os.getenv("MISC_TTS_API_URL")
indo_aryan_tts_url = os.getenv("INDO_ARYAN_TTS_API_URL")
dravidian_tts_url = os.getenv("DRAVIDIAN_TTS_API_URL")
nmt_url = os.getenv("NMT_API_URL")
youtube_api_key = os.getenv("YOUTUBE_API_KEY")
align_json_url = os.getenv("ALIGN_JSON_URL")
transliteration_url = os.getenv("TRANSLITERATION_URL")

storage_account_key = os.getenv("AZURE_STORAGE_ACCOUNT_KEY")
connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
container_name = os.getenv("AZURE_STORAGE_CONTAINER_NAME")

flower_url = os.getenv("FLOWER_URL", "http://localhost:5555")
flower_auth = os.getenv("FLOWER_BASIC_AUTH", None)
flower_username, flower_password = None, None
if flower_auth:
    flower_username, flower_password = flower_auth.split(":")

frontend_url = os.getenv("FRONTEND_URL")
## CONSTANTS ##

backend_default_translation_type = "MACHINE_GENERATED"
backend_default_transcript_type = "MACHINE_GENERATED"
backend_default_voice_over_type = "MACHINE_GENERATED"
voice_over_payload_offset_size = 3

allowed_roles = {
    "TRANSCRIPTION_EDIT": ["TRANSCRIPT_EDITOR", "UNIVERSAL_EDITOR"],
    "TRANSCRIPTION_REVIEW": ["TRANSCRIPT_REVIEWER", "UNIVERSAL_EDITOR"],
    "TRANSLATION_EDIT": ["TRANSLATION_EDITOR", "UNIVERSAL_EDITOR"],
    "TRANSLATION_REVIEW": ["TRANSLATION_REVIEWER", "UNIVERSAL_EDITOR"],
    "VOICEOVER_EDIT": ["VOICEOVER_EDITOR", "UNIVERSAL_EDITOR"],
    "VOICEOVER_REVIEW": ["VOICEOVER_REVIEWER", "UNIVERSAL_EDITOR"],
}

DEFAULT_SPEAKER = {
    "name": "default",
    "gender": "male",
    "age": "21-60",
    "id": "default_speaker_chitralekha",
}
