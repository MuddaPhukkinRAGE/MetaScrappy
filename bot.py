import os
import re
import time
import aiohttp
import discord
from discord import app_commands
from bs4 import BeautifulSoup
TOKEN = os.getenv("DISCORD_TOKEN")
BASE_URL = "https://metaforge.app/arc-raiders"
CACHE_SECONDS = 600
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=12)
intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)
price_cache = {}
def make_slug(item: str) -> str:
    """Convert an item name into a likely MetaForge item-page slug."""
    slug = item.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")
async def fetch_price(item: str):
    """Try to read the displayed 24-hour median from a MetaForge item page."""
    slug = make_slug(item)
    url = f"{BASE_URL}/database/item/{slug}"
    cached = price_cache.get(slug)
    if cached and time.time() - cached["time"] < CACHE_SECONDS:
        return cached["price"], cached["url"]
    headers = {
        "User-Agent": "Mozilla/5.0 MetaScrappy/1.0"
    }
    async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
        async with session.get(url, headers=headers) as response:
            if response.status != 200:
                return None, url
            html = await response.text()
    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text(" ", strip=True)
    # Only accept a price if the page explicitly labels it as a 24h median.
    patterns = [
        r"24\s*[- ]?hour\s*median[^0-9]{0,50}([\d,]+)",
        r"24h\s*median[^0-9]{0,50}([\d,]+)",
        r"median\s*\(24h\)[^0-9]{0,50}([\d,]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, page_text, re.IGNORECASE)
        if match:
            price = int(match.group(1).replace(",", ""))
            price_cache[slug] = {
                "price": price,
                "url": url,
                "time": time.time(),
            }
            return price, url
    return None, url
@tree.command(
    name="price",
    description="Look up an ARC Raiders Marketplace 24h Median price"
)
@app_commands.describe(item="The ARC Raiders item name")
async def price(interaction: discord.Interaction, item: str):
    # Acknowledge Discord immediately so the interaction doesn't expire.
    await interaction.response.defer(thinking=True)
    try:
        value, url = await fetch_price(item)
        if value is None:
            await interaction.followup.send(
                f"I couldn't verify the displayed 24h Median for **{item}**.\n"
                f"Please check the item page directly: {url}\n"
                "I won't guess the price if MetaForge doesn't expose it clearly."
            )
            return
        await interaction.followup.send(
            f"**{item} — {value:,} Assorted Seeds**\n"
            "Marketplace Value (24h Median)\n"
            f"Source: [MetaForge]({url})"
        )
    except (aiohttp.ClientError, TimeoutError) as error:
        print(f"PRICE LOOKUP NETWORK ERROR: {type(error).__name__}: {error}")
        await interaction.followup.send(
            "MetaForge didn't respond in time. Please try again shortly."
        )
    except Exception as error:
        print(f"PRICE LOOKUP ERROR: {type(error).__name__}: {error}")
        await interaction.followup.send(
            "The price lookup ran into an unexpected error. "
            "The error has been recorded in the bot logs."
        )
@client.event
async def on_ready():
    await tree.sync()
    print(f"MetaScrappy is online as {client.user}")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN environment variable is missing")
client.run(TOKEN)
