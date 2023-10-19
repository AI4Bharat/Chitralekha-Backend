from celery import shared_task
from backend.celery import celery_app
from .models import SubscribedUsers, Newsletter


@shared_task(name="send_newsletter")
def send_newsletter():
    logging.info("Sending Newsletter")
    today = date.today()
    newsletters = Newsletter.objects.filter(created_at__contains=today).all()
    if newsletter is not None:
        subscribed_users = SubscribedUsers.get.all()
        for newsletter in newsletters:
            for subscribed_user in subscribed_users:
                logging.info("Sending Mail to %s", suscribed_user.user.email)
                send_mail(
                    "Chitralekha - Newsletter",
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [manager.email],
                    html_message=newsletter.content,
                )
