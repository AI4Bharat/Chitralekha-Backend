from yt_dlp.extractor import get_info_extractor

# Declare a global variable to save the object for Google Drive ID extraction
drive_info_extractor = get_info_extractor("GoogleDrive")()
