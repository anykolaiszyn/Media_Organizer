from abc import ABC, abstractmethod

class IMetadataExtractor(ABC):
    @abstractmethod
    def extract_datetime(self, file_path):
        """Return a datetime string or None for the given file."""
        pass
