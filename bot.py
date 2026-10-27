import os
import re
import time
import aiohttp
import discord
from discord import app_commands
TOKEN = os.getenv("DISCORD_TOKEN")
BASE_URL = "https://metaforge.app/arc-raiders"
API_BASE_URL = "https://metaforge.app/api/arc-raiders"
CACHE_SECONDS = 600
ITEM_CACHE_SECONDS = 3600
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15)
intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)
price_cache = {}
item_names = []
item_cache_time = 0
def make_slug(item):
    slug = item.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")
async def load_item_names():
    global item_names, item_cache_time
    if item_names and time.time() - item_cache_time < ITEM_CACHE_SECONDS:
        return item_names
    url = f"{API_BASE_URL}/items"
    headers = {
        "User-Agent": "Mozilla/5.0 MetaScrappy/1.0",
        "Accept": "application/json",
    }
    try:
        async with aiohttp.ClientSession(
            timeout=REQUEST_TIMEOUT,
            headers=headers,
        ) as session:
            async with session.get(url) as response:
                response.raise_for_status()
                payload = await response.json(content_type=None)
        # Accept common API response structures.
        if isinstance(payload, dict):
            data = payload.get("data", payload.get("items", []))
        elif isinstance(payload, list):
            data = payload
        else:
            data = []
        names = set()
        for entry in data:
            if isinstance(entry, str):
                name = entry.strip()
            elif isinstance(entry, dict):
                name = (
                    entry.get("name")
                    or entry.get("displayName")
                    or entry.get("display_name")
                    or ""
                )
                name = str(name).strip()
            else:
                continue
            if name:
                names.add(name)
        if names:
            item_names = sorted(names, key=str.casefold)
            item_cache_time = time.time()
            print(f"ITEM AUTOCOMPLETE: Loaded {len(item_names)} names")
        return item_names
    except Exception as error:
        print(f"ITEM AUTOCOMPLETE: Could not load item names: {error}")
        return item_names
async def fetch_price(item):
    slug = make_slug(item)
    item_url = f"{BASE_URL}/database/item/{slug}"
    cached = price_cache.get(slug)
    if cached and time.time() - cached["cached_at"] < CACHE_SECONDS:
        return (
            cached["price"],
            cached["url"],
            cached["timestamp"],
            cached["trade_count"],
        )
    api_url = (
        f"{API_BASE_URL}/trade/stats/"
        f"{slug}/prices?range=1d"
    )
    headers = {
        "User-Agent": "Mozilla/5.0 MetaScrappy/1.0",
        "Accept": "application/json",
    }
    async with aiohttp.ClientSession(
        timeout=REQUEST_TIMEOUT,
        headers=headers,
    ) as session:
        async with session.get(api_url) as response:
            if response.status != 200:
                print(
                    f"PRICE LOOKUP: HTTP {response.status} for {slug}"
                )
                return None, item_url, None, None
            payload = await response.json(content_type=None)
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list) or not data:
        print(f"PRICE LOOKUP: No history data for {slug}")
        return None, item_url, None, None
    valid_points = [
        point
        for point in data
        if isinstance(point, dict)
        and isinstance(point.get("time"), (int, float))
        and isinstance(point.get("median_price"), (int, float))
        and point["median_price"] > 0
    ]
    if not valid_points:
        print(f"PRICE LOOKUP: No valid median points for {slug}")
        return None, item_url, None, None
    latest = max(valid_points, key=lambda point: point["time"])
    price = int(latest["median_price"])
    timestamp = int(latest["time"])
    trade_count = latest.get("trade_count")
    price_cache[slug] = {
        "price": price,
        "url": item_url,
        "timestamp": timestamp,
        "trade_count": trade_count,
        "cached_at": time.time(),
    }
    return price, item_url, timestamp, trade_count
@tree.command(
    name="price",
    description="Look up an ARC Raiders item's price history",
)
@app_commands.describe(item="Start typing an item name")
async def price(interaction: discord.Interaction, item: str):
    await interaction.response.defer(thinking=True)
    try:
        value, item_url, timestamp, trade_count = await fetch_price(item)
        if value is None:
            await interaction.followup.send(
                f"I couldn't find recent price-history data for "
                f"**{item}**.\n"
                f"Check MetaForge: {item_url}\n"
                f"I won't guess the price."
            )
            return
        message = (
            f"**{item} — {value:,} Assorted Seeds**\n"
            f"Latest recorded median in the 1-day price history. "
            f"This may differ from the value displayed on the item page.\n"
            f"Data point: <t:{int(timestamp / 1000)}:R>\n"
            f"Source: [MetaForge]({item_url})"
        )
        if isinstance(trade_count, (int, float)):
            message += (
                f"\nTrades recorded for this data point: "
                f"{int(trade_count)}"
            )
        await interaction.followup.send(message)
    except (aiohttp.ClientError, TimeoutError) as error:
        print(f"PRICE LOOKUP: Network error for {item}: {error}")
        await interaction.followup.send(
            "MetaForge's price-history endpoint didn't respond. "
            "Please try again shortly."
        )
    except Exception as error:
        print(f"PRICE LOOKUP: Unexpected error for {item}: {error}")
        await interaction.followup.send(
            "The price lookup encountered an unexpected error. "
            "Please try again later."
        )
@price.autocomplete("item")
async def item_autocomplete(
    interaction: discord.Interaction,
    current: str,
):
    names = await load_item_names()
    if not names:
        return []
    query = current.strip().casefold()
    if not query:
        matches = names[:25]
    else:
        # Prioritize names that start with what the user typed.
        starts_with = [
            name for name in names
            if name.casefold().startswith(query)
        ]
        # Then include names containing the typed text.
        contains = [
            name for name in names
            if query in name.casefold()
            and not name.casefold().startswith(query)
        ]
        matches = (starts_with + contains)[:25]
    return [
        app_commands.Choice(name=name[:100], value=name[:100])
        for name in matches
    ]
@client.event
async def on_ready():
    await tree.sync()
    print(f"MetaScrappy is online as {client.user}")
if not TOKEN:
    raise RuntimeError(
        "DISCORD_TOKEN is missing from the environment variables."
    )
client.run(TOKEN)
