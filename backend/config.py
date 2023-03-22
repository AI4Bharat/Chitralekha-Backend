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

english_asr_url = "http://216.48.183.5:7001/transcribe"
asr_url = "http://216.48.182.174:5000/transcribe"
tts_url = "https://tts-api.ai4bharat.org/"

storage_account_key = "+8RJ9apUdZII//sIXG8Y7Y4FvS5nkC3g8fS/AAEHICreptAdUTnHsPHC9vWYvtuIzXZwh1vo2n+0+ASt9Ew17w=="
connection_string = "DefaultEndpointsProtocol=https;AccountName=chitralekhadev;AccountKey=+8RJ9apUdZII//sIXG8Y7Y4FvS5nkC3g8fS/AAEHICreptAdUTnHsPHC9vWYvtuIzXZwh1vo2n+0+ASt9Ew17w==;EndpointSuffix=core.windows.net"
container_name = "multimedia"
