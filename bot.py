#!/usr/bin/env python3
import os
import sys
import traceback
import discord
from datetime import datetime

print("🚀 Starting bot with debugging...")

# -------------------------
# LOAD CONFIG FROM ENV
# -------------------------
TOKEN = os.getenv("DISCORD_TOKEN")
FACTION_ID = os.getenv("FACTION_ID")
ATTACK_CHANNEL_ID = os.getenv("ATTACK_CHANNEL_ID")
WAR_CHANNEL_ID = os.getenv("WAR_CHANNEL_ID")
LEADER_CHANNEL_ID = os.getenv("LEADER_CHANNEL_ID")

print(f"🔹 Loaded env vars: TOKEN set? {'Yes' if TOKEN else 'No'}, FACTION_ID: {FACTION_ID}")

if not TOKEN:
    print("❌ DISCORD_TOKEN environment variable not set!")
    sys.exit(1)

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
        print(f"✅ Module '{mod_name}' imported successfully")
    except Exception as e:
        print(f"❌ Failed to import module '{mod_name}': {e}")
        traceback.print_exc()
        imported_modules[mod_name] = None

# -------------------------
# CREATE DISCORD CLIENT
# -------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
client = discord.Client(intents=intents)
print("✅ Discord client created successfully with intents")

# -------------------------
# REGISTER COMMANDS
# -------------------------
COMMANDS = {}

for name, mod in imported_modules.items():
    if not mod:
        print(f"⚠️ Module {name} is None, skipping command registration")
        continue

    try:
        if hasattr(mod, "bank"):
            COMMANDS.update({
                "bank": getattr(mod, "bank"),
                "/bank": getattr(mod, "bank")
            })
            print(f"🔹 Registered banking commands for module '{name}'")
        if hasattr(mod, "revives"):
            COMMANDS.update({
                "revives": getattr(mod, "revives"),
                "/revives": getattr(mod, "revives")
            })
            print(f"🔹 Registered revives commands for module '{name}'")
        if hasattr(mod, "bounty"):
            COMMANDS.update({
                "bounty": getattr(mod, "bounty"),
                "/bounty": getattr(mod, "bounty")
            })
            print(f"🔹 Registered bounty commands for module '{name}'")
    except Exception as e:
        print(f"❌ Error registering commands for module '{name}': {e}")
        traceback.print_exc()

print(f"✅ Total commands registered: {list(COMMANDS.keys())}")

# -------------------------
# SETUP MODULE EVENTS (e.g., banking)
# -------------------------
banking_mod = imported_modules.get("banking")
if banking_mod and hasattr(banking_mod, "setup_banking_events"):
    print("🔹 Setting up banking events")
    try:
        banking_mod.setup_banking_events(client)
    except Exception as e:
        print(f"❌ Failed to setup banking events: {e}")
        traceback.print_exc()

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
    try:
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

        print(f"📩 Received message: '{message.content}' from {message.author} in {message.channel}")

        # Dispatch commands
        handled = False
        for cmd_name, cmd_func in COMMANDS.items():
            if content_lower.startswith(cmd_name):
                print(f"⚡ Triggered command '{cmd_name}' from message")
                # Banking needs full message
                if cmd_name in ["bank", "/bank"] and "banking" in imported_modules:
                    await imported_modules["banking"].handle_bank_command(message)
                else:
                    await cmd_func(message.channel)
                handled = True
                break

        if not handled:
            print(f"ℹ️ No command matched for message: '{message.content}'")

    except Exception as e:
        print(f"❌ Error processing message: {e}")
        traceback.print_exc()

# -------------------------
# START BOT
# -------------------------
try:
    print("🚀 Running bot...")
    client.run(TOKEN)
except discord.LoginFailure:
    print("❌ Invalid bot token!")
except KeyboardInterrupt:
    print("👋 Bot stopped by user")
except Exception as e:
    print(f"❌ Failed to start bot: {e}")
    traceback.print_exc()
