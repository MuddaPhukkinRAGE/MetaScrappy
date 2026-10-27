import os
import re
import time
import aiohttp
import discord
from discord import app_commands
from bs4 import BeautifulSoup
TOKEN = os.getenv("DISCORD_TOKEN")
BASE_URL = "https://metaforge.app/arc-raiders"
API_BASE_URL = "https://metaforge.app/api/arc-raiders"
CACHE_SECONDS = 600
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15)
intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)
price_cache = {}
def make_slug(item: str) -> str:
    slug = item.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")
async def fetch_price(item: str):
    slug = make_slug(item)
    item_url = f"{BASE_URL}/database/item/{slug}"
    cached = price_cache.get(slug)
    if cached and time.time() - cached["time"] < CACHE_SECONDS:
        return cached["price"], cached["url"]
    headers = {
        "User-Agent": "Mozilla/5.0 MetaScrappy/1.0",
        "Accept": "text/html,application/json",
    }
    async with aiohttp.ClientSession(
        timeout=REQUEST_TIMEOUT,
        headers=headers,
    ) as session:
        async with session.get(
            item_url,
            allow_redirects=True,
        ) as response:
            if response.status != 200:
                print(
                    f"PRICE LOOKUP: Item page returned "
                    f"HTTP {response.status}: {item_url}"
                )
                return None, item_url
            html = await response.text()
    soup = BeautifulSoup(html, "html.parser")
    # First try the rendered page text.
    page_text = soup.get_text(" ", strip=True)
    # Only accept a number located after the exact Marketplace Value
    # heading. Do not use the unrelated historical median endpoint.
    patterns = [
        (
            r"MetaForge\s+Marketplace\s+Value\s*"
            r"\(\s*24h\s+Median\s*\)\s*"
            r"([\d,]+)\s*Seeds?"
        ),
        (
            r"Marketplace\s+Value\s*"
            r"\(\s*24h\s+Median\s*\)\s*"
            r"([\d,]+)\s*Seeds?"
        ),
    ]
    for pattern in patterns:
        match = re.search(
            pattern,
            page_text,
            re.IGNORECASE,
        )
        if match:
            price = int(match.group(1).replace(",", ""))
            price_cache[slug] = {
                "price": price,
                "url": item_url,
                "time": time.time(),
            }
            print(
                f"PRICE LOOKUP SUCCESS: {item} = "
                f"{price} Seeds"
            )
            return price, item_url
    # The page may be JavaScript-rendered, meaning the visible price
    # is not present in the initial HTML. Record useful diagnostics.
    print(
        f"PRICE LOOKUP: Could not find the displayed "
        f"24h Median in the HTML for {item}. "
        f"Page title: {soup.title.get_text(strip=True) if soup.title else 'None'}"
    )
    return None, item_url
@tree.command(
    name="price",
    description="Look up an ARC Raiders Marketplace 24h Median price",
)
@app_commands.describe(
    item="The ARC Raiders item name",
)
async def price(
    interaction: discord.Interaction,
    item: str,
):
    # Acknowledge Discord immediately before making network requests.
    await interaction.response.defer(thinking=True)
    try:
        value, item_url = await fetch_price(item)
        if value is None:
            await interaction.followup.send(
                f"I couldn't verify the displayed 24h Median "
                f"for **{item}**.\n"
                f"Check the item page: {item_url}\n"
                "I won't guess the price if MetaForge doesn't "
                "expose it in the page HTML."
            )
            return
        await interaction.followup.send(
            f"**{item} — {value:,} Assorted Seeds**\n"
            "Marketplace Value (24h Median)\n"
            f"Source: [MetaForge]({item_url})"
        )
    except (aiohttp.ClientError, TimeoutError) as error:
        print(
            f"PRICE LOOKUP NETWORK ERROR: "
            f"{type(error).__name__}: {error}"
        )
        await interaction.followup.send(
            "MetaForge didn't respond in time. "
            "Please try again shortly."
        )
    except Exception as error:
        print(
            f"PRICE LOOKUP ERROR: "
            f"{type(error).__name__}: {error}"
        )
        await interaction.followup.send(
            "The price lookup encountered an unexpected error. "
            "Please check the bot logs."
        )
@client.event
async def on_ready():
    await tree.sync()
    print(f"MetaScrappy is online as {client.user}")
if not TOKEN:
    raise RuntimeError(
        "DISCORD_TOKEN environment variable is missing"
    )
client.run(TOKEN)
