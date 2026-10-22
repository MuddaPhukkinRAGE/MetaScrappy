
import os
import discord
from discord import app_commands

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


@tree.command(
    name="price",
    description="Look up an ARC Raiders item price"
)
@app_commands.describe(item="The ARC Raiders item name")
async def price(interaction: discord.Interaction, item: str):
    await interaction.response.send_message(
        f"Price lookup for **{item}** is not connected yet. "
        "We're waiting for MetaForge to confirm the official price API."
    )


@client.event
async def on_ready():
    await tree.sync()
    print(f"MetaScrappy is online as {client.user}")


if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN environment variable is missing")

client.run(TOKEN)

