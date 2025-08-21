import os
import json
import requests
import asyncio
from datetime import datetime, timezone
import discord
from config import TORN_API_KEY, CHAIN_CHANNEL_ID

CACHE_FILE = "last_chain.json"

# --- Cache functions ---
def read_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_cache(data):
    with open(CACHE_FILE, "w") as f:
        json.dump(data, f)

# --- Torn API ---
def get_chains():
    url = f"https://api.torn.com/v2/faction/chains?limit=100&sort=DESC&key={TORN_API_KEY}"
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        return r.json().get("chains", [])
    except requests.RequestException as e:
        print(f"❌ Error fetching chains: {e}")
        return []

# --- Embed builder ---
def build_chain_embed(chain_length, respect=None, start=None, end=None):
    embed = discord.Embed(
        title=f"🔥 Faction Chain: {chain_length} hits",
        color=0xFFA500,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="Chain Length", value=str(chain_length), inline=True)
    if respect is not None:
        embed.add_field(name="Respect Gained", value=str(respect), inline=True)
    if start:
        embed.add_field(name="Start Time", value=start, inline=False)
    if end:
        embed.add_field(name="End Time", value=end, inline=False)
    embed.set_footer(text="Torn Faction Tracker")
    return embed

# --- Background monitor ---
async def start(client):
    await client.wait_until_ready()
    channel = client.get_channel(CHAIN_CHANNEL_ID)
    if not channel:
        print(f"❌ Channel {CHAIN_CHANNEL_ID} not found")
        return

    print("🔍 Starting chain monitor...")
    while True:
        try:
            print("🔄 Checking for new chains...")
            chains = get_chains()
            valid_chains = [c for c in chains if c.get("chain", 0) >= 25]
            if not valid_chains:
                print("⚠️ No chains >= 25 found")
                await asyncio.sleep(600)
                continue

            last_chain = valid_chains[0]
            chain_id = str(last_chain.get("id"))
            cache = read_cache()

            if cache.get("last_chain_id") == chain_id:
                print("⏭️ Last chain already posted, skipping.")
                await asyncio.sleep(600)
                continue

            # Build embed and post
            start_ts = datetime.fromtimestamp(last_chain.get("start", 0), timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            end_ts = datetime.fromtimestamp(last_chain.get("end", 0), timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            embed = build_chain_embed(
                chain_length=last_chain.get("chain", 0),
                respect=last_chain.get("respect", 0),
                start=start_ts,
                end=end_ts
            )
            await channel.send(embed=embed)
            print(f"✅ Posted new chain {chain_id} to channel")
            save_cache({"last_chain_id": chain_id})
        except Exception as e:
            print(f"❌ Error in chain monitor: {e}")
        await asyncio.sleep(600)  # check every 10 minutes

# --- Command for dummy/testing chains ---
async def chain_command(channel, number=None):
    if number:
        try:
            chain_length = int(number)
        except ValueError:
            chain_length = 100
        embed = build_chain_embed(chain_length)
        await channel.send(embed=embed)
        print(f"✅ Posted dummy chain: {chain_length}")
    else:
        # Check live chains once
        print("🔄 Checking Torn for new chains via command...")
        chains = get_chains()
        valid_chains = [c for c in chains if c.get("chain", 0) >= 25]
        if not valid_chains:
            await channel.send("⚠️ No chains found.")
            print("⚠️ No chains >= 25 found")
            return

        last_chain = valid_chains[0]
        start_ts = datetime.fromtimestamp(last_chain.get("start", 0), timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        end_ts = datetime.fromtimestamp(last_chain.get("end", 0), timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        embed = build_chain_embed(
            chain_length=last_chain.get("chain", 0),
            respect=last_chain.get("respect", 0),
            start=start_ts,
            end=end_ts
        )
        await channel.send(embed=embed)
        print(f"✅ Posted live chain via command: {last_chain.get('id')}")
