"""
Tests for memory monitoring functionality.
"""
import unittest
from unittest.mock import patch, MagicMock
import tempfile
import os
from media_organizer.app.memory_monitor import MemoryMonitor, check_dataset_size_and_warn


class TestMemoryMonitor(unittest.TestCase):
    
    def test_estimate_memory_usage(self):
        """Test memory usage estimation for different file counts."""
        # Small dataset
        small_estimate = MemoryMonitor.estimate_memory_usage(100)
        self.assertGreater(small_estimate, 0)
        self.assertLess(small_estimate, 10)  # Should be less than 10MB
        
        # Large dataset
        large_estimate = MemoryMonitor.estimate_memory_usage(10000)
        self.assertGreater(large_estimate, small_estimate)
        self.assertGreater(large_estimate, 10)  # Should be more than 10MB
        
        # Massive dataset
        massive_estimate = MemoryMonitor.estimate_memory_usage(50000)
        self.assertGreater(massive_estimate, large_estimate)
    
    def test_check_large_dataset_warning(self):
        """Test large dataset warning thresholds."""
        # Small dataset - no warning
        small_warning = MemoryMonitor.check_large_dataset_warning(5000)
        self.assertIsNone(small_warning)
        
        # Large dataset - should get warning
        large_warning = MemoryMonitor.check_large_dataset_warning(15000)
        self.assertIsNotNone(large_warning)
        self.assertIn("Large dataset detected", large_warning)
        self.assertIn("15,000 files", large_warning)
        
        # Massive dataset - should get stronger warning
        massive_warning = MemoryMonitor.check_large_dataset_warning(60000)
        self.assertIsNotNone(massive_warning)
        self.assertIn("MASSIVE DATASET DETECTED", massive_warning)
        self.assertIn("60,000 files", massive_warning)
    
    @patch('psutil.virtual_memory')
    @patch('psutil.Process')
    def test_get_memory_info(self, mock_process, mock_virtual_memory):
        """Test memory information retrieval."""
        # Mock system memory
        mock_memory = MagicMock()
        mock_memory.percent = 75.5
        mock_memory.available = 4 * 1024**3  # 4GB
        mock_virtual_memory.return_value = mock_memory
        
        # Mock process memory
        mock_proc = MagicMock()
        mock_proc_info = MagicMock()
        mock_proc_info.rss = 200 * 1024**2  # 200MB
        mock_proc.memory_info.return_value = mock_proc_info
        mock_process.return_value = mock_proc
        
        system_percent, process_mb, available_gb = MemoryMonitor.get_memory_info()
        
        self.assertEqual(system_percent, 75.5)
        self.assertEqual(process_mb, 200.0)
        self.assertEqual(available_gb, 4.0)
    
    @patch('psutil.virtual_memory')
    @patch('psutil.Process')
    def test_check_memory_pressure(self, mock_process, mock_virtual_memory):
        """Test memory pressure detection."""
        # Mock high memory usage scenario
        mock_memory = MagicMock()
        mock_memory.percent = 85.0  # High system usage
        mock_memory.available = 0.5 * 1024**3  # Low available memory
        mock_virtual_memory.return_value = mock_memory
        
        mock_proc = MagicMock()
        mock_proc_info = MagicMock()
        mock_proc_info.rss = 600 * 1024**2  # High process memory
        mock_proc.memory_info.return_value = mock_proc_info
        mock_process.return_value = mock_proc
        
        warning = MemoryMonitor.check_memory_pressure()
        
        self.assertIsNotNone(warning)
        self.assertIn("MEMORY PRESSURE DETECTED", warning)
        self.assertIn("High system memory usage (85.0%)", warning)
        self.assertIn("High app memory usage (600.0MB)", warning)
        self.assertIn("Low available memory (0.5GB", warning)
    
    @patch('psutil.virtual_memory')
    @patch('psutil.Process')
    def test_check_memory_pressure_normal(self, mock_process, mock_virtual_memory):
        """Test memory pressure detection under normal conditions."""
        # Mock normal memory usage scenario
        mock_memory = MagicMock()
        mock_memory.percent = 60.0  # Normal system usage
        mock_memory.available = 4.0 * 1024**3  # Plenty of available memory
        mock_virtual_memory.return_value = mock_memory
        
        mock_proc = MagicMock()
        mock_proc_info = MagicMock()
        mock_proc_info.rss = 100 * 1024**2  # Normal process memory
        mock_proc.memory_info.return_value = mock_proc_info
        mock_process.return_value = mock_proc
        
        warning = MemoryMonitor.check_memory_pressure()
        
        self.assertIsNone(warning)
    
    def test_check_dataset_size_and_warn_small(self):
        """Test dataset size checking for small datasets."""
        result = check_dataset_size_and_warn(5000)
        self.assertTrue(result)  # Should proceed without warnings
    
    def test_check_dataset_size_and_warn_large_with_callback(self):
        """Test dataset size checking with callback for large datasets."""
        # Mock callback that returns True (user wants to continue)
        mock_callback = MagicMock(return_value=True)
        
        result = check_dataset_size_and_warn(15000, mock_callback)
        
        self.assertTrue(result)
        mock_callback.assert_called()
        
        # Check that the callback was called with appropriate warning
        call_args = mock_callback.call_args[0]
        self.assertEqual(call_args[0], "Large Dataset Warning")
        self.assertIn("15,000 files", call_args[1])
    
    def test_check_dataset_size_and_warn_user_cancels(self):
        """Test dataset size checking when user chooses to cancel."""
        # Mock callback that returns False (user wants to cancel)
        mock_callback = MagicMock(return_value=False)
        
        result = check_dataset_size_and_warn(15000, mock_callback)
        
        self.assertFalse(result)
        mock_callback.assert_called()


if __name__ == '__main__':
    unittest.main()
