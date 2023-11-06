## SECRETS ##
import os
from dotenv import load_dotenv

dhruva_key = os.getenv("DHRUVA_KEY")
english_asr_url = os.getenv("ENGLISH_ASR_API_URL")
indic_asr_url = os.getenv("INDIC_ASR_API_URL")
service_id_hindi = os.getenv("SERVICE_ID_HINDI")
service_id_indo_aryan = os.getenv("SERVICE_ID_INDO_ARYAN")
service_id_dravidian = os.getenv("SERVICE_ID_DRAVIDIAN")
nmt_url = os.getenv("NMT_API_URL")
transliteration_url = os.getenv("TRANSLITERATION_URL")

frontend_url = os.getenv("FRONTEND_URL")
## CONSTANTS ##
