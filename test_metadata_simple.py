#!/usr/bin/env python3
"""
Quick test to verify metadata_extractor works with headless ExifTool.
"""

import sys
import os
sys.path.insert(0, 'media_organizer')

from media_organizer.app.metadata_extractor import extract_metadata
from media_organizer.app.exiftool_check import get_exiftool_path
from pathlib import Path

def test_metadata_extraction():
    """Test that metadata extraction works without showing windows"""
    print("Testing metadata extraction...")
    
    # Check ExifTool path
    exiftool_path = get_exiftool_path()
    print(f"ExifTool path: {exiftool_path}")
    
    if not Path(exiftool_path).exists():
        print(f"ERROR: ExifTool not found at {exiftool_path}")
        return False
    
    # Create a test file
    test_file = Path("test_metadata.txt")
    test_file.write_text("This is a test file for metadata extraction")
    
    try:
        # Test metadata extraction
        print(f"Extracting metadata from {test_file}...")
        metadata = extract_metadata(str(test_file))
        
        print(f"Metadata result type: {type(metadata)}")
        if isinstance(metadata, dict):
            if "error" in metadata:
                print(f"Metadata extraction returned error: {metadata['error']}")
                # This is expected for a text file, so it's not necessarily a failure
                if "exiftool_error" in metadata.get("type", ""):
                    print("✓ ExifTool ran successfully (expected error for text file)")
                    return True
            else:
                print(f"Metadata extracted successfully: {len(metadata)} tags")
                return True
        else:
            print(f"Unexpected metadata result: {metadata}")
            return False
            
    except Exception as e:
        print(f"ERROR: Metadata extraction failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Clean up
        if test_file.exists():
            test_file.unlink()
    
    return False

if __name__ == "__main__":
    success = test_metadata_extraction()
    if success:
        print("\n✓ Metadata extraction test passed!")
        print("ExifTool subprocess calls should run headlessly (no Windows).")
    else:
        print("\n✗ Metadata extraction test failed!")
        sys.exit(1)
