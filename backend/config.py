backend_default_translation_type = "MACHINE_GENERATED"
backend_default_transcript_type = "MACHINE_GENERATED"

allowed_roles = {
    "TRANSCRIPTION_EDIT": ["TRANSCRIPT_EDITOR", "UNIVERSAL_EDITOR"],
    "TRANSCRIPTION_REVIEW": ["TRANSCRIPT_REVIEWER", "UNIVERSAL_EDITOR"],
    "TRANSLATION_EDIT": ["TRANSLATION_EDITOR", "UNIVERSAL_EDITOR"],
    "TRANSLATION_REVIEW": ["TRANSLATION_REVIEWER", "UNIVERSAL_EDITOR"],
}

english_asr_url = "http://216.48.183.5:7001/transcribe"
asr_url = "http://216.48.182.174:5000/transcribe"
