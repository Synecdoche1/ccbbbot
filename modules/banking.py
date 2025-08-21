# banking.py
import discord
import asyncio
import re
import aiohttp
from datetime import datetime
try:
    from config import FACTION_ID, TORN_API_KEY, BANKING_CHANNEL_ID
    print(f"✅ Banking config loaded - Faction ID: {FACTION_ID}, Banking Channel: {BANKING_CHANNEL_ID}")
except ImportError as e:
    print(f"❌ Failed to import config for banking: {e}")
    FACTION_ID = None
    TORN_API_KEY = None
    BANKING_CHANNEL_ID = None

# =====================
# Display balance cache (for looks only)
# =====================
display_balance_cache = {}  # {torn_user_id: display balance}

# =====================
# Helpers
# =====================
async def get_faction_balance(torn_user_id):
    if not TORN_API_KEY or not FACTION_ID:
        return None, None, "API key or faction ID not configured"
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://api.torn.com/v2/faction/balance?key={TORN_API_KEY}"
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None, None, f"API request failed with status {resp.status}"
                data = await resp.json()
                if "error" in data:
                    return None, None, f"API error: {data['error']['error']}"

                faction_balance = data.get('balance', {}).get('faction', {}).get('money', 0)
                user_balance = None
                for member in data.get('balance', {}).get('members', []):
                    if member.get('id') == torn_user_id:
                        user_balance = member.get('money', 0)
                        break
                if user_balance is None:
                    return faction_balance, None, f"User ID {torn_user_id} not found in faction"
                return faction_balance, user_balance, None
    except Exception as e:
        return None, None, f"Error fetching balance: {str(e)}"

def format_money(amount):
    if amount is None:
        return "Unknown"
    if amount >= 1_000_000_000:
        return f"${amount/1_000_000_000:.1f}B"
    elif amount >= 1_000_000:
        return f"${amount/1_000_000:.1f}M"
    elif amount >= 1_000:
        return f"${amount/1_000:.1f}K"
    else:
        return f"${amount:,}"

# =====================
# Bank command
# =====================
async def handle_bank_command(client, message):
    try:
        if message.author.bot:
            return

        content = message.content.lower().strip()
        if message.guild and message.guild.me:
            mention = f"<@{message.guild.me.id}>"
            mention_nick = f"<@!{message.guild.me.id}>"
            content = content.replace(mention, "").replace(mention_nick, "").strip()

        if not content.startswith("bank"):
            return

        # Torn ID from display name
        id_match = re.search(r'\[(\d+)\]', message.author.display_name)
        if not id_match:
            await message.channel.send(
                "❌ Could not find your Torn user ID in your display name. Format 'Username [TornID]'"
            )
            return
        torn_user_id = int(id_match.group(1))

        # Parse amount
        amount_match = re.search(r'(\d+(?:\.\d+)?)\s*([kmb]?)', content)
        if not amount_match:
            await message.channel.send("❌ Please specify an amount. Example: `bank 1m`")
            return
        amt_str, suffix = amount_match.groups()
        requested_amount = int(float(amt_str) * {'k':1000,'m':1_000_000,'b':1_000_000_000}.get(suffix.lower(),1))

        # Fetch real balance
        _, real_balance, error = await get_faction_balance(torn_user_id)
        if error:
            await message.channel.send(f"❌ Error checking faction balance: {error}")
            return

        # Use display balance cache, fallback to real balance
        current_display_balance = display_balance_cache.get(torn_user_id, real_balance)
        if current_display_balance < requested_amount:
            await message.channel.send("❌ You don't have enough funds for this request.")
            return

        # Deduct for display only
        display_balance_cache[torn_user_id] = current_display_balance - requested_amount

        # Build embed
        embed = discord.Embed(
            title="🏦 Bank Request",
            description=f"**Amount Requested:** {format_money(requested_amount)}",
            color=0x00FF00,
            timestamp=datetime.now()
        )
        embed.add_field(name="👤 Requested by", value=message.author.mention, inline=True)
        embed.add_field(name="💰 User Balance", value=format_money(current_display_balance), inline=True)
        embed.add_field(name="📊 Raw Amount", value=f"${requested_amount:,}", inline=True)
        embed.set_footer(text=f"Torn ID: {torn_user_id}", icon_url=message.author.avatar.url if message.author.avatar else None)

        # Send in channel
        await message.channel.send(embed=embed)

        # Send to banking channel
        await send_to_banking_channel(client, message, embed, requested_amount, torn_user_id)

    except Exception as e:
        await message.channel.send(f"❌ Error processing bank request: {str(e)}")
        print(f"Error in handle_bank_command: {e}")

# =====================
# Send to banking channel
# =====================
async def send_to_banking_channel(client, message, embed, requested_amount, requester_id):
    if not BANKING_CHANNEL_ID:
        print("⚠️ BANKING_CHANNEL_ID not configured")
        return
    try:
        guild = message.guild
        banking_channel = guild.get_channel(BANKING_CHANNEL_ID)
        if not banking_channel:
            print(f"❌ Banking channel ID {BANKING_CHANNEL_ID} not found")
            return

        notif_text = f"@everyone\n💰 **New Bank Request** from {message.channel.mention}"
        bank_msg = await banking_channel.send(notif_text, embed=embed)

        # Add reactions
        await bank_msg.add_reaction("👍")
        await bank_msg.add_reaction("🤚")

        # Reaction listener
        asyncio.create_task(bank_reaction_listener(client, bank_msg, embed, requested_amount, requester_id))

    except Exception as e:
        print(f"Error sending to banking channel: {e}")

# =====================
# Reaction listener
# =====================
async def bank_reaction_listener(client, bank_msg, embed, requested_amount, requester_id):
    def check(reaction, user):
        return reaction.message.id == bank_msg.id and not user.bot

    while True:
        reaction, user = await client.wait_for("reaction_add", check=check)

        # Actioned
        if str(reaction.emoji) == "👍":
            # Use display balance cache
            balance_str = format_money(display_balance_cache.get(requester_id, None))

            requested_by_field = next((f for f in embed.fields if f.name == "👤 Requested by"), None)
            requester = requested_by_field.value if requested_by_field else "Unknown"
            now_str = datetime.now().strftime("%d/%m/%Y %H:%M")

            log_msg = f"✅ {user.mention} sent {requester} {format_money(requested_amount)} at {now_str}. Their remaining balance is now {balance_str}."
            await bank_msg.channel.send(log_msg)
            await bank_msg.delete()
            print(f"Bank request actioned by {user}")
            break

        # Claimed
        elif str(reaction.emoji) == "🤚":
            await bank_msg.edit(content=f"🤚 Claimed by {user.mention}", embed=embed)
            print(f"Bank request claimed by {user}")

# =====================
# Optional: help command
# =====================
async def bank(channel):
    embed = discord.Embed(
        title="🏦 Bank Commands",
        description="Request money from the faction bank",
        color=0x00FF00
    )
    embed.add_field(
        name="📝 Usage",
        value="Mention the bot with `bank <amount>`\nExamples:\n• `@bot bank 1m`\n• `@bot bank 500k`\n• `@bot bank 1000`",
        inline=False
    )
    embed.add_field(
        name="💡 Supported Formats",
        value="• Numbers: `1000`, `50000`\n• Thousands: `500k`\n• Millions: `1m`, `2.5m`\n• Billions: `1b`, `1.2b`",
        inline=False
    )
    await channel.send(embed=embed)

# =====================
# Setup events for bot.py
# =====================
def setup_banking_events(client):
    @client.event
    async def on_message(message):
        await handle_bank_command(client, message)
