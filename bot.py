import os
import asyncio
import discord
from discord.ext import tasks

TOKEN = os.environ.get("MTM4MjI3MjU1NzMxODkzNDY1MA.GYb1z1.WdMVYfyWB-916mcPQZwatS83ai3FVkZuxbdOqc")  # Token bota
CHANNEL_ID = int(os.environ.get("1438609894495354921", 0))

client = discord.Client(intents=discord.Intents.default())
message = None

async def update_clock():
    global message
    channel = client.get_channel(CHANNEL_ID)
    if channel is None:
        print("Nie można znaleźć kanału!")
        return

    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("http://localhost:10000/clock") as resp:
                    clock_text = await resp.text()
            if message is None:
                message = await channel.send(clock_text)
            else:
                await message.edit(content=clock_text)
        except Exception as e:
            print("Błąd aktualizacji zegara:", e)
        await asyncio.sleep(1)

@client.event
async def on_ready():
    print(f"Bot zalogowany jako {client.user}")
    client.loop.create_task(update_clock())

client.run(TOKEN)
