from translation.metadata import TRANSLATION_LANGUAGE_CHOICES
from django.db.models import (
    Q,
    Count,
    Avg,
    F,
    FloatField,
    BigIntegerField,
    Sum,
    Value,
    Case,
    When,
    IntegerField,
)
from django.db.models.functions import Cast, Concat


def task_search_filter(videos, search_dict, filter_dict):
    if search_dict is not None:
        if "video_name" in search_dict:
            videos = videos.filter(Q(name__icontains=search_dict["video_name"]))

    if "src_language" in filter_dict and len(filter_dict["src_language"]):
        src_lang_list = []
        for lang in filter_dict["src_language"]:
            lang_shortcode = get_language_label(lang)
            src_lang_list.append(lang_shortcode)
        if len(src_lang_list):
            videos = videos.filter(language__in=src_lang_list)

    return videos


def task_filter_query(all_tasks, filter_dict):
    if "task_type" in filter_dict and len(filter_dict["task_type"]):
        all_tasks = all_tasks.filter(task_type__in=filter_dict["task_type"])
    if "target_language" in filter_dict and len(filter_dict["target_language"]):
        target_lang_list = []
        for lang in filter_dict["target_language"]:
            lang_shortcode = get_language_label(lang)
            target_lang_list.append(lang_shortcode)
        if len(target_lang_list):
            all_tasks = all_tasks.filter(target_language__in=target_lang_list)
    if "status" in filter_dict and len(filter_dict["status"]):
        all_tasks = all_tasks.filter(status__in=filter_dict["status"])

    return all_tasks


def task_search_by_assignee(all_tasks, search_dict):
    if "assignee" in search_dict and len(search_dict["assignee"]):
        queryset = all_tasks.annotate(
            search_name=Concat("user__first_name", Value(" "), "user__last_name")
        )
        all_tasks = queryset.filter(search_name__icontains=search_dict["assignee"])

    return all_tasks

def task_search_by_task_id(all_tasks,search_dict):
    if "task_id" in search_dict and search_dict["task_id"]!=None:
        all_tasks = all_tasks.filter(Q(pk=search_dict["task_id"]))
    return all_tasks

def task_search_by_description(all_tasks, search_dict):
    if "description" in search_dict and len(search_dict["description"]):
        all_tasks = all_tasks.filter(
            Q(description__icontains=search_dict["description"])
            | Q(description__icontains=search_dict["description"])
        )
    return all_tasks


def get_language_label(target_language):
    for language in TRANSLATION_LANGUAGE_CHOICES:
        if target_language == language[1]:
            return language[0]
    return "-"

def search_active_task(all_tasks, search_dict):
    if "active" in search_dict:
        all_tasks = all_tasks.filter(is_active=True)
    if "non_active" in search_dict:
        all_tasks = all_tasks.filter(is_active=False)
    return all_tasks
