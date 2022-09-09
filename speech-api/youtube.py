from yt_dlp import YoutubeDL

ydl_options = {
    "format": "best",
    # 'outtmpl': '%(id)s',
}
ydl = YoutubeDL(ydl_options)


ydl_audio_options = {
    "format": "bestaudio",
    # 'outtmpl': '%(id)s',
}
ydl_audio = YoutubeDL(ydl_audio_options)


def get_yt_video_and_subs(yt_url, lang="en", get_audio=True):
    info = ydl.extract_info(yt_url, download=False)
    result = {
        "video": info["url"],
    }

    if get_audio:
        audio_info = ydl_audio.extract_info(yt_url, download=False)
        if "url" in audio_info:
            result["audio"] = audio_info["url"]

    subtitle_payload = None

    # Search for uploaded captions
    if "subtitles" in info:
        if lang in info["subtitles"]:
            # If it's named "English"
            subtitle_payload = info["subtitles"][lang]
        else:
            # If it has a custom name like "English transcript by NPTEL"
            for s_key in info["subtitles"]:
                if s_key.startswith(lang + "-"):
                    subtitle_payload = info["subtitles"][s_key]
                    break

    # If manual captions not found, search for ASR transcripts
    if not subtitle_payload and "automatic_captions" in info:
        if lang in info["automatic_captions"]:
            subtitle_payload = info["automatic_captions"][lang]

    if subtitle_payload:
        result["subtitles"] = [
            item["url"] for item in subtitle_payload if item["ext"] == "vtt"
        ][0]

    return result


def test():
    # Random videos for test cases
    videos = {
        "proper_en": "https://www.youtube.com/watch?v=KLe7Rxkrj94",
        "improper_en": "https://www.youtube.com/watch?v=YZf5q-ICf8Y",
        "auto_en": "https://www.youtube.com/watch?v=koX-EZBC6CQ",
        "no_captions": "https://www.youtube.com/watch?v=Ek8oOnD6feQ",
    }

    for video_name, video_url in videos.items():
        result = get_yt_video_and_subs(video_url, "en")
        print(video_name)
        print(result["subtitles"] if "subtitles" in result else "Not Found")
        print()


if __name__ == "__main__":
    test()
