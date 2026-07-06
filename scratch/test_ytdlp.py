import yt_dlp
import asyncio

async def test_yt_dlp():
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'ignoreerrors': True,
    }
    
    query = "ytsearch1:44neverluv wanna sleep"
    print(f"Searching YouTube for: '{query}'...")
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(query, download=False)
        if 'entries' in info and info['entries']:
            entry = info['entries'][0]
            print("Title:", entry.get('title'))
            print("Duration:", entry.get('duration'))
            print("Direct URL:", entry.get('url')[:100] + "...")
        else:
            print("No entries found.")

if __name__ == "__main__":
    asyncio.run(test_yt_dlp())
