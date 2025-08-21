#!/usr/bin/env python3
import os
import requests
import asyncio
import logging
from datetime import datetime, timezone
import discord
from config import TORN_API_KEY, STOCK_CHANNEL_ID  # make sure this is set

# Categories to check#!/usr/bin/env python3
import os
import requests
import asyncio
import logging
from datetime import datetime, timezone
import discord
from config import TORN_API_KEY, STOCK_CHANNEL_ID  # Discord channel ID

logger = logging.getLogger(__name__)

MIN_PER_ITEM = int(os.getenv("MIN_PER_ITEM", "50"))
FILTERED_DRUGS = ["Xanax"]  # Only show these drugs

stock_monitor_task: asyncio.Task = None

def fetch_inventory():
    if not TORN_API_KEY:
        raise ValueError("Missing TORN_API_KEY")
    selections = "armor,weapons,temporary,medical,drugs,boosters"
    url = f"https://api.torn.com/faction/?selections={selections}&key={TORN_API_KEY}"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError(f"Torn API {data['error'].get('code')}: {data['error'].get('error')}")
    return data

def find_low_items(data):
    """Return items below threshold, filtered"""
    CHECK_CATEGORIES = ["medical", "boosters", "drugs"]
    low = {}
    for cat in CHECK_CATEGORIES:
        items_data = data.get(cat, [])
        items = list(items_data.values()) if isinstance(items_data, dict) else items_data
        filtered_items = []
        for item in items:
            name = item.get("name", "Unknown")
            qty = int(item.get("quantity", 0))
            if qty < MIN_PER_ITEM:
                if cat == "drugs" and name not in FILTERED_DRUGS:
                    continue
                filtered_items.append((name, qty))
        low[cat] = filtered_items
    return low

def format_stock_embed(low_items):
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
    try:
        data = fetch_inventory()
        low_items = find_low_items(data)
        embed = format_stock_embed(low_items)
        channel = client.get_channel(STOCK_CHANNEL_ID)
        if channel:
            await channel.send(embed=embed)
        else:
            logger.error(f"Stock channel not found: {STOCK_CHANNEL_ID}")
    except Exception as e:
        logger.error(f"Error checking faction stock: {e}", exc_info=True)

async def stock_monitor_loop(client, interval_minutes=15):
    await client.wait_until_ready()
    while not client.is_closed():
        await check_stock(client)
        await asyncio.sleep(interval_minutes * 60)

async def start(client):
    global stock_monitor_task
    if not stock_monitor_task or stock_monitor_task.done():
        stock_monitor_task = asyncio.create_task(stock_monitor_loop(client))
        logger.info("Stock monitor started")
        return True
    return False

async def stop():
    global stock_monitor_task
    if stock_monitor_task:
        stock_monitor_task.cancel()
        try:
            await stock_monitor_task
        except asyncio.CancelledError:
            pass
        stock_monitor_task = None
        logger.info("Stock monitor stopped")

CHECK_CATEGORIES = ["medical", "boosters", "drugs"]
MIN_PER_ITEM = int(os.getenv("MIN_PER_ITEM", "50"))
FILTERED_DRUGS = ["Xanax"]  # Only show these drugs

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

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
    """Return items below threshold, filtered as needed"""
    low = {}
    for cat in CHECK_CATEGORIES:
        items_data = data.get(cat, [])
        items = list(items_data.values()) if isinstance(items_data, dict) else items_data

        filtered_items = []
        for item in items:
            name = item.get("name", "Unknown")
            qty = int(item.get("quantity", 0))
            if qty < min_qty:
                # If category is drugs, only include filtered drugs
                if cat == "drugs" and name not in FILTERED_DRUGS:
                    continue
                filtered_items.append((name, qty))

        low[cat] = filtered_items
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
