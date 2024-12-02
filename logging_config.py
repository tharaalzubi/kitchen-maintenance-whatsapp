# logging_config.py
import logging
import logging.handlers
import os
from datetime import datetime

def setup_logging():
    """Configure logging for the application"""
    # Create logs directory if it doesn't exist
    if not os.path.exists('logs'):
        os.makedirs('logs')

    # Generate log filename with timestamp
    log_filename = f'logs/kitchen_maintenance_{datetime.now().strftime("%Y%m%d")}.log'

    # Configure logging format
    log_format = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Setup file handler
    file_handler = logging.handlers.RotatingFileHandler(
        log_filename,
        maxBytes=10485760,  # 10MB
        backupCount=5
    )
    file_handler.setFormatter(log_format)

    # Setup console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_format)

    # Get root logger and configure
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if os.getenv('DEBUG', 'True').lower() == 'true' else logging.INFO)

    # Remove existing handlers if any
    root_logger.handlers = []

    # Add handlers
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Create specific loggers
    loggers = {
        'whatsapp': logging.getLogger('whatsapp'),
        'database': logging.getLogger('database'),
        'maintenance': logging.getLogger('maintenance'),
        'session': logging.getLogger('session')
    }

    # Configure specific loggers
    for logger_name, logger in loggers.items():
        logger.setLevel(logging.DEBUG if os.getenv('DEBUG', 'True').lower() == 'true' else logging.INFO)
        logger.handlers = []  # Remove existing handlers
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        logger.propagate = False

    return loggers

# Usage example:
# loggers = setup_logging()
# whatsapp_logger = loggers['whatsapp']
# whatsapp_logger.debug('Sending WhatsApp message')