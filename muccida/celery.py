import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'muccida.settings')

app = Celery('muccida')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()