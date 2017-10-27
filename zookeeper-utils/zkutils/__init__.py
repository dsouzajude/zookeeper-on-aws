import os
import logging
from logging.config import dictConfig


__author__ = "Jude D'Souza <dsouza_jude@hotmail.com>"
__version_info__ = (0, 1)
__version__ = '.'.join(map(str, __version_info__))


log_levels = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL
}


def setup_logging():
    log_level = os.environ.get('LOG_LEVEL', 'INFO')
    log_level = log_levels.get(log_level, logging.INFO)
    logging_config = dict(
        version = 1,
        formatters = {
            'simple': {
                'format': '%(asctime)s %(levelname)-8s %(message)s'
            }
        },
        handlers = {
            'console': {
                'class': 'logging.StreamHandler',
                'formatter': 'simple',
                'level': log_level,
                'stream': 'ext://sys.stdout'
            },
            'file': {
                'class': 'logging.handlers.RotatingFileHandler',
                'formatter': 'simple',
                'level': log_level,
                'filename': '/var/log/zkutils.log',
                'mode': 'a',
                'maxBytes': 10485760,
                'backupCount': 5
            }
        },
        root = {
            'handlers': ['console', 'file'],
            'level': log_level,
        },
    )
    dictConfig(logging_config)
    return logging.getLogger(__name__)


setup_logging()
