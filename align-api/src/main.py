from configuration import ModelPath
from wav2vec2.utils import Wav2vec2
from rich.console import Console
from rich.traceback import install

install()
console = Console()

language_codes = ModelPath.language_codes
aligner_models = {}
for language in language_codes:
    console.log(f"Loading aligner model for language {language}")
    aligner_models[language] = Wav2vec2(
        ModelPath.wav2vec2_path, language_code=language, mode="tensor",
        device=ModelPath.device)
