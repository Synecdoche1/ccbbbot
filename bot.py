#!/usr/bin/env python3
import sys
import os
import traceback
import asyncio
import re
import discord

print("🚀 Starting bot...")

# -------------------------
# IMPORT CORE LIBRARIES
# -------------------------
try:
    import discord
    print("✅ Discord.py imported successfully")
except ImportError as e:
    print(f"❌ Failed to import discord: {e}")
    sys.exit(1)

try:
    from config import ATTACK_CHANNEL_ID, WAR_CHANNEL_ID, LEADER_CHANNEL_ID, FACTION_ID
    print(f"✅ Config loaded - Faction ID: {FACTION_ID}")
except ImportError as e:
    print(f"❌ Failed to import config: {e}")
    sys.exit(1)

try:
    from pathlib import Path
    print("✅ Pathlib imported successfully")
except ImportError as e:
    print(f"❌ Failed to import pathlib: {e}")
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
        print(f"🔍 DEBUG: Trying to import {mod_name}...")
        imported_modules[mod_name] = __import__(f"modules.{mod_name}", fromlist=[mod_name])
        print(f"✅ {mod_name.capitalize()} module imported successfully")
    except Exception as e:
        print(f"❌ Failed to import {mod_name} module: {e}")
        traceback.print_exc()
        imported_modules[mod_name] = None

# -------------------------
# LOAD BOT TOKEN
# -------------------------
try:
    with open("token.txt") as f:
        TOKEN = f.read().strip()
    print("✅ Bot token loaded successfully")
except FileNotFoundError:
    print("❌ token.txt file not found!")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error reading token: {e}")
    sys.exit(1)

# -------------------------
# CREATE DISCORD CLIENT
# -------------------------
try:
    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)
    print("✅ Discord client created successfully")
except Exception as e:
    print(f"❌ Error creating Discord client: {e}")
    sys.exit(1)

# -------------------------
# COMMAND REGISTRY
# -------------------------
COMMANDS = {}

# Revive commands
revive = imported_modules.get("revive")
if revive:
    COMMANDS.update({
        "revives": revive.revives,
        "/revives": revive.revives
    })

# Bounty commands
bounty = imported_modules.get("bounty")
if bounty:
    COMMANDS.update({
        "bounties": bounty.bounties,
        "/bounties": bounty.bounties
    })

# Inactivity commands
inactivity = imported_modules.get("inactivity")
if inactivity:
    COMMANDS.update({
        "inactivity": inactivity.inactivity,
        "/inactivity": inactivity.inactivity,
        "inactive": inactivity.inactivity,
        "/inactive": inactivity.inactivity
    })

# War commands
war = imported_modules.get("war")
if war:
    COMMANDS.update({
        "war": war.war_status,
        "/war": war.war_status,
        "war_status": war.war_status,
        "/war_status": war.war_status
    })

# Chain commands
chain = imported_modules.get("chain")
if chain:
    COMMANDS.update({
        "chain": chain.chain_command,
        "/chain": chain.chain_command
    })

# Banking commands - FIXED
banking = imported_modules.get("banking")
if banking:
    COMMANDS.update({
        "bank": banking.bank,  # Changed from bank_request to bank
        "/bank": banking.bank
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
    
    # Setup banking events if banking module is available
    if banking and hasattr(banking, 'setup_banking_events'):
        try:
            banking.setup_banking_events(client)
            print("✅ Banking events setup completed")
        except Exception as e:
            print(f"❌ Error setting up banking events: {e}")
    
    # Optional: start module background tasks here
    for mod_name in ["attack", "war", "stock", "chain"]:
        mod = imported_modules.get(mod_name)
        if mod and hasattr(mod, "start"):
            try:
                asyncio.create_task(mod.start(client))
                print(f"✅ {mod_name.capitalize()} monitoring started")
            except Exception as e:
                print(f"❌ Error starting {mod_name} monitoring: {e}")
                traceback.print_exc()

# -------------------------
# ON_MESSAGE EVENT
# -------------------------
@client.event
async def on_message(message):
    try:
        # Always log incoming messages for debugging
        print(f"📨 Message received: '{message.content}' from {message.author} in {message.channel}")
        
        if message.author == client.user:
            print("   ↳ Ignoring message from self")
            return  # ignore self

        # Check for commands when bot is mentioned OR in DMs
        should_process = client.user in message.mentions or isinstance(message.channel, discord.DMChannel)
        print(f"🤔 Should process command? {should_process}")
        
        if not should_process:
            print("   ↳ Not processing (bot not mentioned and not DM)")
            return

        content_lower = message.content.lower().strip()
        print(f"🔍 Processing content: '{content_lower}'")
        
        # Remove mention from content for cleaner command parsing
        if client.user in message.mentions:
            mention_str = f"<@{client.user.id}>"
            mention_str_nick = f"<@!{client.user.id}>"
            content_lower = content_lower.replace(mention_str, "").replace(mention_str_nick, "").strip()
            print(f"🔍 Content after removing mention: '{content_lower}'")

        # Special handling for bank commands with amounts
        if banking and ('bank ' in content_lower or content_lower.startswith('bank')):
            print("🏦 Processing bank command")
            
            # Check if it's just "bank" without amount (show help)
            if content_lower.strip() == 'bank':
                print("🏦 Showing bank help")
                try:
                    await message.channel.send("🔄 Processing bank command...")
                    await banking.bank(message.channel)
                    print("✅ Successfully executed bank help command")
                except Exception as e:
                    error_msg = f"❌ Error executing bank help command: {str(e)}"
                    print(error_msg)
                    traceback.print_exc()
                    await message.channel.send(error_msg)
            else:
                # Handle bank command with amount
                print("🏦 Processing bank command with amount")
                try:
                    await message.channel.send("🔄 Processing bank request...")
                    await banking.handle_bank_command(message)
                    print("✅ Successfully executed bank command")
                except Exception as e:
                    error_msg = f"❌ Error executing bank command: {str(e)}"
                    print(error_msg)
                    traceback.print_exc()
                    await message.channel.send(error_msg)
            return

        # Check other commands
        command_found = False
        for cmd, func in COMMANDS.items():
            if not func:
                continue
            
            print(f"🔍 Checking if '{cmd.lower()}' matches '{content_lower}'")
            
            # Check if the command matches exactly or is contained in the message
            if content_lower == cmd.lower() or cmd.lower() in content_lower:
                command_found = True
                try:
                    print(f"🚀 Executing command: {cmd}")
                    
                    # Show different processing messages based on command type
                    if 'war' in cmd.lower():
                        await message.channel.send("🔄 Processing war command...")
                    elif 'revive' in cmd.lower():
                        await message.channel.send("🔄 Processing revives command...")
                    elif 'bounty' in cmd.lower() or 'bounties' in cmd.lower():
                        await message.channel.send("🔄 Processing bounties command...")
                    elif 'inactiv' in cmd.lower():
                        await message.channel.send("🔄 Processing inactivity command...")
                    elif 'chain' in cmd.lower():
                        await message.channel.send("🔄 Processing chain command...")
                    else:
                        await message.channel.send("🔄 Processing command...")
                    
                    await func(message.channel)
                    print(f"✅ Successfully executed command: {cmd}")
                except Exception as e:
                    error_msg = f"❌ Error executing command '{cmd}': {str(e)}"
                    print(error_msg)
                    traceback.print_exc()
                    await message.channel.send(error_msg)
                break

        if not command_found:
            # No command found, send help
            print("❓ No command found, sending help")
            embed = discord.Embed(
                title="🤖 Available Commands",
                description="Mention me with one of these commands:",
                color=0x00FF00
            )
            
            # Build command list dynamically based on available modules
            command_list = []
            if revive:
                command_list.append("• `revives` or `/revives` - Show revivable faction members")
            if bounty:
                command_list.append("• `bounties` or `/bounties` - Show current bounties")
            if inactivity:
                command_list.append("• `inactivity` or `/inactivity` - Check inactive members")
            if war:
                command_list.append("• `war` or `/war` - Check current war status")
            if chain:
                command_list.append("• `chain` or `/chain` - Show chain information")
            if banking:
                command_list.append("• `bank <amount>` - Request money from faction bank")
            
            embed.add_field(
                name="Commands", 
                value="\n".join(command_list), 
                inline=False
            )
            
            example_text = f"<@{client.user.id}> revives\n<@{client.user.id}> war"
            if banking:
                example_text += f"\n<@{client.user.id}> bank 1m"
            
            embed.add_field(
                name="Example",
                value=example_text,
                inline=False
            )
            embed.add_field(
                name="Debug Info",
                value=f"Your message: `{message.content}`\nProcessed as: `{content_lower}`",
                inline=False
            )
            await message.channel.send(embed=embed)

    except Exception as e:
        error_msg = f"❌ Error in on_message: {e}"
        print(error_msg)
        traceback.print_exc()
        # Try to send error to channel if possible
        try:
            await message.channel.send(f"❌ An error occurred: {str(e)}")
        except:
            pass

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