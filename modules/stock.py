#!/usr/bin/env python3
import os
import requests
import asyncio
import logging
from datetime import datetime, timezone
import discord
from config import TORN_API_KEY, FACTION_ID, STOCK_CHANNEL_ID  # your Discord channel ID

CHECK_CATEGORIES = ["medical", "boosters", "drugs"]
MIN_PER_ITEM = int(os.getenv("MIN_PER_ITEM", "50"))

logger = logging.getLogger(__name__)

def fetch_inventory():
    """Fetch faction inventory from Torn API"""
    if not TORN_API_KEY:
        raise ValueError("Missing TORN_API_KEY environment variable.")

    selections = "armor,weapons,temporary,medical,drugs,boosters"
    url = f"https://api.torn.com/faction/?selections={selections}&key={TORN_API_KEY}"
    logger.debug(f"Fetching faction inventory: {url.replace(TORN_API_KEY,'REDACTED')}")

    r = requests.get(url, timeout=20)
    r.raise_for_status()
    data = r.json()

    if isinstance(data, dict) and "error" in data:
        raise RuntimeError(f"Torn API {data['error'].get('code')}: {data['error'].get('error')}")
    
    return data


def find_low_items(data, min_qty=MIN_PER_ITEM):
    """Return items below threshold"""
    low = {}
    for cat in CHECK_CATEGORIES:
        items_data = data.get(cat, [])
        items = list(items_data.values()) if isinstance(items_data, dict) else items_data
        low[cat] = [
            (item.get("name", "Unknown"), int(item.get("quantity", 0)))
            for item in items if int(item.get("quantity", 0)) < min_qty
        ]
    return low


def format_embed(low_items):
    """Create a Discord embed from low stock items"""
    embed = discord.Embed(
        title="⚠️ Faction Stock Low",
        color=0xFFA500,
        timestamp=datetime.now(timezone.utc)
    )
    
    for cat, items in low_items.items():
        if items:
            lines = "\n".join([f"- {name} ({qty})" for name, qty in items])
            embed.add_field(name=cat.title(), value=lines, inline=False)
    
    if not embed.fields:
        embed.description = "✅ All stock levels are sufficient."
    
    embed.set_footer(text="Torn Faction Stock Checker")
    return embed


async def check_stock(client):
    """Check stock and post into Discord channel"""
    try:
        data = fetch_inventory()
        low_items = find_low_items(data)
        embed = format_embed(low_items)

        channel = client.get_channel(STOCK_CHANNEL_ID)
        if not channel:
            logger.error(f"Stock channel not found: {STOCK_CHANNEL_ID}")
            return
        
        await channel.send(embed=embed)
        logger.info("✅ Stock check posted successfully")
    except Exception as e:
        logger.error(f"Error checking faction stock: {e}")


async def start_periodic_stock(client, interval_minutes=15):
    """Run stock check every N minutes"""
    await client.wait_until_ready()
    while not client.is_closed():
        await check_stock(client)
        await asyncio.sleep(interval_minutes * 60)
