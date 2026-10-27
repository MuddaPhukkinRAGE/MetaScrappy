import os
import re
import time

import aiohttp
import discord
from discord import app_commands
from bs4 import BeautifulSoup

TOKEN = os.getenv("DISCORD_TOKEN")

BASE_URL = "https://metaforge.app/arc-raiders/database/item/"
CACHE_SECONDS = 600

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

price_cache = {}


def make_slug(item: str) -> str:
    """Convert an item name into a likely MetaForge page slug."""
    slug = item.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


async def fetch_price(item: str):
    """Read the displayed 24-hour median from a MetaForge item page."""
    slug = make_slug(item)
    url = BASE_URL + slug

    cached = price_cache.get(slug)
    if cached and time.time() - cached["time"] < CACHE_SECONDS:
        return cached["price"], cached["url"]

    timeout = aiohttp.ClientTimeout(total=20)
    headers = {
        "User-Agent": "Mozilla/5.0 MetaScrappy/1.0"
    }

    async with aiohttp.ClientSession(
        timeout=timeout,
        headers=headers
    ) as session:
        async with session.get(url) as response:
            if response.status == 404:
                return None, url

            response.raise_for_status()
            html = await response.text()

    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text(" ", strip=True)

    match = re.search(
        r"MetaForge Marketplace Value\s*\(24h Median\)\s*"
        r"([\d,]+)\s*Seeds",
        page_text,
        re.IGNORECASE,
    )

    if not match:
        print(f"PRICE LOOKUP ERROR: 24h Median not found on {url}")
        return None, url

    price = int(match.group(1).replace(",", ""))

    price_cache[slug] = {
        "price": price,
        "url": url,
        "time": time.time(),
    }

    return price, url


@tree.command(
    name="price",
    description="Look up an ARC Raiders Marketplace price"
)
@app_commands.describe(item="The ARC Raiders item name")
async def price(interaction: discord.Interaction, item: str):
    await interaction.response.defer(thinking=True)

    try:
        value, url = await fetch_price(item)

        if value is None:
            await interaction.followup.send(
                f"I couldn't find a readable 24h Median for "
                f"**{item}**.\n"
                f"Check the item name or open the "
                f"[MetaForge page]({url})."
            )
            return

        await interaction.followup.send(
            f"**{item} — {value:,} Seeds**\n"
            f"Marketplace Value (24h Median)\n"
            f"Source: [MetaForge]({url})"
        )

    except Exception as error:
        print(
            f"PRICE LOOKUP ERROR: "
            f"{type(error).__name__}: {error}"
        )
        await interaction.followup.send(
            f"Price lookup failed: `{type(error).__name__}`. "
            "Check Render logs for details."
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
