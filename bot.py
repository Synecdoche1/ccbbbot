#!/usr/bin/env python3
import os
import sys
import traceback
import threading
from flask import Flask
import discord
import asyncio

print("🚀 Starting bot...")

# -------------------------
# FLASK SERVER TO KEEP RENDER HAPPY
# -------------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_flask, daemon=True).start()
print("✅ Flask server started (dummy server for Render free tier)")

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
modules_to_import = ["revive","attack","bounty","inactivity","war","stock","chain","banking"]
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
# COMMAND HANDLER
# -------------------------
COMMANDS = {}

# Map commands to module functions
for name, mod in imported_modules.items():
    if mod:
        if name == "banking":
            COMMANDS.update({
                "bank": mod.bank,
                "/bank": mod.bank
            })
        elif name == "revive":
            COMMANDS.update({
                "revives": mod.revives,
                "/revives": mod.revives
            })
        # Add other commands here if needed

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
        print("✅ Banking events set up")

# -------------------------
# ON_MESSAGE EVENT
# -------------------------
@client.event
async def on_message(message):
    if message.author == client.user:
        return

    # Only process if bot is mentioned or DM
    should_process = client.user in message.mentions or isinstance(message.channel, discord.DMChannel)
    if not should_process:
        return

    content_lower = message.content.lower().strip()
    # Remove mention text
    mention_str = f"<@{client.user.id}>"
    mention_str_nick = f"<@!{client.user.id}>"
    content_lower = content_lower.replace(mention_str, "").replace(mention_str_nick, "").strip()

    # DEBUG: show received command
    print(f"📩 Received command: {content_lower} from {message.author}")

    for cmd_name, func in COMMANDS.items():
        if content_lower.startswith(cmd_name):
            print(f"⚡ Running command: {cmd_name}")
            try:
                await func(message.channel) if "revives" in cmd_name else await func(client, message)
            except Exception as e:
                print(f"❌ Error running command {cmd_name}: {e}")
                traceback.print_exc()
            break

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
