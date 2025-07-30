
import asyncio
import aiohttp
import os

URL = f"https://{os.getenv('WEBHOOK_HOST')}"

async def keep_alive():
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(URL) as response:
                    print(f"Pinged {URL}: {response.status}")
        except Exception as e:
            print(f"Keep-alive error: {e}")
        await asyncio.sleep(30)
        
