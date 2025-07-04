from datetime import datetime
import os
from typing import Union


class Logger:
    """
    Logger class with configurable log levels and environment-based configuration.
    
    Log levels (in order of severity):
    - DEBUG (10): Detailed information for debugging
    - INFO (20): General information messages
    - WARNING (30): Warning messages for potential issues
    - ERROR (40): Error messages for serious problems
    
    Environment Variables:
    - MEDIA_ORGANIZER_LOG_LEVEL: Set log level (DEBUG, INFO, WARNING, ERROR)
      Default: INFO
      
    Usage:
    - Set to DEBUG to see all debug output: $env:MEDIA_ORGANIZER_LOG_LEVEL="DEBUG"
    - Set to WARNING to see only warnings and errors: $env:MEDIA_ORGANIZER_LOG_LEVEL="WARNING"
    """
    # Log level constants
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    
    LEVEL_NAMES = {
        DEBUG: "DEBUG",
        INFO: "INFO", 
        WARNING: "WARNING",
        ERROR: "ERROR"
    }
    
    def __init__(self, log_file=None, level=None):
        self.log_file = log_file
        # Set default log level based on environment variable or default to INFO
        if level is None:
            env_level = os.environ.get('MEDIA_ORGANIZER_LOG_LEVEL', 'INFO').upper()
            level_map = {
                'DEBUG': self.DEBUG,
                'INFO': self.INFO,
                'WARNING': self.WARNING,
                'ERROR': self.ERROR
            }
            self.level = level_map.get(env_level, self.INFO)
        else:
            self.level = level

    def should_log(self, level: int) -> bool:
        """Check if a message at the given level should be logged."""
        return level >= self.level

    def log(self, message: str, level: Union[str, int] = "INFO") -> None:
        """Log a message at the specified level."""
        # Convert string level to numeric if needed
        if isinstance(level, str):
            level_map = {
                'DEBUG': self.DEBUG,
                'INFO': self.INFO,
                'WARNING': self.WARNING,
                'ERROR': self.ERROR
            }
            numeric_level = level_map.get(level.upper(), self.INFO)
        else:
            numeric_level = level
        # Convert string level to numeric if needed
        if isinstance(level, str):
            level_map = {
                'DEBUG': self.DEBUG,
                'INFO': self.INFO,
                'WARNING': self.WARNING,
                'ERROR': self.ERROR
            }
            numeric_level = level_map.get(level.upper(), self.INFO)
        else:
            numeric_level = level
        
        # Skip logging if level is below threshold
        if not self.should_log(numeric_level):
            return
            
        level_name = self.LEVEL_NAMES.get(numeric_level, "INFO")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg = f"[{timestamp}] [{level_name}] {message}"
        
        # Always print to console (the UI log window captures this)
        print(msg)
        
        if self.log_file:
            try:
                with open(self.log_file, 'a', encoding='utf-8') as f:
                    f.write(msg + '\n')
            except (FileNotFoundError, PermissionError) as e:
                # Print to console as fallback if log file is inaccessible
                print(f"[LOG ERROR] Cannot write to log file {self.log_file}: {e}")
            except OSError as e:
                # Handle disk full, read-only filesystem, etc.
                print(f"[LOG ERROR] Filesystem error writing to {self.log_file}: {e}")
            except UnicodeEncodeError as e:
                # Handle encoding issues with non-ASCII characters
                print(f"[LOG ERROR] Encoding error writing to {self.log_file}: {e}")
            except Exception as e:
                # Catch any other unexpected errors but still provide context
                print(f"[LOG ERROR] Unexpected error writing to {self.log_file}: {e}")
                # Don't crash on log file errors, but at least log the issue

    def debug(self, message: str) -> None:
        """Log debug message (only shown when log level is DEBUG)."""
        self.log(message, self.DEBUG)

    def info(self, message: str) -> None:
        """Log informational message."""
        self.log(message, self.INFO)

    def warning(self, message: str) -> None:
        """Log warning message."""
        self.log(message, self.WARNING)

    def error(self, message: str) -> None:
        """Log error message."""
        self.log(message, self.ERROR)

    def set_level(self, level: int) -> None:
        """Set the logging level."""
        self.level = level


# Default global logger instance
logger = Logger()
log = logger.info
