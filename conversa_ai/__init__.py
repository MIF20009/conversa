# Import Celery app when Django starts (only if Celery is available)
try:
    from .celery import app as celery_app
    __all__ = ('celery_app',)
except ImportError:
    # Celery not available, skip initialization
    celery_app = None
    __all__ = ()
