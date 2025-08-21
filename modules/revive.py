import requests
import discord
import json
import os
import traceback

# -------------------------
# CONFIG FROM ENVIRONMENT
# -------------------------
TORN_API_KEY = os.getenv("TORN_API_KEY", "YOUR_API_KEY_HERE")
FACTION_ID = os.getenv("FACTION_ID", "YOUR_FACTION_ID_HERE")

if TORN_API_KEY == "YOUR_API_KEY_HERE" or FACTION_ID == "YOUR_FACTION_ID_HERE":
    print("❌ Torn API key or Faction ID not set. Revives command will not work until configured.")

# -------------------------
# CACHE FUNCTIONS
# -------------------------
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

# -------------------------
# REVIVES COMMAND
# -------------------------
async def revives(channel):
    """Send revivable faction members as an embed"""
    print(f"🔍 Starting revives command for faction {FACTION_ID}")

    # Check for valid API key
    if TORN_API_KEY == "YOUR_API_KEY_HERE" or FACTION_ID == "YOUR_FACTION_ID_HERE":
        error_msg = "❌ Bot configuration error: Torn API key or Faction ID not set."
        print(error_msg)
        await channel.send(error_msg)
        return

    try:
        # Initial status message
        status_msg = await channel.send("🔍 Fetching faction members...")

        api_url = f"https://api.torn.com/v2/faction/members?selections=profile&key={TORN_API_KEY}"
        r = requests.get(api_url, timeout=20)
        r.raise_for_status()
        data = r.json()

        if "error" in data:
            await channel.send(f"❌ Torn API error: {data['error']}")
            return

        members_data = data.get("members", {})
        if not members_data:
            await channel.send("❌ No members data found.")
            return

        # Process members
        revivable_members = {"Everyone": [], "Friends & faction": []}
        total_revives = 0

        for member_id, member_info in members_data.items():
            if not member_info.get("is_revivable"):
                continue

            setting = member_info.get("revive_setting")
            if setting not in revivable_members:
                continue

            total_revives += 1
            name = member_info.get("name", f"ID:{member_id}")
            profile_link = f"https://www.torn.com/profiles.php?XID={member_id}"
            revivable_members[setting].append(f"[{name}]({profile_link})")

        await status_msg.delete()

        if total_revives == 0:
            embed = discord.Embed(
                title="⚡ Revivable Faction Members",
                description="🎉 No revivable members found! Everyone is healthy.",
                color=0x00FF00
            )
            await channel.send(embed=embed)
            print("✅ No revivable members - sent message")
            return

        # Build embed
        embed = discord.Embed(
            title="⚡ Revivable Faction Members",
            description=f"⚠️ **{total_revives} members have revives enabled!** ⚠️\n\n*📱 Please turn your revives OFF!!*",
            color=0xFF6B6B
        )

        for setting, members in revivable_members.items():
            if members:
                chunk_size = 20
                for i in range(0, len(members), chunk_size):
                    chunk = members[i:i+chunk_size]
                    field_name = f"🔴 {setting}" if i == 0 else f"🔴 {setting} (cont.)"
                    embed.add_field(name=field_name, value="\n".join(chunk), inline=False)

        embed.set_footer(text="Paca's favourite • Last updated")
        embed.timestamp = discord.utils.utcnow()
        await channel.send(embed=embed)
        print(f"✅ Sent revives embed with {total_revives} members")

    except Exception as e:
        error_msg = f"❌ Unexpected error in revives command: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        try:
            await channel.send(error_msg)
        except:
            pass
