from backend.celery import celery_app
from .models import SubscribedUsers, Newsletter
from django.conf import settings
from django.core.mail import send_mail
import logging
from config import app_name, frontend_url


@celery_app.task(queue="newsletter")
def celery_newsletter_call(newsletter_id, subject):
    logging.info("Sending Newsletter")
    subscribed_users = SubscribedUsers.objects.all()
    newsletter = Newsletter.objects.get(pk=newsletter_id)
    for subscribed_user in subscribed_users:
        if newsletter.category in subscribed_user.subscribed_categories:
            logging.info("Sending Mail to %s", subscribed_user.user.email)
            subscribed_categories = ",".join(subscribed_user.subscribed_categories)
            unsubscribe_link = f"{frontend_url}/#/newsletter/unsubscribe?email={subscribed_user.email}&categories={subscribed_categories}"
            cont = newsletter.content.replace("{unsubscribe_link}", unsubscribe_link)
            newsletter.content = cont
            newsletter.save()
            try:
                send_mail(
                    f"{app_name} - Newsletter",
                    subject,
                    settings.DEFAULT_FROM_EMAIL,
                    [subscribed_user.email],
                    html_message=newsletter.content,
                )
            except:
                logging.info("Mail can't be sent.")
        logging.info("User is not subscribed to this cateogry.")
