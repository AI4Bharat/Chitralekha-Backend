python3 manage.py collectstatic --noinput
gunicorn backend.wsgi -b :8082 --log-level debug --capture-output --access-logfile -
