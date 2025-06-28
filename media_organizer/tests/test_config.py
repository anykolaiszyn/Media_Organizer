from media_organizer.app.config import SUPPORTED_FORMATS, IMAGE_FORMATS, VIDEO_FORMATS

def test_supported_formats():
    assert '.jpg' in SUPPORTED_FORMATS
    assert '.mp4' in SUPPORTED_FORMATS
    assert all(f in SUPPORTED_FORMATS for f in IMAGE_FORMATS)
    assert all(f in SUPPORTED_FORMATS for f in VIDEO_FORMATS)
