from celery import Celery
from fastapi import UploadFile

celery_app = Celery(
    "tasks", broker="pyamqp://user:password@localhost:5672//", backend="rpc://"
)


@celery_app.task
def embed_file(file: UploadFile):
    return
