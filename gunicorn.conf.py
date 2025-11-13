# gunicorn.conf.py
import os, tempfile

bind = os.getenv("GUNICORN_BIND", "0.0.0.0:18000")
workers = int(os.getenv("GUNICORN_WORKERS", "2"))         # t3.medium → 2
worker_class = "uvicorn.workers.UvicornWorker"

graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", "30"))
timeout = int(os.getenv("GUNICORN_TIMEOUT", "60"))
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", "5"))

backlog = int(os.getenv("GUNICORN_BACKLOG", "2048"))
max_requests = int(os.getenv("GUNICORN_MAX_REQUESTS", "2000"))          # 누수 방지
max_requests_jitter = int(os.getenv("GUNICORN_MAX_REQUESTS_JITTER", "200"))

loglevel = os.getenv("GUNICORN_LOGLEVEL", "info")
accesslog = os.getenv("GUNICORN_ACCESSLOG", "-")  # '-'=stdout
errorlog = os.getenv("GUNICORN_ERRORLOG", "-")
capture_output = True

# Linux면 /dev/shm, 기타면 /tmp
worker_tmp_dir = os.getenv("GUNICORN_WORKER_TMP_DIR") or (
    "/dev/shm" if os.path.exists("/dev/shm") else tempfile.gettempdir()
)