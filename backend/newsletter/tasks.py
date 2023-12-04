from celery import shared_task
from backend.celery import celery_app
from .models import SubscribedUsers, Newsletter
from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail
import logging


@shared_task(name="send_newsletter")
def send_newsletter():
    logging.info("Sending Newsletter")
    now = timezone.now()
    past_24_hours = now - timezone.timedelta(hours=24)

    # Get all objects created in the past 24 hours
    newsletters = Newsletter.objects.filter(created_at__gte=past_24_hours).all()
    if newsletters is not None:
        subscribed_users = SubscribedUsers.objects.all()
        for newsletter in newsletters:
            for subscribed_user in subscribed_users:
                logging.info("Sending Mail to %s", subscribed_user.user.email)
                try:
                    send_mail(
                        "Chitralekha - Newsletter",
                        "",
                        settings.DEFAULT_FROM_EMAIL,
                        [subscribed_user.user.email],
                        html_message=newsletter.content,
                    )
                except:
                    logging.info("Mail can't be sent.")
