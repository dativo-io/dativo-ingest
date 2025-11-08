#!/usr/bin/env python3
"""
Generate audio file from the pluggable readers explanation script.

Usage:
    python generate_audio.py

Output:
    pluggable_readers_explained.mp3 (~25 minutes)
"""

import os
import sys

def generate_audio_gtts():
    """Generate audio using gTTS (Google Text-to-Speech)."""
    try:
        from gtts import gTTS
    except ImportError:
        print("ERROR: gTTS not installed.")
        print("Install with: pip install gtts")
        return False
    
    script_path = '/workspace/PLUGGABLE_READERS_AUDIO_SCRIPT.txt'
    output_path = 'pluggable_readers_explained.mp3'
    
    print("Reading script...")
    with open(script_path, 'r') as f:
        text = f.read()
    
    print(f"Generating audio (~25 minutes)...")
    print("This may take 30-60 seconds...")
    
    tts = gTTS(text=text, lang='en', slow=False)
    tts.save(output_path)
    
    file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
    
    print(f"\n✅ SUCCESS!")
    print(f"   File: {output_path}")
    print(f"   Size: {file_size_mb:.1f} MB")
    print(f"   Duration: ~25 minutes")
    print(f"\nYou can now listen to the explanation!")
    
    return True

def generate_audio_macos():
    """Generate audio using macOS 'say' command."""
    if sys.platform != 'darwin':
        return False
    
    script_path = '/workspace/PLUGGABLE_READERS_AUDIO_SCRIPT.txt'
    output_path = 'pluggable_readers_explained.aiff'
    
    print("Using macOS 'say' command...")
    print("Generating audio (~25 minutes)...")
    
    # Try with Alex voice (high quality)
    cmd = f'say -v Alex -f "{script_path}" -o "{output_path}"'
    result = os.system(cmd)
    
    if result == 0:
        file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
        
        print(f"\n✅ SUCCESS!")
        print(f"   File: {output_path}")
        print(f"   Size: {file_size_mb:.1f} MB")
        print(f"   Duration: ~25 minutes")
        print(f"\nTo convert to MP3 (requires ffmpeg):")
        print(f"   ffmpeg -i {output_path} pluggable_readers_explained.mp3")
        
        return True
    
    return False

def main():
    print("=" * 60)
    print("PLUGGABLE READERS/WRITERS - AUDIO GENERATOR")
    print("=" * 60)
    print()
    
    # Try macOS first (faster, better quality)
    if sys.platform == 'darwin':
        print("Detected: macOS")
        print("Attempting to use built-in 'say' command...\n")
        if generate_audio_macos():
            return
        else:
            print("\n'say' command failed. Falling back to gTTS...\n")
    
    # Fall back to gTTS
    print("Using gTTS (Google Text-to-Speech)...\n")
    if generate_audio_gtts():
        return
    
    # If all failed
    print("\n❌ Could not generate audio.")
    print("\nPlease try one of these options:")
    print("1. Install gTTS: pip install gtts")
    print("2. Use online service: https://ttsmaker.com")
    print("3. Read: /workspace/HOW_TO_GENERATE_AUDIO.md")

if __name__ == '__main__':
    main()
