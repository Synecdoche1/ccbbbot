import requests
import discord
import traceback
from datetime import datetime, timezone

# Import config
try:
    from config import TORN_API_KEY, FACTION_ID
    print(f"✅ Config loaded for inactivity - Faction ID: {FACTION_ID}")
except ImportError as e:
    print(f"❌ Failed to import config: {e}")
    raise SystemExit("❌ Config file not found or missing TORN_API_KEY/FACTION_ID")

# --- FUNCTIONS ---
def get_faction_members():
    """Get all faction members with their activity data"""
    url = f"https://api.torn.com/v2/faction/members?selections=profile&key={TORN_API_KEY}"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    data = r.json()
    return data.get("members", [])

def calculate_inactive_days(last_action_data):
    """Calculate days since last action"""
    if not last_action_data:
        return 0
    
    # Handle if last_action is a dict with timestamp
    if isinstance(last_action_data, dict):
        timestamp = last_action_data.get('timestamp', 0)
    else:
        timestamp = last_action_data
    
    if not timestamp:
        return 0
    
    last_action = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    current_time = datetime.now(timezone.utc)
    time_diff = current_time - last_action
    return time_diff.days

async def inactivity(channel):
    """Check for inactive faction members and send as embed"""
    print(f"📅 Starting inactivity check for faction {FACTION_ID}")
    
    try:
        # Send initial status message
        status_msg = await channel.send("🔍 Checking faction member activity...")
        
        # Get faction members
        try:
            members = get_faction_members()
            await status_msg.edit(content=f"📊 Analyzing activity for {len(members)} faction members...")
            print(f"Found {len(members)} faction members")
        except Exception as e:
            error_msg = f"❌ Failed to get faction members: {str(e)}"
            print(error_msg)
            await channel.send(error_msg)
            return
        
        # Group members by inactivity days
        inactive_groups = {1: [], 2: [], 3: [], "4+": []}
        
        for i, member in enumerate(members):
            # Update status every 20 members
            if i % 20 == 0 and i > 0:
                await status_msg.edit(content=f"📊 Analyzing activity... ({i}/{len(members)})")
            
            # Get last action data - could be dict or timestamp
            last_action = member.get("last_action", 0)
            
            # Debug: Print first member's last_action structure
            if member == members[0]:
                print(f"Debug - last_action structure: {last_action}")
            
            inactive_days = calculate_inactive_days(last_action)
            
            # Track 1, 2, 3 days, and 4+ days inactive
            if inactive_days == 1:
                group_key = 1
            elif inactive_days == 2:
                group_key = 2
            elif inactive_days == 3:
                group_key = 3
            elif inactive_days > 3:
                group_key = "4+"
            else:
                continue  # Skip if 0 days inactive
            
            inactive_groups[group_key].append({
                'id': member['id'],
                'name': member['name'],
                'level': member['level'],
                'inactive_days': inactive_days
            })
            print(f"📅 {member['name']} - {inactive_days} day{'s' if inactive_days != 1 else ''} inactive")
        
        # Delete status message
        try:
            await status_msg.delete()
        except:
            pass
        
        # Check if there are any inactive members
        total_inactive = sum(len(members) for members in inactive_groups.values())
        
        if total_inactive == 0:
            # No inactive members found
            embed = discord.Embed(
                title="✅ Activity Check Complete",
                description="🎉 No inactive members found! Everyone is active.",
                color=0x00FF00
            )
            embed.add_field(
                name="ℹ️ Info", 
                value=f"Checked {len(members)} faction members for inactivity (1+ days).", 
                inline=False
            )
            embed.set_footer(text=f"Faction {FACTION_ID} • Activity Monitor")
            embed.timestamp = discord.utils.utcnow()
            
            await channel.send(embed=embed)
            print("✅ No inactive members - sent status message")
            return
        
        # Build embed fields for inactive members
        fields = []
        # Process in order: 1, 2, 3, 4+ days
        for days in [1, 2, 3, "4+"]:
            inactive_members = inactive_groups[days]
            if inactive_members:
                member_list = []
                for member in inactive_members:
                    profile_url = f"https://www.torn.com/profiles.php?XID={member['id']}"
                    # Show actual days for 4+ group
                    if days == "4+":
                        member_list.append(f"• [{member['name']}]({profile_url}) (Lvl {member['level']}) - {member['inactive_days']} days")
                    else:
                        member_list.append(f"• [{member['name']}]({profile_url}) (Lvl {member['level']})")
                
                # Split long lists to avoid Discord embed limits
                member_chunks = []
                current_chunk = []
                current_length = 0
                
                for member_line in member_list:
                    if current_length + len(member_line) + 2 > 1000:  # Discord field value limit
                        if current_chunk:
                            member_chunks.append(current_chunk)
                        current_chunk = [member_line]
                        current_length = len(member_line)
                    else:
                        current_chunk.append(member_line)
                        current_length += len(member_line) + 2  # +2 for newline
                
                if current_chunk:
                    member_chunks.append(current_chunk)
                
                # Create fields for each chunk
                for i, chunk in enumerate(member_chunks):
                    if days == "4+":
                        field_name = f"🔴 4+ Days Inactive ({len(inactive_members)} member{'s' if len(inactive_members) != 1 else ''})"
                    else:
                        field_name = f"📅 {days} Day{'s' if days != 1 else ''} Inactive ({len(inactive_members)} member{'s' if len(inactive_members) != 1 else ''})"
                    
                    if i > 0:
                        field_name += f" (cont.)"
                    
                    field_value = "\n".join(chunk)
                    fields.append({
                        "name": field_name,
                        "value": field_value,
                        "inline": False
                    })
        
        # Create and send embed
        embed = discord.Embed(
            title="⚠️ Inactive Faction Members Alert",
            description=f"Found **{total_inactive}** inactive member{'s' if total_inactive != 1 else ''}",
            color=0xFF6B35  # Orange color for warning
        )
        
        for field in fields:
            embed.add_field(name=field["name"], value=field["value"], inline=field["inline"])
        
        # Add summary field
        summary_lines = []
        for days in [1, 2, 3, "4+"]:
            count = len(inactive_groups[days])
            if count > 0:
                if days == "4+":
                    summary_lines.append(f"• {count} member{'s' if count != 1 else ''} inactive for 4+ days")
                else:
                    summary_lines.append(f"• {count} member{'s' if count != 1 else ''} inactive for {days} day{'s' if days != 1 else ''}")
        
        if summary_lines:
            embed.add_field(
                name="📊 Summary",
                value="\n".join(summary_lines),
                inline=False
            )
        
        embed.set_footer(text=f"Faction {FACTION_ID} • Activity Monitor")
        embed.timestamp = discord.utils.utcnow()
        
        # Send with @everyone mention (if bot has permissions)
        content = "@everyone" if total_inactive > 0 else None
        
        await channel.send(content=content, embed=embed)
        print(f"✅ Sent inactivity alert for {total_inactive} members")
        
    except Exception as e:
        error_msg = f"❌ Unexpected error in inactivity command: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        try:
            await channel.send(error_msg)
        except:
            print("❌ Could not send error message to channel")