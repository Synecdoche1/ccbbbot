#!/usr/bin/env python3
import os
import sys
import traceback
import asyncio
import discord
from flask import Flask
from threading import Thread

# -------------------------
# FLASK KEEP-ALIVE
# -------------------------
app = Flask("")

@app.route("/")
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

Thread(target=run_flask).start()
print("✅ Flask server started to keep Render free tier alive")

# -------------------------
# LOAD CONFIG
# -------------------------
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    print("❌ DISCORD_TOKEN environment variable not set!")
    sys.exit(1)

print("✅ Config loaded from environment variables")

# -------------------------
# IMPORT MODULES
# -------------------------
modules_to_import = ["revive", "banking"]
imported_modules = {}
for mod_name in modules_to_import:
    try:
        imported_modules[mod_name] = __import__(f"modules.{mod_name}", fromlist=[mod_name])
        print(f"✅ {mod_name} module imported successfully")
    except Exception as e:
        print(f"❌ Failed to import {mod_name} module: {e}")
        traceback.print_exc()
        imported_modules[mod_name] = None

# -------------------------
# COMMAND REGISTRY
# -------------------------
COMMANDS = {}
if imported_modules.get("revive"):
    COMMANDS.update({
        "revives": imported_modules["revive"].revives,
        "/revives": imported_modules["revive"].revives
    })
if imported_modules.get("banking"):
    COMMANDS.update({
        "bank": imported_modules["banking"].bank,
        "/bank": imported_modules["banking"].bank
    })

print(f"✅ Commands registered: {list(COMMANDS.keys())}")

# -------------------------
# DISCORD CLIENT
# -------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
client = discord.Client(intents=intents)
print("✅ Discord client created")

# -------------------------
# ON_READY
# -------------------------
@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user} (ID: {client.user.id})")
    print(f"✅ Bot is in {len(client.guilds)} guilds")
    for guild in client.guilds:
        print(f"   - {guild.name} (ID: {guild.id})")

    # Setup banking reaction events if available
    banking = imported_modules.get("banking")
    if banking and hasattr(banking, "setup_banking_events"):
        banking.setup_banking_events(client)

# -------------------------
# ON_MESSAGE
# -------------------------
@client.event
async def on_message(message):
    if message.author == client.user:
        return

    # Only respond if bot is mentioned in a server channel
    if not message.guild or client.user not in message.mentions:
        return

    # Normalize content
    content = message.content.strip().lower()
    mention_str = f"<@{client.user.id}>"
    mention_str_nick = f"<@!{client.user.id}>"
    if content.startswith(mention_str):
        content = content[len(mention_str):].strip()
    elif content.startswith(mention_str_nick):
        content = content[len(mention_str_nick):].strip()

    # Remove leading '/' for slash-like commands
    if content.startswith("/"):
        content = content[1:].strip()

    # DEBUG: show message
    print(f"📥 Message received in {message.channel} from {message.author}: '{content}'")

    # Check commands
    for cmd_name, cmd_func in COMMANDS.items():
        normalized_cmd_name = cmd_name.lstrip("/").lower()
        if content.startswith(normalized_cmd_name):
            print(f"📌 Command triggered: {cmd_name} by {message.author}")
            try:
                await cmd_func(message.channel)
            except Exception as e:
                print(f"❌ Error executing {cmd_name}: {e}")
                traceback.print_exc()
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
