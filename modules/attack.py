import requests
import json
import os
import asyncio
from datetime import datetime, timezone
from config import TORN_API_KEY, FACTION_ID, ATTACK_CHANNEL_ID
import discord

CACHE_FILE = "last_attack.json"
PLAYER_CACHE_FILE = "player_cache.json"

def read_cache(file):
    if os.path.exists(file):
        try:
            with open(file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}
    return {}

def save_cache(data, file):
    try:
        with open(file, "w") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"❌ Error saving cache: {e}")

def timestamp_to_str(ts):
    try:
        return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except (ValueError, OSError):
        return "Unknown time"

def player_link(pid):
    return f"https://www.torn.com/profiles.php?XID={pid}"

def faction_link(fid):
    return f"https://www.torn.com/factions.php?step=profile&ID={fid}"

def get_player_name(pid, cache):
    """Get player name from cache or API, exactly like the GitHub script"""
    if str(pid) in cache:
        return cache[str(pid)]
    
    try:
        url = f"https://api.torn.com/v2/user/{pid}?selections=basic&key={TORN_API_KEY}"
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        data = r.json()
        
        # Check for API errors
        if "error" in data:
            print(f"❌ API Error getting player {pid}: {data['error']}")
            name = "Unknown"
        else:
            name = data.get("name", "Unknown")
            
    except requests.RequestException as e:
        print(f"❌ Request error getting player {pid}: {e}")
        name = "Unknown"
    
    cache[str(pid)] = name
    save_cache(cache, PLAYER_CACHE_FILE)
    return name

def get_last_attack():
    """Get the latest attack, exactly like the GitHub script"""
    url = f"https://api.torn.com/v2/faction/attacksfull?limit=1&sort=DESC&key={TORN_API_KEY}"
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        data = r.json()
        
        # Check for API errors
        if "error" in data:
            print(f"❌ API Error: {data['error']}")
            return None
            
        attacks = data.get("attacks", [])
        return attacks[0] if attacks else None
        
    except requests.RequestException as e:
        print(f"❌ Error fetching attacks: {e}")
        return None

async def start(client):
    """Continuously check for new attacks"""
    print("🔍 Starting attack monitoring...")
    await client.wait_until_ready()
    
    channel = client.get_channel(ATTACK_CHANNEL_ID)
    if not channel:
        print(f"❌ Attack channel not found with ID: {ATTACK_CHANNEL_ID}")
        return
    
    print(f"✅ Attack monitoring started in #{channel.name}")

    while not client.is_closed():
        try:
            player_cache = read_cache(PLAYER_CACHE_FILE)
            last_attack_cache = read_cache(CACHE_FILE)
            
            last_attack = get_last_attack()
            if not last_attack:
                print("⚠️ No attacks found.")
                await asyncio.sleep(60)
                continue

            # Validate attacker and defender info
            attacker_info = last_attack.get("attacker")
            defender_info = last_attack.get("defender")
            if not attacker_info or not defender_info:
                print("⚠️ Attack data missing attacker or defender.")
                await asyncio.sleep(60)
                continue

            attack_id = str(last_attack.get("id", "unknown"))
            if last_attack_cache.get("last_attack_id") == attack_id:
                print("📝 Last attack already posted, skipping.")
                await asyncio.sleep(60)
                continue

            # Safely get IDs
            attacker_id = attacker_info.get("id")
            attacker_faction_id = attacker_info.get("faction_id", 0)
            defender_id = defender_info.get("id")
            defender_faction_id = defender_info.get("faction_id", 0)
            
            # Get names using cache or API
            attacker_name = get_player_name(attacker_id, player_cache) if attacker_id else "Unknown"
            defender_name = get_player_name(defender_id, player_cache) if defender_id else "Unknown"

            # Get other info safely
            result = last_attack.get("result", "Unknown")
            attacker_respect = last_attack.get("respect_gain", 0)
            defender_respect = last_attack.get("respect_loss", 0)
            started = timestamp_to_str(last_attack.get("started", 0))
            ended = timestamp_to_str(last_attack.get("ended", 0))

            # Create embed
            embed_color = 0xFF0000 if "Left" in result or "Hospitalised" in result else 0x00FF00
            embed = discord.Embed(
                title=f"⚔️ Faction Attack Result: {result}",
                color=embed_color,
                timestamp=datetime.now(timezone.utc)
            )

            embed.add_field(
                name="Attacker",
                value=f"[{attacker_name}]({player_link(attacker_id)}) | [Faction]({faction_link(attacker_faction_id)})\nRespect Gained: {attacker_respect}",
                inline=True
            )
            embed.add_field(
                name="Defender",
                value=f"[{defender_name}]({player_link(defender_id)}) | [Faction]({faction_link(defender_faction_id)})\nRespect Lost: {defender_respect}",
                inline=True
            )
            embed.add_field(name="Started", value=started, inline=False)
            embed.add_field(name="Ended", value=ended, inline=False)
            embed.add_field(name="Outcome", value=result, inline=False)
            embed.set_footer(text="Torn Faction Tracker")
            
            await channel.send(embed=embed)
            print(f"✅ Posted attack {attack_id}: {attacker_name} vs {defender_name}")

            # Update cache
            save_cache({"last_attack_id": attack_id}, CACHE_FILE)

        except Exception as e:
            print(f"❌ Error in attack monitoring: {e}")
            import traceback
            traceback.print_exc()
        
        await asyncio.sleep(60)
async def start(client):
    """Continuously check for new attacks"""
    print("🔍 Starting attack monitoring...")
    await client.wait_until_ready()
    
    channel = client.get_channel(ATTACK_CHANNEL_ID)
    if not channel:
        print(f"❌ Attack channel not found with ID: {ATTACK_CHANNEL_ID}")
        return
    
    print(f"✅ Attack monitoring started in #{channel.name}")

    while not client.is_closed():
        try:
            player_cache = read_cache(PLAYER_CACHE_FILE)
            last_attack_cache = read_cache(CACHE_FILE)
            
            last_attack = get_last_attack()
            if not last_attack:
                print("⚠️ No attacks found.")
                await asyncio.sleep(60)
                continue

            # Validate attacker and defender info
            attacker_info = last_attack.get("attacker")
            defender_info = last_attack.get("defender")
            if not attacker_info or not defender_info:
                print("⚠️ Attack data missing attacker or defender.")
                await asyncio.sleep(60)
                continue

            attack_id = str(last_attack.get("id", "unknown"))
            if last_attack_cache.get("last_attack_id") == attack_id:
                print("📝 Last attack already posted, skipping.")
                await asyncio.sleep(60)
                continue

            # Safely get IDs
            attacker_id = attacker_info.get("id")
            attacker_faction_id = attacker_info.get("faction_id", 0)
            defender_id = defender_info.get("id")
            defender_faction_id = defender_info.get("faction_id", 0)
            
            # Get names using cache or API
            attacker_name = get_player_name(attacker_id, player_cache) if attacker_id else "Unknown"
            defender_name = get_player_name(defender_id, player_cache) if defender_id else "Unknown"

            # Get other info safely
            result = last_attack.get("result", "Unknown")
            attacker_respect = last_attack.get("respect_gain", 0)
            defender_respect = last_attack.get("respect_loss", 0)
            started = timestamp_to_str(last_attack.get("started", 0))
            ended = timestamp_to_str(last_attack.get("ended", 0))

            # Create embed
            embed_color = 0xFF0000 if "Left" in result or "Hospitalised" in result else 0x00FF00
            embed = discord.Embed(
                title=f"⚔️ Faction Attack Result: {result}",
                color=embed_color,
                timestamp=datetime.now(timezone.utc)
            )

            embed.add_field(
                name="Attacker",
                value=f"[{attacker_name}]({player_link(attacker_id)}) | [Faction]({faction_link(attacker_faction_id)})\nRespect Gained: {attacker_respect}",
                inline=True
            )
            embed.add_field(
                name="Defender",
                value=f"[{defender_name}]({player_link(defender_id)}) | [Faction]({faction_link(defender_faction_id)})\nRespect Lost: {defender_respect}",
                inline=True
            )
            embed.add_field(name="Started", value=started, inline=False)
            embed.add_field(name="Ended", value=ended, inline=False)
            embed.add_field(name="Outcome", value=result, inline=False)
            embed.set_footer(text="Torn Faction Tracker")
            
            await channel.send(embed=embed)
            print(f"✅ Posted attack {attack_id}: {attacker_name} vs {defender_name}")

            # Update cache
            save_cache({"last_attack_id": attack_id}, CACHE_FILE)

        except Exception as e:
            print(f"❌ Error in attack monitoring: {e}")
            import traceback
            traceback.print_exc()
        
        await asyncio.sleep(60)
