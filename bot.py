#!/usr/bin/env python3
import sys
import os
import traceback
import asyncio
import discord
from datetime import datetime
import modules.war as war_module

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
client = discord.Client(intents=intents)
print("✅ Discord client created successfully")

# -------------------------
# COMMAND REGISTRY
# -------------------------
COMMANDS = {}

# Banking commands
banking = imported_modules.get("banking")
if banking:
    COMMANDS.update({
        "bank": banking.bank,
        "/bank": banking.bank
    })

# War commands
COMMANDS.update({
    "war": lambda message: war_module.war_status(message.channel),
    "/war": lambda message: war_module.war_status(message.channel),
    "startwar": lambda message: war_module.start(client),
    "/startwar": lambda message: war_module.start(client)
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

    # Start war monitor automatically
    try:
        started = await war_module.start(client)
        if started:
            print("✅ War monitoring started automatically")
        else:
            print("⚠️ War monitoring did not start")
    except Exception as e:
        print(f"❌ Failed to start war monitoring: {e}")
        traceback.print_exc()

# -------------------------
# ON_MESSAGE EVENT
# -------------------------
@client.event
async def on_message(message):
    if message.author == client.user:
        return

    should_process = client.user in message.mentions or isinstance(message.channel, discord.DMChannel)
    if not should_process:
        return

    content_lower = message.content.lower().strip()
    # Remove mention
    if client.user in message.mentions:
        mention_str = f"<@{client.user.id}>"
        mention_str_nick = f"<@!{client.user.id}>"
        content_lower = content_lower.replace(mention_str, "").replace(mention_str_nick, "").strip()

    # Check commands
    for cmd, func in COMMANDS.items():
        if content_lower.startswith(cmd):
            try:
                print(f"⚡ Executing command: {cmd} from {message.author}")
                await func(message)
            except Exception as e:
                print(f"❌ Error executing {cmd}: {e}")
                traceback.print_exc()
            return

    # Banking inline commands
    if banking and 'bank' in content_lower:
        if content_lower.strip() == 'bank':
            await banking.bank(message.channel)
        else:
            await banking.handle_bank_command(message)

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
