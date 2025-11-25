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

# Worker가 fork된 직후 Config를 로드하여 환경변수 설정
def post_fork(server, worker):
    """Worker가 fork된 후 Config를 로드하여 LangSmith 환경변수를 설정합니다."""
    from app.config import get_config
    config = get_config()
    # Config에서 이미 환경변수를 설정하므로 추가 작업 불필요
    worker.log.info(f"Worker {worker.pid}: Config 로드 완료, LangSmith API Key: {'SET' if config.LANGSMITH_API_KEY else 'NOT SET'}")