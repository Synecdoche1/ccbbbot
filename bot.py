#!/usr/bin/env python3
import os
import sys
import traceback
import discord
import asyncio
from flask import Flask
from threading import Thread

print("🚀 Starting bot...")

# -------------------------
# CONFIG FROM ENV
# -------------------------
TOKEN = os.getenv("DISCORD_TOKEN")
FACTION_ID = os.getenv("FACTION_ID")
ATTACK_CHANNEL_ID = os.getenv("ATTACK_CHANNEL_ID")
WAR_CHANNEL_ID = os.getenv("WAR_CHANNEL_ID")
LEADER_CHANNEL_ID = os.getenv("LEADER_CHANNEL_ID")

if not TOKEN:
    print("❌ DISCORD_TOKEN environment variable not set!")
    sys.exit(1)

print("✅ Config loaded from environment variables")

# -------------------------
# IMPORT MODULES
# -------------------------
modules_to_import = [
    "revive", "attack", "bounty", "inactivity", "war", "stock", "chain", "banking"
]

imported_modules = {}
for mod_name in modules_to_import:
    try:
        imported_modules[mod_name] = __import__(f"modules.{mod_name}", fromlist=[mod_name])
        print(f"✅ {mod_name.capitalize()} module imported successfully")
    except Exception as e:
        print(f"❌ Failed to import {mod_name} module: {e}")
        traceback.print_exc()
        imported_modules[mod_name] = None

# -------------------------
# DISCORD CLIENT SETUP
# -------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
client = discord.Client(intents=intents)
print("✅ Discord client created successfully")

# -------------------------
# COMMAND REGISTRY
# -------------------------
COMMANDS = {}

for name in ["revive","bounty","inactivity","war","chain","banking"]:
    mod = imported_modules.get(name)
    if mod:
        if name == "revive":
            COMMANDS.update({
                "revives": mod.revives,
                "/revives": mod.revives
            })
        elif name == "banking":
            COMMANDS.update({
                "bank": mod.bank,
                "/bank": mod.bank
            })

print(f"✅ Commands registered: {list(COMMANDS.keys())}")

# -------------------------
# ON_READY EVENT
# -------------------------
@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user} (ID: {client.user.id})")
    print(f"✅ Bot is in {len(client.guilds)} guilds")
    for guild in client.guilds:
        print(f"   - {guild.name} (ID: {guild.id})")

    # Setup banking events if available
    banking = imported_modules.get("banking")
    if banking and hasattr(banking, "setup_banking_events"):
        banking.setup_banking_events(client)
        print("✅ Banking events initialized")

# -------------------------
# ON_MESSAGE EVENT
# -------------------------
@client.event
async def on_message(message):
    if message.author.bot:
        return

    should_process = client.user in message.mentions or isinstance(message.channel, discord.DMChannel)
    if not should_process:
        return

    content_lower = message.content.lower().strip()
    # Remove mention
    mention_str = f"<@{client.user.id}>"
    mention_nick = f"<@!{client.user.id}>"
    content_lower = content_lower.replace(mention_str, "").replace(mention_nick, "").strip()

    print(f"📩 Received command: {content_lower} from {message.author}")

    # Process revives command
    if any(cmd in content_lower for cmd in ["revives", "/revives"]):
        revive_mod = imported_modules.get("revive")
        if revive_mod and hasattr(revive_mod, "revives"):
            print("⚡ Executing revives command")
            await revive_mod.revives(message.channel)
        else:
            await message.channel.send("❌ Revives module not available")
        return

    # Process banking command
    if "bank" in content_lower:
        banking_mod = imported_modules.get("banking")
        if banking_mod:
            if content_lower.strip() == "bank":
                await banking_mod.bank(message.channel)
            else:
                await banking_mod.handle_bank_command(message)
        return

# -------------------------
# FLASK KEEP-ALIVE FOR RENDER FREE TIER
# -------------------------
app = Flask("keep_alive")

@app.route("/")
def home():
    return "Discord bot is running!", 200

def run_server():
    port = int(os.getenv("PORT", 5000))
    print(f"🌐 Flask server starting on port {port} for Render keep-alive")
    app.run(host="0.0.0.0", port=port)

Thread(target=run_server, daemon=True).start()

# -------------------------
# START BOT
# -------------------------
try:
    client.run(TOKEN)
except discord.LoginFailure:
    print("❌ Invalid bot token!")
except KeyboardInterrupt:
    print("👋 Bot stopped by user")
except Exception as e:
    print(f"❌ Failed to start bot: {e}")
    traceback.print_exc()
