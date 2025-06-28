from datetime import datetime


class Logger:
    def __init__(self, log_file=None):
        self.log_file = log_file

    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg = f"[{timestamp}] [{level}] {message}"
        print(msg)
        if self.log_file:
            try:
                with open(self.log_file, 'a', encoding='utf-8') as f:
                    f.write(msg + '\n')
            except Exception:
                pass  # Don't crash on log file errors

    def info(self, message):
        self.log(message, "INFO")

    def warning(self, message):
        self.log(message, "WARNING")

    def error(self, message):
        self.log(message, "ERROR")


# Default global logger instance
logger = Logger()
log = logger.info
