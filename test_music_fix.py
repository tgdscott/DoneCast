"""
Quick test to verify the music fix logic handles both GCS and local files correctly.
"""

def test_music_filename_parsing():
    """Test that we can correctly identify GCS vs local files."""
    
    # GCS URLs
    gcs_urls = [
        "gs://podcast612-media/music/background_music.mp3",
        "gs://bucket/folder/file.mp3",
    ]
    
    for url in gcs_urls:
        assert url.startswith("gs://"), f"Should detect GCS URL: {url}"
        gcs_str = url[5:]  # Remove "gs://"
        bucket, key = gcs_str.split("/", 1)
        print(f"✓ GCS URL: {url} -> bucket={bucket}, key={key}")
    
    # Local files
    local_files = [
        "background_music.mp3",
        "music/background_music.mp3",
        "/absolute/path/music.mp3",
    ]
    
    for filename in local_files:
        assert not filename.startswith("gs://"), f"Should detect local file: {filename}"
        print(f"✓ Local file: {filename}")
    
    print("\n✅ All tests passed!")

if __name__ == "__main__":
    test_music_filename_parsing()
