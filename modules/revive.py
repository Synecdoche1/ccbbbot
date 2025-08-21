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
    print("❌ Torn API key or Faction ID not set. Revives command will not work until configured.

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

async def revives(channel):
    """Send revivable faction members as an embed"""
    print(f"🔍 Starting revives command for faction {FACTION_ID}")
    
    # Check if we have valid config
    if TORN_API_KEY == "YOUR_API_KEY_HERE" or FACTION_ID == "YOUR_FACTION_ID_HERE":
        error_msg = "❌ Bot configuration error: Please check your config.py file and make sure TORN_API_KEY and FACTION_ID are set correctly."
        print(error_msg)
        await channel.send(error_msg)
        return
    
    try:
        # Send initial status message
        status_msg = await channel.send("🔍 Fetching faction members...")
        
        # Use the correct API v2 endpoint that works in your GitHub script
        api_urls = [
            f"https://api.torn.com/v2/faction/members?selections=profile&key={TORN_API_KEY}",
            f"https://api.torn.com/user/?selections=profile&key={TORN_API_KEY}"  # Fallback to test API key
        ]
        
        members_data = None
        used_url = None
        
        for i, api_url in enumerate(api_urls):
            try:
                print(f"🔍 Trying API endpoint {i+1}/{len(api_urls)}: {api_url[:50]}...")
                
                # Update status for user
                await status_msg.edit(content=f"🔍 Trying API endpoint {i+1}/{len(api_urls)}...")
                
                r = requests.get(api_url, timeout=20)
                print(f"📡 HTTP Status: {r.status_code}")
                
                r.raise_for_status()
                data = r.json()
                
                print(f"📋 Response keys: {list(data.keys())}")
                
                # Check for API errors
                if "error" in data:
                    error_info = data["error"]
                    print(f"❌ API Error: {error_info}")
                    
                    if i == len(api_urls) - 1:  # Last attempt
                        await channel.send(f"❌ Torn API Error: {error_info}")
                        return
                    continue
                
                # Handle different response formats
                if "members" in data:
                    members_data = data["members"]
                    used_url = api_url
                    print(f"✅ Got {len(members_data)} members from endpoint {i+1}")
                    break
                elif i == len(api_urls) - 1:  # Last URL was just to test API key
                    if "player_id" in data:
                        print("✅ API key works, but couldn't fetch faction data")
                        await channel.send("❌ API key is valid, but couldn't fetch faction member data. Check your faction ID or permissions.")
                        return
                else:
                    print(f"❌ No 'members' key in response: {list(data.keys())}")
                    continue
                    
            except requests.exceptions.Timeout:
                print(f"⏰ Timeout for endpoint {i+1}")
                if i == len(api_urls) - 1:
                    await channel.send("❌ Request timed out. Torn API might be slow.")
                    return
                continue
            except requests.exceptions.HTTPError as e:
                print(f"🌐 HTTP Error for endpoint {i+1}: {e}")
                if r.status_code == 403:
                    await channel.send("❌ Access denied. Check your API key permissions.")
                    return
                elif r.status_code == 429:
                    await channel.send("❌ Rate limited by Torn API. Please try again later.")
                    return
                continue
            except requests.RequestException as e:
                print(f"❌ Request error for endpoint {i+1}: {e}")
                if i == len(api_urls) - 1:
                    await channel.send(f"❌ Network error: {e}")
                    return
                continue
            except json.JSONDecodeError as e:
                print(f"❌ JSON decode error for endpoint {i+1}: {e}")
                continue
            except Exception as e:
                print(f"❌ Unexpected error for endpoint {i+1}: {e}")
                traceback.print_exc()
                continue
        
        if not members_data:
            await channel.send("❌ Could not fetch faction members from any API endpoint.")
            return
        
        # Update status
        await status_msg.edit(content="📊 Processing member data...")
        
        # Process members - API v2 returns a list directly
        if isinstance(members_data, list):
            members = members_data
        elif isinstance(members_data, dict):
            # Convert dict to list of member objects (fallback for other API formats)
            members = []
            for member_id, member_info in members_data.items():
                if isinstance(member_info, dict):
                    member_info["id"] = member_id  # Make sure ID is included
                    members.append(member_info)
        else:
            members = []
        
        print(f"📊 Processing {len(members)} members")
        
        # Group revivable members by setting (matching your working script)
        groups = {"Everyone": [], "Friends & faction": []}
        revivable_count = 0
        
        for member in members:
            try:
                # Use the same logic as your working GitHub script
                if not member.get("is_revivable"):
                    continue
                
                revivable_count += 1
                
                # Get revive setting exactly like your working script
                setting = member.get("revive_setting")
                
                # Skip if setting not in our groups (like your working script)
                if setting not in groups:
                    continue
                
                member_id = member.get("id")
                member_name = member.get("name", f"ID:{member_id}")
                
                profile_link = f"https://www.torn.com/profiles.php?XID={member_id}"
                groups[setting].append(f"[{member_name}]({profile_link})")
                
                print(f"✅ Found revivable member: {member_name} (ID: {member_id}, setting: {setting})")
                
            except Exception as e:
                print(f"❌ Error processing member {member}: {e}")
                continue
        
        print(f"📊 Found {revivable_count} total revivable members")
        
        # Delete the status message
        try:
            await status_msg.delete()
        except:
            pass
        
        # Build embed fields
        embed_fields = []
        total_members = 0
        
        for setting, member_list in groups.items():
            if member_list:
                # Split long lists to avoid Discord embed limits
                member_chunks = []
                current_chunk = []
                current_length = 0
                
                for member in member_list:
                    if current_length + len(member) + 2 > 1000:  # Discord field value limit
                        if current_chunk:
                            member_chunks.append(current_chunk)
                        current_chunk = [member]
                        current_length = len(member)
                    else:
                        current_chunk.append(member)
                        current_length += len(member) + 2  # +2 for newline
                
                if current_chunk:
                    member_chunks.append(current_chunk)
                
                # Create fields for each chunk
                for i, chunk in enumerate(member_chunks):
                    field_name = f"🔴 {setting}" if i == 0 else f"🔴 {setting} (cont.)"
                    value = "\n".join(chunk)
                    embed_fields.append({"name": field_name, "value": value, "inline": False})
                    total_members += len(chunk)
        
        if not embed_fields:
            embed = discord.Embed(
                title="⚡ Revivable Faction Members",
                description="🎉 No revivable members found! Everyone is healthy.",
                color=0x00FF00
            )
            embed.add_field(
                name="ℹ️ Note", 
                value="This could mean everyone is healthy, or there might be an issue with the API data.", 
                inline=False
            )
            await channel.send(embed=embed)
            print("✅ No revivable members - sent success message")
            return
        
        # Create and send embed
        embed = discord.Embed(
            title="⚡ Revivable Faction Members",
            color=0xFF6B6B,  # Red color for urgency
            description=f"⚠️ **{total_members} members have revives enabled!** ⚠️\n\n*📱 Please turn your revives OFF!!*"
        )
        
        for field in embed_fields:
            embed.add_field(name=field["name"], value=field["value"], inline=field["inline"])
        
        embed.set_footer(text=f"Paca's favourite • Last updated")
        embed.timestamp = discord.utils.utcnow()
        
        await channel.send(embed=embed)
        print(f"✅ Sent revives embed with {total_members} members")
        
    except Exception as e:
        error_msg = f"❌ Unexpected error in revives command: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        try:
            await channel.send(error_msg)
        except:
            print("❌ Could not send error message to channel")
