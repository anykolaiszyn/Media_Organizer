"""
Quick test script to verify memory monitoring functionality.
"""
import sys
import os

# Add the project root to the path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from media_organizer.app.memory_monitor import MemoryMonitor, check_dataset_size_and_warn
from media_organizer.app.logger import logger

def test_memory_monitoring():
    """Test memory monitoring functionality with various dataset sizes."""
    
    logger.info("=== Memory Monitoring Test ===")
    
    # Test current memory info
    logger.info("1. Current Memory Information:")
    system_percent, process_mb, available_gb = MemoryMonitor.get_memory_info()
    logger.info(f"   System Memory: {system_percent:.1f}% used")
    logger.info(f"   Process Memory: {process_mb:.1f}MB")
    logger.info(f"   Available Memory: {available_gb:.1f}GB")
    
    # Test memory estimation
    logger.info("2. Memory Usage Estimation:")
    test_sizes = [1000, 10000, 25000, 50000]
    for size in test_sizes:
        estimated = MemoryMonitor.estimate_memory_usage(size)
        logger.info(f"   {size:,} files: ~{estimated:.1f}MB estimated")
    
    # Test dataset warnings
    logger.info("3. Dataset Size Warnings:")
    test_sizes = [5000, 15000, 60000]
    for size in test_sizes:
        warning = MemoryMonitor.check_large_dataset_warning(size)
        if warning:
            logger.info(f"   {size:,} files: Warning triggered")
            logger.info(f"   First line: {warning.split(chr(10))[0]}")
        else:
            logger.info(f"   {size:,} files: No warning")
    
    # Test memory pressure check
    logger.info("4. Memory Pressure Check:")
    pressure_warning = MemoryMonitor.check_memory_pressure()
    if pressure_warning:
        logger.warning("   Memory pressure detected!")
        logger.warning(f"   Warning: {pressure_warning.split(chr(10))[0]}")
    else:
        logger.info("   Memory pressure: Normal")
    
    # Test with mock callback
    logger.info("5. Dataset Check with Mock Callback:")
    def mock_callback(title, message):
        logger.info(f"   Callback called: {title}")
        logger.info(f"   Message preview: {message[:50]}...")
        return True  # User chooses to continue
    
    result = check_dataset_size_and_warn(15000, mock_callback)
    logger.info(f"   Result: {'Proceed' if result else 'Cancel'}")
    
    logger.info("=== Test Complete ===")


if __name__ == "__main__":
    test_memory_monitoring()
