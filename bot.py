#!/usr/bin/env python3
import os
import sys
import traceback
import discord
from datetime import datetime

print("🚀 Starting bot...")

# -------------------------
# LOAD CONFIG FROM ENV
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
# CREATE DISCORD CLIENT
# -------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
client = discord.Client(intents=intents)
print("✅ Discord client created successfully")

# -------------------------
# REGISTER COMMANDS
# -------------------------
COMMANDS = {}

for name, mod in imported_modules.items():
    if not mod:
        continue

    # Banking commands
    if hasattr(mod, "bank"):
        COMMANDS.update({
            "bank": getattr(mod, "bank"),
            "/bank": getattr(mod, "bank")
        })
    # Revives command
    if hasattr(mod, "revives"):
        COMMANDS.update({
            "revives": getattr(mod, "revives"),
            "/revives": getattr(mod, "revives")
        })
    # Bounty command
    if hasattr(mod, "bounty"):
        COMMANDS.update({
            "bounty": getattr(mod, "bounty"),
            "/bounty": getattr(mod, "bounty")
        })
    # Add other module commands here similarly

print(f"✅ Commands registered: {list(COMMANDS.keys())}")

# -------------------------
# SETUP EVENTS FROM MODULES (banking, etc.)
# -------------------------
banking_mod = imported_modules.get("banking")
if banking_mod and hasattr(banking_mod, "setup_banking_events"):
    banking_mod.setup_banking_events(client)

# -------------------------
# ON_READY EVENT
# -------------------------
@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user} (ID: {client.user.id})")
    print(f"✅ Bot is in {len(client.guilds)} guilds")
    for guild in client.guilds:
        print(f"   - {guild.name} (ID: {guild.id})")

# -------------------------
# ON_MESSAGE EVENT
# -------------------------
@client.event
async def on_message(message):
    if message.author == client.user:
        return

    # Only respond to mentions or DMs
    should_process = client.user in message.mentions or isinstance(message.channel, discord.DMChannel)
    if not should_process:
        return

    content_lower = message.content.lower().strip()
    # Remove bot mention
    if client.user in message.mentions:
        mention_str = f"<@{client.user.id}>"
        mention_str_nick = f"<@!{client.user.id}>"
        content_lower = content_lower.replace(mention_str, "").replace(mention_str_nick, "").strip()

    # Find command in COMMANDS
    for cmd_name, cmd_func in COMMANDS.items():
        if content_lower.startswith(cmd_name):
            # Banking is special because it needs the message object
            if cmd_name in ["bank", "/bank"] and "banking" in imported_modules:
                await imported_modules["banking"].handle_bank_command(message)
            else:
                await cmd_func(message.channel)
            return

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
