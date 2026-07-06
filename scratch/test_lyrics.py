import sys
import os

# Add root folder to sys.path so we can import from bot
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bot.config import settings
import lyricsgenius

def main():
    token = settings.genius_access_token.get_secret_value()
    print("Genius Token:", token[:20] if token else "None")
    
    genius = lyricsgenius.Genius(
        token,
        timeout=10,
        retries=2,
        remove_section_headers=False,
    )
    
    # Let's see the current headers
    print("Default Headers:", genius._session.headers)
    
    # Try search
    try:
        print("Searching lyrics without custom headers...")
        song = genius.search_song("wanna sleep", "44neverluv")
        if song:
            print("Found lyrics:", song.lyrics[:100] + "...")
        else:
            print("Song not found.")
    except Exception as e:
        print("Failed:", e)

    # Let's try changing the User-Agent
    genius._session.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    print("\nModified Headers:", genius._session.headers)
    
    try:
        print("Searching lyrics with custom User-Agent...")
        song = genius.search_song("wanna sleep", "44neverluv")
        if song:
            print("Found lyrics:", song.lyrics[:100] + "...")
        else:
            print("Song not found.")
    except Exception as e:
        print("Failed:", e)

if __name__ == "__main__":
    main()
