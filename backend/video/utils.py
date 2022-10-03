from datetime import timedelta
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError
from yt_dlp.extractor import get_info_extractor

ydl = YoutubeDL({"format": "best"})

# Declare a global variable to save the object for Google Drive ID extraction
drive_info_extractor = get_info_extractor("GoogleDrive")()

def get_data_from_google_video(url: str, lang: str = "en"):
    '''
    Get video details from Google's platforms:
    YouTube and Drive
    '''

    try:
        info = ydl.extract_info(url, download=False)
    except DownloadError:
        raise
    
    # Check if the link is for Google Drive or YouTube
    if "drive.google.com" in url:

        # Get the file ID from the URL
        file_id = info["id"]

        # Create a direct download link by extracting the ID from the URL
        # and appending it to the Google Drive direct download link
        url = "https://drive.google.com/uc?export=download&confirm=yTib&id=" + file_id
        info["url"] = url
        info["webpage_url"] = "https://drive.google.com/file/d/" + file_id
    
    # Extract required data from the video info
    normalized_url = info["webpage_url"]
    title = info["title"]
    duration = timedelta(seconds=info["duration"])

    # Get the Direct URL to the video
    direct_video_url = info["url"]

    subtitles = None
    if "subtitles" in info:
        if lang in info["subtitles"]:
            # If it's named "English"
            subtitles = info["subtitles"][lang]
        else:
            # If it has a custom name like "English transcript by NPTEL"
            for s_key in info["subtitles"]:
                if s_key.startswith(lang + "-"):
                    subtitles = info["subtitles"][s_key]
                    break

    # If manual captions not found, search for ASR transcripts
    if (
        not subtitles
        and "automatic_captions" in info
        and lang in info["automatic_captions"]
    ):
        subtitles = info["automatic_captions"][lang]

    # subtitles_list = []
    subtitle_payload = None
    if subtitles:
        # Get the VTT URL from the subtitle info and make a GET request to fetch the data
        subtitle_url = [item["url"] for item in subtitles if item["ext"] == "vtt"][0]
        subtitle_payload = requests.get(subtitle_url).text

        # # Parse the VTT file contents and append to the subtitle list
        # subtitles_list.extend(
        #     {"start": caption.start, "end": caption.end, "text": caption.text}
        #     for caption in webvtt.read_buffer(StringIO(subtitle_payload))
        # )
    
    # Get the direct audio URL
    direct_audio_url = None
    for fmt in info["formats"]:
        if (
            fmt["resolution"] == "audio only"
            and fmt["ext"] == "m4a"
            and fmt["quality"] == 3
        ):
            direct_audio_url = fmt["fragment_base_url"] if "fragment_base_url" in fmt else fmt["url"]
            break

    return direct_video_url, normalized_url, title, duration, subtitle_payload, direct_audio_url
