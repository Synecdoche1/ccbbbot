import os
import json
import traceback
import requests
import discord
from flask import Flask

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

    # Check config
    if TORN_API_KEY == "YOUR_API_KEY_HERE" or FACTION_ID == "YOUR_FACTION_ID_HERE":
        error_msg = "❌ Bot configuration error: Torn API key or Faction ID not set."
        print(error_msg)
        await channel.send(error_msg)
        return

    try:
        status_msg = await channel.send("🔍 Fetching faction members...")
        api_url = f"https://api.torn.com/v2/faction/members?selections=profile&key={TORN_API_KEY}"

        r = requests.get(api_url, timeout=20)
        r.raise_for_status()
        data = r.json()
        print(f"📡 Fetched data from Torn API: keys={list(data.keys())}")

        if "error" in data:
            await channel.send(f"❌ Torn API error: {data['error']}")
            return

        members_data = data.get("members", {})
        members_list = []

        # Handle both dict and list formats
        if isinstance(members_data, dict):
            for member_id, member_info in members_data.items():
                member_info["id"] = member_id
                members_list.append(member_info)
        elif isinstance(members_data, list):
            members_list = members_data
        else:
            print("❌ Unexpected members_data format")
            await channel.send("❌ Could not parse members data from Torn API.")
            return

        print(f"📊 Processing {len(members_list)} members")
        revivable_members = {"Everyone": [], "Friends & faction": []}
        total_revives = 0

        for member in members_list:
            try:
                if not member.get("is_revivable"):
                    continue
                setting = member.get("revive_setting")
                if setting not in revivable_members:
                    continue

                total_revives += 1
                member_name = member.get("name", f"ID:{member.get('id')}")
                profile_link = f"https://www.torn.com/profiles.php?XID={member.get('id')}"
                revivable_members[setting].append(f"[{member_name}]({profile_link})")
                print(f"✅ Found revivable: {member_name} ({setting})")
            except Exception as e:
                print(f"❌ Error processing member: {e}")
                continue

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
        print(f"❌ Unexpected error in revives command: {e}")
        traceback.print_exc()
        try:
            await channel.send(f"❌ Unexpected error: {e}")
        except:
            pass

# -------------------------
# FLASK KEEP-ALIVE FOR RENDER FREE TIER
# -------------------------
app = Flask("keep_alive")

@app.route("/")
def home():
    return "Revive module is running!", 200

def run_server():
    import threading
    port = int(os.getenv("PORT", 5000))
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=port)).start()
    print(f"🌐 Flask server started on port {port} for Render keep-alive")

# Start the Flask server immediately when module is loaded
run_server()
