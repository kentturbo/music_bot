import yt_dlp
import time
import os
import asyncio

async def test_download_m4a():
    ydl_opts = {
        'format': 'bestaudio[ext=m4a]/best[ext=aac]/best',
        'outtmpl': 'scratch/test_song.%(ext)s',
        'quiet': False,
    }
    
    query = "ytsearch1:44neverluv wanna sleep"
    print(f"Downloading raw m4a: '{query}'...")
    start = time.time()
    
    loop = asyncio.get_running_loop()
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = await loop.run_in_executor(
            None, lambda: ydl.extract_info(query, download=True)
        )
        print(f"Finished in {time.time() - start:.2f}s")
        # Check files
        for f in os.listdir("scratch"):
            if f.startswith("test_song"):
                print(f"File: {f} ({os.path.getsize(os.path.join('scratch', f)) / 1024 / 1024:.2f} MB)")
                os.remove(os.path.join("scratch", f))

if __name__ == "__main__":
    asyncio.run(test_download_m4a())
