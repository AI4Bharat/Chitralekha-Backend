## SECRETS ##
import os
from dotenv import load_dotenv

# FIXME: Temporarily, eng-ASR is hosted separately. Will be merged soon into `asr_url`
english_asr_url = "http://216.48.183.5:7001/transcribe"
asr_url = os.getenv("ASR_API_URL")
tts_url = os.getenv("TTS_API_URL")
anuvaad_url = os.getenv("ANUVAAD_NMT_URL")

storage_account_key = os.getenv("AZURE_STORAGE_ACCOUNT_KEY")
connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
container_name = os.getenv("AZURE_STORAGE_CONTAINER_NAME")

flower_url = os.getenv("FLOWER_URL", "http://localhost:5555")
flower_auth = os.getenv("FLOWER_BASIC_AUTH", None)
flower_username, flower_password = None, None
if flower_auth:
    flower_username, flower_password = flower_auth.split(':')

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
