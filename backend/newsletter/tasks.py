from backend.celery import celery_app
from .models import SubscribedUsers, Newsletter
from django.conf import settings
from django.core.mail import send_mail
import logging
from config import app_name


@celery_app.task(queue="newsletter")
def celery_newsletter_call(newsletter_id, subject):
    logging.info("Sending Newsletter")
    subscribed_users = SubscribedUsers.objects.all()
    newsletter = Newsletter.objects.get(pk=newsletter_id)
    for subscribed_user in subscribed_users:
        logging.info("Sending Mail to %s", subscribed_user.user.email)
        cont = newsletter.content.replace("{user_email_id}", subscribed_user.email)
        newsletter.content = cont
        newsletter.save()
        try:
            send_mail(
                f"{app_name} - Newsletter",
                "",
                settings.DEFAULT_FROM_EMAIL,
                [subscribed_user.email],
                html_message=newsletter.content,
            )
        except:
            logging.info("Mail can't be sent.")
