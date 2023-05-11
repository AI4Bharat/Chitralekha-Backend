import uuid
from django.db import models
from translation.metadata import LANGUAGE_CHOICES
from video.models import Video
from django.conf import settings
import datetime
from django.utils import timezone
from users.models import User
from organization.models import TRANSCRIPT_TYPE, TRANSLATION_TYPE_CHOICES

TRANSCRIPTION_EDIT = "TRANSCRIPTION_EDIT"
TRANSCRIPTION_REVIEW = "TRANSCRIPTION_REVIEW"
TRANSLATION_EDIT = "TRANSLATION_EDIT"
TRANSLATION_REVIEW = "TRANSLATION_REVIEW"
VOICEOVER_EDIT = "VOICEOVER_EDIT"
VOICEOVER_REVIEW = "VOICEOVER_REVIEW"
NEW = "NEW"
SELECTED_SOURCE = "SELECTED_SOURCE"
INPROGRESS = "INPROGRESS"
COMPLETE = "COMPLETE"
POST_PROCESS = "POST_PROCESS"
FAILED = "FAILED"
REOPEN = "REOPEN"
P1 = "P1"
P2 = "P2"
P3 = "P3"
P4 = "P4"

TASK_STATUS = (
    (NEW, "New"),
    (SELECTED_SOURCE, "Selected Source"),
    (INPROGRESS, "In Progress"),
    (POST_PROCESS, "Post Process"),
    (FAILED, "Failed"),
    (COMPLETE, "Complete"),
)

TASK_TYPE = (
    (TRANSCRIPTION_EDIT, "Transcription Edit"),
    (TRANSCRIPTION_REVIEW, "Transcription Review"),
    (TRANSLATION_EDIT, "Translation Edit"),
    (TRANSLATION_REVIEW, "Translation Review"),
    (VOICEOVER_EDIT, "VoiceOver Edit"),
    (VOICEOVER_REVIEW, "VoiceOver Review"),
)

PRIORITY = (
    (P1, "Priority No 1"),
    (P2, "Priority No 2"),
    (P3, "Priority No 3"),
    (P4, "Priority No 4"),
)


class Task(models.Model):
    """
    Model for Tasks
    """

    task_uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name="Task UUID",
        primary_key=False,
    )
    task_type = models.CharField(choices=TASK_TYPE, max_length=35)
    video = models.ForeignKey(
        Video,
        on_delete=models.CASCADE,
        verbose_name="Task Video ID",
        related_name="tasks",
    )
    target_language = models.CharField(
        choices=LANGUAGE_CHOICES,
        max_length=4,
        verbose_name="Target Language",
        blank=True,
    )
    verified_transcript = models.BooleanField(null=True, blank=True)
    status = models.CharField(
        choices=TASK_STATUS, verbose_name="Task Status", max_length=35, default=None
    )
    user = models.ForeignKey(
        User,
        verbose_name="Task Assignee",
        on_delete=models.CASCADE,
    )
    description = models.TextField(
        max_length=400, null=True, blank=True, help_text=("Task Description")
    )
    eta = models.DateTimeField(verbose_name="ETA", default=None, blank=True, null=True)
    priority = models.CharField(
        choices=PRIORITY, verbose_name="Priority", max_length=2, blank=True, null=True
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="task_created",
        verbose_name="created_by",
        help_text=("Task Created By"),
    )
    is_active = models.BooleanField(
        verbose_name="active",
        default=False,
        help_text=("Designates whether this task is accessible to the assignee."),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Task Created At")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Task Updated At")
    time_spent = models.IntegerField(
        default=0, null=True, blank=True, verbose_name="Time Spent"
    )

    @property
    def get_src_language_label(self):
        for language in LANGUAGE_CHOICES:
            if self.video.language == language[0]:
                return language[1]

    @property
    def get_task_type_label(self):
        for t_type in TASK_TYPE:
            if self.task_type == t_type[0]:
                return t_type[1]

    @property
    def get_target_language_label(self):
        for language in LANGUAGE_CHOICES:
            if self.target_language == language[0]:
                return language[1]
        return "-"

    @property
    def get_language_pair_label(self):
        src_language = self.get_src_language_label
        target_language = self.get_target_language_label
        if target_language == "-":
            return src_language
        else:
            return src_language + "-" + target_language

    @property
    def get_task_status(self):
        return self.get_task_type_label + " : " + self.status

    @property
    def get_task_status_label(self):
        for status in TASK_STATUS:
            if self.status == status[0]:
                return status[1]
        return "-"

    @property
    def format_time_spent(self):
        if self.time_spent == None or self.time_spent == 0:
            full_time = 0
        elif self.time_spent < 60:
            full_time = str(self.time_spent) + "s"
        elif self.time_spent < 60 * 60:
            full_time = (
                str(int(self.time_spent // 60))
                + "m "
                + str(int(self.time_spent % 60))
                + "s"
            )
        elif self.time_spent >= 60 * 60 and self.time_spent < 24 * 60 * 60:
            full_time = (
                str(int(self.time_spent // (60 * 60)))
                + "h "
                + str(int((self.time_spent % (60 * 60)) // 60))
                + "m"
            )
        elif self.time_spent >= 24 * 60 * 60 and self.time_spent < 30 * 24 * 60 * 60:
            full_time = (
                str(int(self.time_spent // (24 * 60 * 60)))
                + "d "
                + str(int((self.time_spent % (24 * 60 * 60)) // (60 * 60)))
                + "h"
            )
        elif (
            self.time_spent >= 30 * 24 * 60 * 60
            and self.time_spent < 12 * 30 * 24 * 60 * 60
        ):
            full_time = (
                str(int(self.time_spent // (30 * 24 * 60 * 60)))
                + "m "
                + str(int((self.time_spent % (30 * 24 * 60 * 60)) // (24 * 60 * 60)))
                + "d"
            )
        else:
            full_time = (
                str(int(self.time_spent // (12 * 30 * 24 * 60 * 60)))
                + "y "
                + str(
                    int(
                        (self.time_spent % (12 * 30 * 24 * 60 * 60))
                        // (30 * 24 * 60 * 60)
                    )
                )
                + "m"
            )
        return full_time

    @property
    def get_source_type(self):
        source_mapping = {
            "TRANSCRIPTION_EDIT": "self.transcript_tasks.values('transcript_type').first()",
            "TRANSCRIPTION_REVIEW": "self.transcript_tasks.values('transcript_type').first()",
            "TRANSLATION_EDIT": "self.translation_tasks.values('translation_type').first()",
            "TRANSLATION_REVIEW": "self.translation_tasks.values('translation_type').first()",
            "VOICEOVER_EDIT": "self.voice_over_tasks.values('voice_over_type').first()",
            "VOICEOVER_REVIEW": "self.voice_over_tasks.values('voice_over_type').first()",
        }

        fields_mapping = {
            "TRANSCRIPTION_EDIT": "transcript_type",
            "TRANSCRIPTION_REVIEW": "transcript_type",
            "TRANSLATION_EDIT": "translation_type",
            "TRANSLATION_REVIEW": "translation_type",
            "VOICEOVER_EDIT": "voice_over_type",
            "VOICEOVER_REVIEW": "voice_over_type",
        }

        source_type = None

        if self.task_type in source_mapping.keys():
            source_type_var = eval(source_mapping[self.task_type])
            if source_type_var is not None:
                source_type = source_type_var[fields_mapping[self.task_type]]

        if source_type:
            for TRANSCRIPT_TYPE_OBJ in TRANSCRIPT_TYPE:
                if source_type == TRANSCRIPT_TYPE_OBJ[0]:
                    return TRANSCRIPT_TYPE_OBJ[1]
            return "-"
        else:
            return "-"

    def __str__(self):
        return str(self.id)
