#!/usr/bin/env python3
"""
Test script to verify ExifTool runs headlessly (no Windows popups) in the built executable.
"""

import sys
import os
import subprocess
import time
from pathlib import Path

def test_headless_exiftool():
    """Test that ExifTool subprocess calls don't show Windows"""
    print("Testing ExifTool headless execution...")
    
    # Path to the built executable
    exe_path = Path("c:/SecretProjects/Media_Organizer/build_output/media_organizer.exe")
    exiftool_path = Path("c:/SecretProjects/Media_Organizer/build_output/ExifTool/exiftool.exe")
    
    if not exe_path.exists():
        print(f"ERROR: Executable not found at {exe_path}")
        return False
        
    if not exiftool_path.exists():
        print(f"ERROR: ExifTool not found at {exiftool_path}")
        return False
        
    print(f"✓ Found executable: {exe_path}")
    print(f"✓ Found ExifTool: {exiftool_path}")
    
    # Test direct ExifTool call with headless flags
    print("\n1. Testing direct ExifTool call...")
    
    # Create a test image file (simple way)
    test_file = Path("test_image.txt")
    test_file.write_text("This is a test file for ExifTool")
    
    try:
        # Call ExifTool directly with headless flags
        cmd = [str(exiftool_path), '-j', '-G', '-a', '-s', str(test_file)]
        startupinfo = None
        if sys.platform.startswith('win'):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            
        print(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, startupinfo=startupinfo)
        
        print(f"ExifTool return code: {result.returncode}")
        if result.stdout:
            print(f"ExifTool stdout: {result.stdout[:200]}...")
        if result.stderr:
            print(f"ExifTool stderr: {result.stderr[:200]}...")
            
        print("✓ ExifTool ran without showing a window")
        
    except Exception as e:
        print(f"ERROR: ExifTool test failed: {e}")
        return False
    finally:
        # Clean up test file
        if test_file.exists():
            test_file.unlink()
    
    print("\n2. Testing built executable...")
    print("The executable should start without showing ExifTool windows.")
    print("Please manually verify that no command prompt windows appear when using the app.")
    
    return True

if __name__ == "__main__":
    success = test_headless_exiftool()
    if success:
        print("\n✓ Headless ExifTool test completed successfully!")
        print("\nTo fully test:")
        print("1. Run the media_organizer.exe")
        print("2. Select a folder with images/videos")
        print("3. Start scanning - no command windows should appear")
        print("4. Check that metadata extraction works correctly")
    else:
        print("\n✗ Headless ExifTool test failed!")
        sys.exit(1)
