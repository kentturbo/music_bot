import yt_dlp
import time
import os
import asyncio

async def test_download():
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'outtmpl': 'scratch/test_song.%(ext)s',
        'quiet': False,
    }
    
    query = "ytsearch1:44neverluv wanna sleep"
    print(f"Downloading and converting: '{query}'...")
    start = time.time()
    
    loop = asyncio.get_running_loop()
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = await loop.run_in_executor(
            None, lambda: ydl.extract_info(query, download=True)
        )
        print(f"Finished in {time.time() - start:.2f}s")
        if os.path.exists("scratch/test_song.mp3"):
            size = os.path.getsize("scratch/test_song.mp3")
            print(f"File created successfully: scratch/test_song.mp3 ({size / 1024 / 1024:.2f} MB)")
            os.remove("scratch/test_song.mp3")
        else:
            print("File not found!")

if __name__ == "__main__":
    asyncio.run(test_download())
