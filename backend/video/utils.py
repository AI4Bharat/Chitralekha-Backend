import requests
from datetime import timedelta
import webvtt
from io import StringIO
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError
from yt_dlp.extractor import get_info_extractor
from django.http import HttpRequest, QueryDict
from transcript.views import export_transcript
from translation.views import export_translation
from django.shortcuts import get_object_or_404,get_list_or_404
import logging
from django.conf import settings
from django.core.mail import send_mail, EmailMultiAlternatives
from video.models import Video, GENDER
from project.models import Project
from video.serializers import VideoSerializer
from task.views import TaskViewSet
from task.serializers import TaskStatusSerializer
from rest_framework.response import Response
from rest_framework import status
from users.models import User
from rest_framework import request
import urllib
from mutagen.mp3 import MP3
import json
from utils.email_template import send_email_template
from config import youtube_api_key
from googleapiclient.discovery import build
import re

ydl = YoutubeDL({"format": "best*[acodec!=none]"})

# Declare a global variable to save the object for Google Drive ID extraction
drive_info_extractor = get_info_extractor("GoogleDrive")()


def get_data_from_google_video(url: str):
    """
    Get video details from Google's platforms:
    YouTube and Drive
    """

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

    # Get the direct audio URL
    direct_audio_url = None
    for fmt in info["formats"]:
        if (
            fmt["resolution"] == "audio only"
            and fmt["ext"] == "m4a"
            and fmt["quality"] == 3
        ):
            direct_audio_url = (
                fmt["fragment_base_url"] if "fragment_base_url" in fmt else fmt["url"]
            )
            break

    return direct_video_url, normalized_url, title, duration, direct_audio_url


def get_subtitles_from_google_video(url: str, lang: str = "en") -> str:
    info = ydl.extract_info(url, download=False)
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
    is_auto_generated = False
    if (
        not subtitles
        and "automatic_captions" in info
        and lang in info["automatic_captions"]
    ):
        subtitles = info["automatic_captions"][lang]
        is_auto_generated = True

    # subtitles_list = []
    subtitle_payload = None
    if subtitles:
        # Get the VTT URL from the subtitle info and make a GET request to fetch the data
        subtitle_url = [item["url"] for item in subtitles if item["ext"] == "vtt"][0]
        subtitle_payload = requests.get(subtitle_url).text
        if is_auto_generated:
            subtitle_payload = clean_youtube_asr_captions(subtitle_payload)

        # # Parse the VTT file contents and append to the subtitle list
        # subtitles_list.extend(
        #     {"start": caption.start, "end": caption.end, "text": caption.text}
        #     for caption in webvtt.read_buffer(StringIO(subtitle_payload))
        # )

    return subtitle_payload, is_auto_generated


def clean_youtube_asr_captions(subtitle_payload: str) -> str:
    """
    YouTube auto-generated VTT has 2 lines per caption:
    1. Normalized previous caption
    2. Current caption with <c> tags for word-level timestamps

    Retain only the 2nd line after normalizing
    """
    parsed_vtt = webvtt.read_buffer(StringIO(subtitle_payload))
    clean_captions = []
    for caption in parsed_vtt:
        lines = caption.text.split("\n")
        if len(lines) == 2:
            clean_text = lines[1].strip()
            if clean_text:
                caption.text = clean_text
                clean_captions.append(caption)
    parsed_vtt._captions = clean_captions
    return parsed_vtt.content


def get_export_translation(request, task_id, export_type):
    new_request = HttpRequest()
    new_request.method = "GET"
    new_request.user = request.user
    new_request.GET = request.GET.copy()
    new_request.GET["task_id"] = task_id
    new_request.GET["export_type"] = export_type
    if "return_file_content" in request.data:
        new_request.GET["return_file_content"] = request.data["return_file_content"]
    return export_translation(new_request)


def get_export_transcript(request, task_id, export_type):
    new_request = HttpRequest()
    new_request.method = "GET"
    new_request.user = request.user
    new_request.GET = request.GET.copy()
    new_request.GET["task_id"] = task_id
    new_request.GET["export_type"] = export_type
    if "return_file_content" in request.data:
        new_request.GET["return_file_content"] = request.data["return_file_content"]
    return export_transcript(new_request)


def send_mail_to_user(task):
    if task.user.enable_mail:
        if task.eta is not None:
            try:
                task_eta = str(task.eta.strftime("%Y-%m-%d"))
            except AttributeError:
                task_eta = str(task.eta)
        else:
            task_eta = "-"
        logging.info("Send email to user %s", task.user.email)
        table_to_send = "<p>Dear User, Following task is active.</p><p><head><style>table, th, td {border: 1px solid black;border-collapse: collapse;}</style></head><body><table>"
        data = "<tr><th>Video Name</th><td>{name}</td></tr><tr><th>Video URL</th><td>{url}</td></tr><tr><th>Project Name</th><td>{project_name}</td></tr><tr><th>ETA</th><td>{eta}</td></tr><tr><th>Description</th><td>{description}</td></tr></table></body></p>".format(
            name=task.video.name,
            url=task.video.url,
            project_name=task.video.project_id.title,
            eta=task_eta,
            description=task.description,
        )
        final_table = table_to_send + data
        try:
            subject = f"{task.get_task_type_label()} is now active"
            message = f"Following task is active you may check the attachment below \n {final_table}"
            compiled_code = send_email_template(subject, message)
            msg = EmailMultiAlternatives(
                subject,
                compiled_code,
                settings.DEFAULT_FROM_EMAIL,
                [task.user.email],
            )
            msg.attach_alternative(compiled_code, "text/html")
            msg.send()
        except Exception as e:
            logging.error("Error in sending Email: %s", str(e))
    else:
        logging.info("Email is not enabled %s", task.user.email)


def create_tasks(
    video_id,
    task_type,
    user,
    eta,
    priority,
    description,
    target_language=None,
    user_id=None,
):
    data = TaskViewSet(detail=True)
    new_request = HttpRequest()
    new_request.user = user
    new_request.data = {
        "task_type": task_type,
        "video_ids": [video_id],
        "target_language": target_language,
        "eta": eta,
        "user_id": user_id,
        "priority": priority,
        "description": description,
    }
    logging.info(
        "Creation of task started for task type{}, {}, {}, {}".format(
            task_type, video_id, target_language, user_id
        )
    )
    ret = data.create(new_request)
    return ret.data


def iso8601_duration_to_seconds(iso_duration):
    regex = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")
    matches = regex.match(iso_duration)

    hours = int(matches.group(1)) if matches.group(1) else 0
    minutes = int(matches.group(2)) if matches.group(2) else 0
    seconds = int(matches.group(3)) if matches.group(3) else 0

    total_seconds = hours * 3600 + minutes * 60 + seconds
    return total_seconds

def fetch_video_details(video_uuid=None, video_url=None):
    if video_url:
        # Fetch all videos matching the URL
        videos = get_list_or_404(Video, url=video_url)
        video_list = []
        for video in videos:
            video_list.append({
                "id": video.id,
                "video_uuid": str(video.video_uuid),
                "name": video.name,
                "url": video.url,
                "language": video.language,
                "description": video.description,
                "duration": str(video.duration),
                "subtitles": video.subtitles,
                "audio_only": video.audio_only,
                "project_id": video.project_id.id,  
                "language_label": video.get_language_label,
                "gender_label": video.get_gender_label,
                "speaker_info": video.speaker_info,
                "multiple_speaker": video.multiple_speaker
            })
        response_data = {
            "videos": video_list,
            
        }
        return response_data, 200

    elif video_uuid:
        # Fetch a single video matching the UUID
        video = get_object_or_404(Video, video_uuid=video_uuid)
        response_data = {
            "video": {
                "id": video.id,
                "video_uuid": str(video.video_uuid),
                "name": video.name,
                "url": video.url,
                "language": video.language,
                "description": video.description,
                "duration": str(video.duration),
                "subtitles": video.subtitles,
                "audio_only": video.audio_only,
                "project_id": video.project_id.id,  
                "language_label": video.get_language_label,
                "gender_label": video.get_gender_label,
                "speaker_info": video.speaker_info,
                "multiple_speaker": video.multiple_speaker
            },
            
        }
        return response_data, 200  



def get_video_func(request):
    url = request.GET.get("multimedia_url")
    lang = request.GET.get("lang", "en")
    project_id = int(request.GET.get("project_id"))
    description = request.GET.get("description", "")
    is_audio_only = request.GET.get("is_audio_only", "false")
    create = request.GET.get("create", "false")
    gender = request.GET.get("gender", "MALE")
    upload_task_type = request.GET.get("task_type")
    upload_target_language = request.GET.get("target_language")
    assignee = request.GET.get("assignee")
    upload_task_description = request.GET.get("task_description", "")
    upload_task_eta = request.GET.get("ETA")
    speaker_info = request.GET.get("speaker_info")
    multiple_speaker = request.GET.get("multiple_speaker", "false")
    url = url.strip()

    create = create.lower() == "true"
    project = Project.objects.filter(pk=project_id).first()
    if project is None:
        return Response(
            {"message": "Project is not found. "},
            status=status.HTTP_404_NOT_FOUND,
        )

    organization = project.organization_id
    if create:
        videos = Video.objects.filter(url=url)
        for video_project in videos.values_list("project_id__id", flat=True):
            if video_project == project_id:
                video = (
                    Video.objects.filter(url=url)
                    .filter(project_id__id=project_id)
                    .first()
                )
                return Response(
                    {
                        "message": "Video is already a part of this project. Please upload in another project.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

    video = Video.objects.filter(url=url).filter(project_id__id=project_id).first()
    if video is None:
        create = True

    # Convert audio only to boolean
    is_audio_only = is_audio_only.lower() == "true"
    multiple_speaker = multiple_speaker.lower() == "true"
    if not url:
        return Response(
            {"message": "Video URL not provided in query params."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if gender is not None:
        gender_list = [gender[0] for gender in GENDER]
        if gender.upper() in gender_list:
            gender = gender.upper()
        else:
            gender = "MALE"

    default_task_eta = upload_task_eta or project.default_eta
    default_task_priority = project.default_priority
    default_task_description = upload_task_description or project.default_description
    consolidated_report = []
    detailed_report = []
    message = ""
    fail_count = 0
    success_count = 0
    ## PATCH: Handle audio_only files separately for google drive links
    ## TODO: Move it to an util function
    if "drive.google.com" in url and is_audio_only:
        # Construct a direct download link from the google drive url
        # get the id from the drive link
        try:
            file_id = drive_info_extractor._match_id(url)
        except Exception:
            return Response(
                {"message": "Invalid Google Drive URL."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        url = f"https://drive.google.com/uc?export=download&confirm=yTib&id={file_id}"

        # Get the video metadata
        title = (
            urllib.request.urlopen(urllib.request.Request(url)).info().get_filename()
        )
        if title[-4:] == ".mp4":
            return Response(
                {"message": "Invalid file type. Mp4 is not supported"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        direct_audio_url = url

        # Calculate the duration
        filename, headers = urllib.request.urlretrieve(url)
        audio = MP3(filename)
        duration = timedelta(seconds=int(audio.info.length))

        # Create a new DB entry if URL does not exist, else return the existing entry
        video, created = Video.objects.get_or_create(
            url=url,
            defaults={
                "name": title,
                "duration": duration,
                "project_id": project,
                "audio_only": is_audio_only,
                "language": lang,
                "description": description,
                "gender": gender,
                "multiple_speaker": multiple_speaker,
            },
        )
        serializer = VideoSerializer(video)
        response_data = {
            "video": serializer.data,
        }

        if is_audio_only:
            response_data["direct_audio_url"] = direct_audio_url
        else:
            response_data["direct_video_url"] = direct_video_url

        if created:
            if speaker_info is not None:
                speakers = set()
                for speaker in json.loads(speaker_info):
                    if speaker["id"] not in speaker:
                        speakers.add(speaker["id"])
                    else:
                        logging.error("Speaker Ids are not unique.")
                        return Response(
                            {"message": "Speaker Ids should be unique."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                video.speaker_info = json.loads(speaker_info)
            else:
                video.speaker_info = []
            video.save()
            logging.info("Audio is created.")
            default_task_types = (
                project.default_task_types or organization.default_task_types
            )
            default_target_languages = (
                project.default_target_languages
                or organization.default_target_languages
            )
            if upload_task_type is not None:
                default_task_types = [upload_task_type]
            if upload_target_language is not None:
                default_target_languages = [upload_target_language]
            if assignee is not None:
                user_id = assignee
            else:
                user_id = None

            if default_task_types is not None:
                for task_type in default_task_types:
                    if (
                        default_target_languages is not None
                        and "TRANSCRIPTION" not in task_type
                    ):
                        for target_language in default_target_languages:
                            task_response = create_tasks(
                                video.id,
                                task_type,
                                request.user,
                                default_task_eta,
                                default_task_priority,
                                default_task_description,
                                target_language,
                                user_id,
                            )
                            detailed_report.extend(
                                task_response["response"]["detailed_report"]
                            )
                            if (
                                task_response["response"]["detailed_report"][0][
                                    "status"
                                ]
                                == "Fail"
                            ):
                                fail_count += 1
                            else:
                                success_count += 1
                    else:
                        task_response = create_tasks(
                            video.id,
                            task_type,
                            request.user,
                            default_task_eta,
                            default_task_priority,
                            default_task_description,
                            None,
                            user_id,
                        )
                        detailed_report.extend(
                            task_response["response"]["detailed_report"]
                        )
                        if (
                            task_response["response"]["detailed_report"][0]["status"]
                            == "Fail"
                        ):
                            fail_count += 1
                        else:
                            success_count += 1
                if fail_count > 0:
                    message = "{0} Tasks creation failed.".format(fail_count)
                    consolidated_report.append(
                        {"message": "Tasks creation failed.", "count": fail_count}
                    )
                if success_count > 0:
                    message = (
                        "{0} Tasks created successfully.".format(success_count)
                        + message
                    )
                    consolidated_report.append(
                        {
                            "message": "Tasks created successfully.",
                            "count": success_count,
                        }
                    )
            response_data["consolidated_report"] = consolidated_report
            response_data["detailed_report"] = detailed_report
            response_data["message"] = "Video created successfully." + message

            return Response(
                response_data,
                status=status.HTTP_200_OK,
            )
        else:
            if assignee is not None:
                user_id = assignee
            else:
                user_id = None

            return Response(
                response_data,
                status=status.HTTP_200_OK,
            )

    try:
        # Get the video info from the YouTube API
        (
            direct_video_url,
            normalized_url,
            title,
            duration,
            direct_audio_url,
        ) = get_data_from_google_video(url)
    except:
        direct_video_url = ""
        direct_audio_url = ""
        normalized_url = url
        try:
            API_KEY = youtube_api_key
            youtube = build("youtube", "v3", developerKey=API_KEY)

            pattern = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
            match = re.search(pattern, url)

            videos_response = (
                youtube.videos()
                .list(part="snippet,contentDetails", id=match.group(1))
                .execute()
            )

            video = videos_response["items"][0]
            title = video["snippet"]["title"]
            duration_iso8601 = video["contentDetails"]["duration"]
            duration = timedelta(seconds=iso8601_duration_to_seconds(duration_iso8601))
        except:
            return Response(
                {"message": "This is an invalid video URL."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    if title[-4:] == ".mp4" and "youtube.com" not in normalized_url:
        return Response(
            {"message": "Invalid file type. Mp4 is not supported"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    # Create a new DB entry if URL does not exist, else return the existing entry
    if create:
        video = Video.objects.create(
            name=title,
            duration=duration,
            project_id=project,
            audio_only=is_audio_only,
            language=lang,
            description=description,
            gender=gender,
            multiple_speaker=multiple_speaker,
            url=normalized_url,
        )
    else:
        video = Video.objects.get(
            name=title,
            project_id=project,
            audio_only=is_audio_only,
            language=lang,
            url=normalized_url,
        )

    if create:
        if speaker_info is not None:
            # Check if speakers are unique within the video.
            speakers = set()
            for speaker in json.loads(speaker_info):
                if speaker["id"] not in speakers:
                    speakers.add(speaker["id"])
                else:
                    logging.error("Speaker Ids are not unique.")
                    return Response(
                        {"message": "Speaker Ids should be unique."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            video.speaker_info = json.loads(speaker_info)
        else:
            video.speaker_info = []
        video.save()
        # subtitle_payload, is_machine_generated = get_subtitles_from_google_video(
        #     url, lang
        # )
        # if subtitle_payload:
        #     # Save the subtitles to the video object
        #     video.subtitles = {
        #         # "status": "SUCCESS",
        #         "output": subtitle_payload,
        #     }
        #     video.save()

    # Create the response data to be returned
    video.audio_only = is_audio_only
    serializer = VideoSerializer(video)
    response_data = {
        "video": serializer.data,
    }

    # Check if it's audio only
    if is_audio_only:
        response_data["direct_audio_url"] = direct_audio_url
    else:
        response_data["direct_video_url"] = direct_video_url

    if create:
        default_task_types = (
            project.default_task_types or organization.default_task_types
        )
        default_target_languages = (
            project.default_target_languages or organization.default_target_languages
        )
        if upload_task_type is not None:
            default_task_types = [upload_task_type]
        if upload_target_language is not None:
            default_target_languages = [upload_target_language]
        if assignee is not None:
            user_id = assignee
        else:
            user_id = None

        if default_task_types is not None:
            for task_type in default_task_types:
                if (
                    default_target_languages is not None
                    and "TRANSCRIPTION" not in task_type
                ):
                    for target_language in default_target_languages:
                        task_response = create_tasks(
                            video.id,
                            task_type,
                            request.user,
                            default_task_eta,
                            default_task_priority,
                            default_task_description,
                            target_language,
                            user_id,
                        )
                        if "response" in task_response and task_response["response"]:
                            if (
                                task_response["response"]["detailed_report"][0][
                                    "status"
                                ]
                                == "Fail"
                            ):
                                fail_count += 1
                            else:
                                success_count += 1
                                detailed_report.extend(
                                    task_response["response"]["detailed_report"]
                                )
                        else:
                            fail_count += 1
                else:
                    task_response = create_tasks(
                        video.id,
                        task_type,
                        request.user,
                        default_task_eta,
                        default_task_priority,
                        default_task_description,
                        None,
                        user_id,
                    )

                    if "response" in task_response and task_response["response"]:
                        if (
                            task_response["response"]["detailed_report"][0]["status"]
                            == "Fail"
                        ):
                            fail_count += 1
                        else:
                            success_count += 1
                            detailed_report.extend(
                                task_response["response"]["detailed_report"]
                            )
                    else:
                        fail_count += 1

            if fail_count > 0:
                message = "{0} Tasks creation failed.".format(fail_count)
                consolidated_report.append(
                    {"message": "Tasks creation failed.", "count": fail_count}
                )
            if success_count > 0:
                message = (
                    "{0} Tasks created successfully.".format(success_count) + message
                )
                consolidated_report.append(
                    {"message": "Tasks created successfully.", "count": success_count}
                )
            response_data["consolidated_report"] = consolidated_report
            response_data["detailed_report"] = detailed_report

        response_data["message"] = "Video created successfully." + message
        return Response(
            response_data,
            status=status.HTTP_200_OK,
        )
    else:
        if assignee is not None:
            user_id = assignee
        else:
            user_id = None
        if upload_task_type is not None:
            if "TRANSCRIPTION" in upload_task_type:
                task_response = create_tasks(
                    video.id,
                    upload_task_type,
                    request.user,
                    default_task_eta,
                    default_task_priority,
                    default_task_description,
                    None,
                    user_id,
                )
            else:
                task_response = create_tasks(
                    video.id,
                    upload_task_type,
                    request.user,
                    default_task_eta,
                    default_task_priority,
                    default_task_description,
                    upload_target_language,
                    user_id,
                )

            detailed_report.extend(task_response["response"]["detailed_report"])

            if task_response["response"]["detailed_report"][0]["status"] == "Fail":
                fail_count += 1
            else:
                success_count += 1

            if fail_count > 0:
                message = "{0} Tasks creation failed.".format(fail_count)
                consolidated_report.append(
                    {"message": "Tasks creation failed.", "count": fail_count}
                )
            if success_count > 0:
                message = (
                    "{0} Tasks created successfully.".format(success_count) + message
                )
                consolidated_report.append(
                    {"message": "Tasks created successfully.", "count": success_count}
                )
            response_data["consolidated_report"] = consolidated_report
            response_data["detailed_report"] = detailed_report

            response_data["message"] = message
        return Response(
            response_data,
            status=status.HTTP_200_OK,
        )


def create_video(
    user_id,
    url,
    project_id,
    task_description,
    video_description,
    ETA,
    gender,
    task_type=None,
    target_language=None,
    assignee=None,
    lang="en",
):
    new_request = HttpRequest()
    new_request.method = "GET"
    user = User.objects.get(id=user_id)
    new_request.user = user
    new_request.GET["multimedia_url"] = url
    new_request.GET["lang"] = lang
    new_request.GET["project_id"] = project_id
    new_request.GET["task_description"] = task_description
    new_request.GET["description"] = video_description
    new_request.GET["ETA"] = ETA
    new_request.GET["create"] = "false"
    new_request.GET["gender"] = gender
    new_request.GET["assignee"] = assignee
    new_request.GET["task_type"] = task_type
    new_request.GET["target_language"] = target_language
    return get_video_func(new_request)


def find_duplicates(data, key):
    temp = []
    duplicates = []

    for dictionary in data:
        if dictionary[key] not in temp:
            temp.append(dictionary[key])
        else:
            duplicates.append(dictionary[key])

    return duplicates
