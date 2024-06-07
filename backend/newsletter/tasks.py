from backend.celery import celery_app
from .models import SubscribedUsers, Newsletter
from django.conf import settings
from django.core.mail import send_mail, EmailMultiAlternatives
import logging
from config import app_name, frontend_url
from utils.email_template import send_email_template


@celery_app.task(queue="newsletter")
def celery_newsletter_call(newsletter_id, subject):
    logging.info("Sending Newsletter")
    subscribed_users = SubscribedUsers.objects.all()
    newsletter = Newsletter.objects.get(pk=newsletter_id)
    for subscribed_user in subscribed_users:
        if newsletter.category in subscribed_user.subscribed_categories:
            logging.info("Sending Mail to %s", subscribed_user.email)
            subscribed_categories = ",".join(subscribed_user.subscribed_categories)
            unsubscribe_link = f"{frontend_url}/#/newsletter/unsubscribe?email={subscribed_user.email}&categories={subscribed_categories}"
            cont = newsletter.content.replace("{unsubscribe_link}", unsubscribe_link)
            try:
                subject = "Reset Password Link For Shoonya"
                message = f"<p> Hello! Please click on the following link to view the newsletter {cont} </p>"

                compiled_code = send_email_template(subject, message)
                msg = EmailMultiAlternatives(
                    subject,
                    compiled_code,
                    settings.DEFAULT_FROM_EMAIL,
                    [subscribed_user.email],
                )
                msg.attach_alternative(compiled_code, "text/html")
                msg.attach_alternative(cont, "text/html")
                msg.send()

                # send_mail(
                #     subject,
                #     "",
                #     settings.DEFAULT_FROM_EMAIL,
                #     [subscribed_user.email],
                #     html_message=cont,
                # )
            except:
                logging.info("Mail can't be sent.")
        else:
            logging.info("User is not subscribed to this cateogry.")
