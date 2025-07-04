"""
Memory monitoring utilities for the Media Organizer app.
Provides functions to monitor memory usage and warn about large datasets.
"""
import psutil
import os
from typing import Optional, Tuple
from .logger import log


class MemoryMonitor:
    """Monitor system and process memory usage."""
    
    # Memory usage thresholds
    LARGE_DATASET_WARNING = 10000  # Files count threshold
    MASSIVE_DATASET_WARNING = 50000  # Files count threshold  
    MEMORY_WARNING_PERCENT = 80  # System memory usage threshold (%)
    PROCESS_MEMORY_WARNING_MB = 500  # Process memory threshold (MB)
    
    @staticmethod
    def get_memory_info() -> Tuple[float, float, float]:
        """
        Get current memory usage information.
        
        Returns:
            Tuple of (system_memory_percent, process_memory_mb, available_memory_gb)
        """
        try:
            # System memory
            system_memory = psutil.virtual_memory()
            system_percent = system_memory.percent
            available_gb = system_memory.available / (1024**3)
            
            # Current process memory
            process = psutil.Process(os.getpid())
            process_memory_mb = process.memory_info().rss / (1024**2)
            
            return system_percent, process_memory_mb, available_gb
            
        except (psutil.Error, OSError) as e:
            log(f"Warning: Could not get memory information: {e}")
            return 0.0, 0.0, 0.0
    
    @staticmethod
    def estimate_memory_usage(file_count: int) -> float:
        """
        Estimate memory usage for processing a given number of files.
        
        Args:
            file_count: Number of files to process
            
        Returns:
            Estimated memory usage in MB
        """
        # Rough estimation based on:
        # - File path strings (~200 bytes average)
        # - Metadata dictionaries (~2KB average per file)
        # - SQLite overhead (~1KB per record)
        # - Python object overhead (~500 bytes per file)
        
        bytes_per_file = 200 + 2048 + 1024 + 500  # ~3.8KB per file
        estimated_mb = (file_count * bytes_per_file) / (1024**2)
        
        # Add 50% buffer for overhead and peak usage
        return estimated_mb * 1.5
    
    @staticmethod
    def check_large_dataset_warning(file_count: int) -> Optional[str]:
        """
        Check if file count warrants a warning and return appropriate message.
        
        Args:
            file_count: Number of files found
            
        Returns:
            Warning message if threshold exceeded, None otherwise
        """
        if file_count >= MemoryMonitor.MASSIVE_DATASET_WARNING:
            estimated_mb = MemoryMonitor.estimate_memory_usage(file_count)
            return (
                f"⚠️ MASSIVE DATASET DETECTED ({file_count:,} files)\n\n"
                f"This operation may use approximately {estimated_mb:.0f}MB of memory.\n"
                f"Consider processing in smaller batches if you experience performance issues.\n\n"
                f"Recommendations:\n"
                f"• Close other applications to free memory\n"
                f"• Process subfolders individually\n"
                f"• Consider using a machine with more RAM for large operations"
            )
        elif file_count >= MemoryMonitor.LARGE_DATASET_WARNING:
            estimated_mb = MemoryMonitor.estimate_memory_usage(file_count)
            return (
                f"📊 Large dataset detected ({file_count:,} files)\n\n"
                f"Estimated memory usage: ~{estimated_mb:.0f}MB\n"
                f"The app will use SQLite pagination to handle this efficiently."
            )
        
        return None
    
    @staticmethod
    def check_memory_pressure() -> Optional[str]:
        """
        Check current memory pressure and return warning if needed.
        
        Returns:
            Warning message if memory pressure is high, None otherwise
        """
        system_percent, process_mb, available_gb = MemoryMonitor.get_memory_info()
        
        warnings = []
        
        if system_percent >= MemoryMonitor.MEMORY_WARNING_PERCENT:
            warnings.append(
                f"⚠️ High system memory usage ({system_percent:.1f}%)"
            )
        
        if process_mb >= MemoryMonitor.PROCESS_MEMORY_WARNING_MB:
            warnings.append(
                f"⚠️ High app memory usage ({process_mb:.1f}MB)"
            )
        
        if available_gb < 1.0:
            warnings.append(
                f"⚠️ Low available memory ({available_gb:.1f}GB remaining)"
            )
        
        if warnings:
            message = "MEMORY PRESSURE DETECTED:\n" + "\n".join(warnings)
            message += "\n\nRecommendations:\n"
            message += "• Close other applications\n"
            message += "• Process fewer files at once\n"
            message += "• Restart the application to free memory"
            return message
        
        return None
    
    @staticmethod 
    def log_memory_stats(context: str = ""):
        """Log current memory statistics for debugging."""
        system_percent, process_mb, available_gb = MemoryMonitor.get_memory_info()
        
        log(f"[MEMORY] {context}")
        log(f"[MEMORY] System: {system_percent:.1f}% used, {available_gb:.1f}GB available")
        log(f"[MEMORY] Process: {process_mb:.1f}MB used")


def check_dataset_size_and_warn(file_count: int, show_dialog_callback=None) -> bool:
    """
    Check dataset size and show warnings if needed.
    
    Args:
        file_count: Number of files found
        show_dialog_callback: Optional callback to show warning dialogs
        
    Returns:
        True if user should proceed, False if they chose to cancel
    """
    # Always log memory stats for large datasets
    if file_count >= MemoryMonitor.LARGE_DATASET_WARNING:
        MemoryMonitor.log_memory_stats(f"Before processing {file_count:,} files")
    
    # Check for large dataset warning
    dataset_warning = MemoryMonitor.check_large_dataset_warning(file_count)
    if dataset_warning and show_dialog_callback:
        if not show_dialog_callback("Large Dataset Warning", dataset_warning):
            return False
    elif dataset_warning:
        log(f"[WARNING] {dataset_warning}")
    
    # Check for memory pressure
    memory_warning = MemoryMonitor.check_memory_pressure()
    if memory_warning and show_dialog_callback:
        if not show_dialog_callback("Memory Pressure Warning", memory_warning):
            return False
    elif memory_warning:
        log(f"[WARNING] {memory_warning}")
    
    return True
