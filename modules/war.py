#!/usr/bin/env python3
"""
War module for Torn bot - monitors ranked wars and provides live updates
Enhanced version with better error handling, caching, and maintainability
"""

import discord
import aiohttp
import asyncio
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass, asdict
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class WarStatus(Enum):
    SCHEDULED = "scheduled"  # War is scheduled but hasn't started
    ACTIVE = "active"
    ENDED = "ended"
    NOT_FOUND = "not_found"


@dataclass
class FactionInfo:
    id: int
    name: str
    tag: str
    members: int
    rank: int
    rank_name: str
    respect: int
    capacity: int
    wins: int
    score: int = 0


@dataclass
class WarData:
    war_id: int
    factions: List[FactionInfo]
    target_score: int
    start_timestamp: int
    end_timestamp: int
    status: WarStatus

    @property
    def is_active(self) -> bool:
        now = datetime.now(timezone.utc).timestamp()
        return (
            self.status == WarStatus.ACTIVE and
            self.start_timestamp > 0 and
            self.start_timestamp <= now and
            (self.end_timestamp == 0 or self.end_timestamp > now)
        )

    @property
    def is_scheduled(self) -> bool:
        now = datetime.now(timezone.utc).timestamp()
        return (
            self.status == WarStatus.SCHEDULED and
            self.start_timestamp > 0 and
            self.start_timestamp > now
        )

    @property
    def our_faction(self) -> Optional[FactionInfo]:
        """Get our faction from the war"""
        return next((f for f in self.factions if f.id == FACTION_ID), None)

    @property
    def enemy_faction(self) -> Optional[FactionInfo]:
        """Get the enemy faction"""
        return next((f for f in self.factions if f.id != FACTION_ID), None)


class APIError(Exception):
    """Custom exception for API-related errors"""
    pass


class ConfigError(Exception):
    """Custom exception for configuration errors"""
    pass


# Configuration loading with validation
def load_config() -> Tuple[str, int, int]:
    """Load and validate configuration"""
    try:
        from config import TORN_API_KEY, FACTION_ID, WAR_CHANNEL_ID
    except ImportError:
        TORN_API_KEY = os.getenv("TORN_API_KEY")
        FACTION_ID = int(os.getenv("FACTION_ID", 0))
        WAR_CHANNEL_ID = int(os.getenv("WAR_CHANNEL_ID", 0))

    if not TORN_API_KEY:
        raise ConfigError("TORN_API_KEY is required")
    if not FACTION_ID:
        raise ConfigError("FACTION_ID is required")
    if not WAR_CHANNEL_ID:
        raise ConfigError("WAR_CHANNEL_ID is required")

    return TORN_API_KEY, FACTION_ID, WAR_CHANNEL_ID


# Load config with error handling
try:
    TORN_API_KEY, FACTION_ID, WAR_CHANNEL_ID = load_config()
except ConfigError as e:
    logger.error(f"Configuration error: {e}")
    TORN_API_KEY, FACTION_ID, WAR_CHANNEL_ID = None, None, None


class TornAPIClient:
    """Handles all Torn API interactions with rate limiting and caching"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = None
        self.cache = {}
        self.cache_ttl = {}
        self.rate_limit_delay = 1.1  # Seconds between requests
        self.last_request = 0

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={'User-Agent': 'Torn War Bot/2.0'}
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def _make_request(self, url: str) -> Optional[Dict]:
        """Make rate-limited API request with retry logic"""
        if not self.session:
            raise APIError("API client not initialized")

        # Rate limiting
        now = asyncio.get_event_loop().time()
        time_since_last = now - self.last_request
        if time_since_last < self.rate_limit_delay:
            await asyncio.sleep(self.rate_limit_delay - time_since_last)

        # Check cache
        cache_key = url
        if cache_key in self.cache and now < self.cache_ttl.get(cache_key, 0):
            logger.debug(f"Cache hit for {url}")
            return self.cache[cache_key]

        max_retries = 3
        for attempt in range(max_retries):
            try:
                self.last_request = asyncio.get_event_loop().time()
                
                async with self.session.get(f"{url}?key={self.api_key}") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        # Cache successful responses for 60 seconds
                        self.cache[cache_key] = data
                        self.cache_ttl[cache_key] = now + 60
                        return data
                    elif resp.status == 429:  # Rate limited
                        wait_time = 2 ** attempt
                        logger.warning(f"Rate limited, waiting {wait_time}s")
                        await asyncio.sleep(wait_time)
                        continue
                    elif resp.status in [502, 503, 504]:  # Server errors
                        if attempt < max_retries - 1:
                            await asyncio.sleep(2 ** attempt)
                            continue
                    
                    logger.error(f"API error {resp.status} for {url}")
                    if resp.status == 403:
                        raise APIError("Invalid API key")
                    elif resp.status == 404:
                        return None
                    
            except aiohttp.ClientError as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Request failed, retrying: {e}")
                    await asyncio.sleep(2 ** attempt)
                    continue
                logger.error(f"API request failed after {max_retries} attempts: {e}")
                
        raise APIError(f"Failed to fetch data from {url}")

    async def get_faction_details(self, faction_id: int) -> Optional[FactionInfo]:
        """Get faction details with error handling"""
        try:
            data = await self._make_request(f"https://api.torn.com/v2/faction/{faction_id}/basic")
            if not data:
                return None
                
            basic = data.get("basic", {})
            rank = basic.get("rank", {})
            
            return FactionInfo(
                id=faction_id,
                name=basic.get("name", "Unknown"),
                tag=basic.get("tag", ""),
                members=basic.get("members", 0),
                rank=rank.get("level", 0),
                rank_name=rank.get("name", "Unranked"),
                respect=basic.get("respect", 0),
                capacity=basic.get("capacity", 0),
                wins=rank.get("wins", 0)
            )
        except APIError as e:
            logger.error(f"Failed to get faction {faction_id} details: {e}")
            return None

    async def get_war_data(self) -> Optional[WarData]:
        """Get current war data"""
        try:
            data = await self._make_request("https://api.torn.com/v2/faction/wars")
            if not data:
                return None
                
            wars = data.get("wars", {})
            ranked_war = wars.get("ranked")
            
            if not ranked_war:
                return WarData(
                    war_id=0,
                    factions=[],
                    target_score=0,
                    start_timestamp=0,
                    end_timestamp=0,
                    status=WarStatus.NOT_FOUND
                )
            
            war_id = ranked_war.get("war_id", 0)
            target_score = ranked_war.get("target", 0)
            start_timestamp = ranked_war.get("start", 0)
            end_timestamp = ranked_war.get("end")
            
            # Handle None end_timestamp (war hasn't started yet)
            if end_timestamp is None:
                end_timestamp = 0
            elif not isinstance(end_timestamp, (int, float)):
                end_timestamp = 0
            
            # Get faction data with scores
            factions = []
            for faction_data in ranked_war.get("factions", []):
                faction_info = await self.get_faction_details(faction_data.get("id"))
                if faction_info:
                    faction_info.score = faction_data.get("score", 0)
                    factions.append(faction_info)
            
            # Determine status based on start/end timestamps
            now = datetime.now(timezone.utc).timestamp()
            
            if start_timestamp > 0:
                if start_timestamp > now:
                    # War is scheduled but hasn't started
                    status = WarStatus.SCHEDULED
                elif end_timestamp > 0 and end_timestamp <= now:
                    # War has ended
                    status = WarStatus.ENDED
                else:
                    # War is active (started but not ended)
                    status = WarStatus.ACTIVE
            else:
                # No valid start timestamp
                status = WarStatus.NOT_FOUND
            
            return WarData(
                war_id=war_id,
                factions=factions,
                target_score=target_score,
                start_timestamp=start_timestamp,
                end_timestamp=end_timestamp,
                status=status
            )
            
        except APIError as e:
            logger.error(f"Failed to get war data: {e}")
            return None


class WarMonitor:
    """Enhanced war monitor with better state management and error handling"""
    
    def __init__(self, client: discord.Client):
        self.client = client
        self.api_client = None
        
        # Configuration
        if not all([TORN_API_KEY, FACTION_ID, WAR_CHANNEL_ID]):
            raise ConfigError("Missing required configuration")
            
        # State management
        self.current_war_id = None
        self.war_message_id = None
        self.last_update = None
        self.is_monitoring = False
        self.monitor_task = None
        
        # Files and directories
        self.data_dir = Path("data")
        self.data_dir.mkdir(exist_ok=True)
        self.state_file = self.data_dir / "war_state.json"
        
        # Load previous state
        self._load_state()

    def _load_state(self) -> None:
        """Load previous state from file"""
        try:
            if self.state_file.exists():
                with open(self.state_file, "r") as f:
                    data = json.load(f)
                    self.current_war_id = data.get("current_war_id")
                    self.war_message_id = data.get("war_message_id")
                    last_update_str = data.get("last_update")
                    if last_update_str:
                        self.last_update = datetime.fromisoformat(last_update_str)
                    logger.info(f"Loaded state: War ID {self.current_war_id}")
        except Exception as e:
            logger.error(f"Failed to load state: {e}")

    def _save_state(self) -> None:
        """Save current state to file"""
        try:
            state_data = {
                "current_war_id": self.current_war_id,
                "war_message_id": self.war_message_id,
                "last_update": self.last_update.isoformat() if self.last_update else None
            }
            with open(self.state_file, "w") as f:
                json.dump(state_data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    @staticmethod
    def format_number(num: int) -> str:
        """Format numbers with commas"""
        return f"{num:,}"

    @staticmethod
    def create_progress_bar(current: int, target: int, length: int = 10) -> str:
        """Create a visual progress bar"""
        if target <= 0:
            return "⬜" * length
        progress = min(current / target, 1.0)
        filled = int(progress * length)
        return "🟩" * filled + "⬜" * (length - filled)

    def calculate_time_remaining(self, war_data: WarData) -> str:
        """Calculate and format remaining time based on war status"""
        now = datetime.now(timezone.utc)
        
        if war_data.status == WarStatus.SCHEDULED:
            # War hasn't started yet, show time until start
            start_time = datetime.fromtimestamp(war_data.start_timestamp, tz=timezone.utc)
            if start_time <= now:
                return "🚀 **WAR STARTING!**"
                
            diff = start_time - now
            total_seconds = int(diff.total_seconds())
            
            if total_seconds >= 86400:  # More than a day
                days = total_seconds // 86400
                hours = (total_seconds % 86400) // 3600
                return f"⏰ Starts in **{days}d {hours}h**"
            elif total_seconds >= 3600:  # More than an hour
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                return f"⏰ Starts in **{hours}h {minutes}m**"
            else:
                minutes = total_seconds // 60
                return f"⏰ Starts in **{minutes}m**"
                
        elif war_data.status == WarStatus.ACTIVE:
            # War is active, show time until end (if known)
            if war_data.end_timestamp > 0:
                end_time = datetime.fromtimestamp(war_data.end_timestamp, tz=timezone.utc)
                if end_time <= now:
                    return "🏁 **WAR ENDED!**"
                    
                diff = end_time - now
                total_seconds = int(diff.total_seconds())
                
                if total_seconds >= 86400:
                    days = total_seconds // 86400
                    hours = (total_seconds % 86400) // 3600
                    return f"⏰ Ends in **{days}d {hours}h**"
                elif total_seconds >= 3600:
                    hours = total_seconds // 3600
                    minutes = (total_seconds % 3600) // 60
                    return f"⏰ Ends in **{hours}h {minutes}m**"
                else:
                    minutes = total_seconds // 60
                    return f"⏰ Ends in **{minutes}m**"
            else:
                return "🔥 **WAR ACTIVE!**"
                
        elif war_data.status == WarStatus.ENDED:
            return "🏁 **WAR ENDED!**"
        else:
            return "❓ **UNKNOWN STATUS**"

    async def create_war_embed(self, war_data: WarData) -> discord.Embed:
        """Create a rich embed for war information"""
        if war_data.status == WarStatus.NOT_FOUND:
            return discord.Embed(
                title="⚔️ War Status",
                description="No active ranked war found",
                color=0x808080,
                timestamp=datetime.now(timezone.utc)
            )

        if len(war_data.factions) < 2:
            return discord.Embed(
                title="⚔️ War Status",
                description="Insufficient faction data",
                color=0xFF4500,
                timestamp=datetime.now(timezone.utc)
            )

        # Determine our faction and enemy
        our_faction = war_data.our_faction
        enemy_faction = war_data.enemy_faction
        
        if not our_faction or not enemy_faction:
            # Fallback to first two factions
            f1, f2 = war_data.factions[0], war_data.factions[1]
        else:
            f1, f2 = our_faction, enemy_faction

        # Determine embed color based on war status and our performance
        if war_data.status == WarStatus.SCHEDULED:
            color = 0xFFFF00  # Yellow - scheduled
        elif war_data.status == WarStatus.ENDED:
            color = 0x808080  # Gray - ended
        elif our_faction:
            if our_faction.score > enemy_faction.score:
                color = 0x00FF00  # Green - winning
            elif our_faction.score < enemy_faction.score:
                color = 0xFF0000  # Red - losing
            else:
                color = 0x0099FF  # Blue - tied
        else:
            color = 0x0099FF  # Blue - neutral

        # Create title based on status
        if war_data.status == WarStatus.SCHEDULED:
            title = f"⚔️ Ranked War Scheduled"
        elif war_data.status == WarStatus.ACTIVE:
            title = f"⚔️ Ranked War In Progress"
        elif war_data.status == WarStatus.ENDED:
            title = f"⚔️ Ranked War Ended"
        else:
            title = f"⚔️ Ranked War"
            
        if war_data.war_id:
            title += f" (ID: {war_data.war_id})"

        embed = discord.Embed(
            title=title,
            color=color,
            timestamp=datetime.now(timezone.utc)
        )

        # Matchup field
        f1_score_str = self.format_number(f1.score)
        f2_score_str = self.format_number(f2.score)
        f1_progress = self.create_progress_bar(f1.score, war_data.target_score)
        f2_progress = self.create_progress_bar(f2.score, war_data.target_score)

        matchup_text = (
            f"**[{f1.name}]({self._get_faction_url(f1.id)})** "
            f"{f'[{f1.tag}]' if f1.tag else ''}\n"
            f"📊 **{f1_score_str}** points\n"
            f"{f1_progress}\n\n"
            f"🆚\n\n"
            f"**[{f2.name}]({self._get_faction_url(f2.id)})** "
            f"{f'[{f2.tag}]' if f2.tag else ''}\n"
            f"📊 **{f2_score_str}** points\n"
            f"{f2_progress}"
        )
        
        embed.add_field(name="🥊 Matchup", value=matchup_text, inline=False)

        # War details
        embed.add_field(
            name="🎯 Target Score", 
            value=self.format_number(war_data.target_score), 
            inline=True
        )
        embed.add_field(
            name="⏱️ Status", 
            value=self.calculate_time_remaining(war_data), 
            inline=True
        )

        # Score difference
        score_diff = abs(f1.score - f2.score)
        embed.add_field(
            name="📈 Score Gap", 
            value=self.format_number(score_diff), 
            inline=True
        )

        # Faction statistics
        stats_text = self._format_faction_stats(f1, f2)
        if stats_text:
            embed.add_field(name="📊 Faction Details", value=stats_text, inline=False)

        embed.set_footer(text="Torn War Bot • Updates every 2 minutes")
        return embed

    def _get_faction_url(self, faction_id: int) -> str:
        """Generate faction profile URL"""
        return f"https://www.torn.com/factions.php?step=profile&ID={faction_id}"

    def _format_faction_stats(self, f1: FactionInfo, f2: FactionInfo) -> str:
        """Format faction statistics for embed"""
        return (
            f"**{f1.name}:**\n"
            f"👑 Rank: {f1.rank} ({f1.rank_name})\n"
            f"👥 Members: {f1.members}/{f1.capacity}\n"
            f"🏆 Respect: {self.format_number(f1.respect)}\n"
            f"🥇 Rank Wars Won: {f1.wins}\n\n"
            f"**{f2.name}:**\n"
            f"👑 Rank: {f2.rank} ({f2.rank_name})\n"
            f"👥 Members: {f2.members}/{f2.capacity}\n"
            f"🏆 Respect: {self.format_number(f2.respect)}\n"
            f"🥇 Rank Wars Won: {f2.wins}"
        )

    async def _send_new_war_message(self, channel: discord.TextChannel, war_data: WarData) -> None:
        """Send a new war message"""
        embed = await self.create_war_embed(war_data)
        
        # Add notification based on war status
        if war_data.status == WarStatus.SCHEDULED:
            content = "📅 **NEW RANKED WAR SCHEDULED!** 📅"
        elif war_data.status == WarStatus.ACTIVE:
            content = "🚨 **RANKED WAR STARTED!** 🚨"
        else:
            content = None
            
        try:
            msg = await channel.send(content=content, embed=embed)
            self.war_message_id = msg.id
            logger.info(f"Sent new war message for war {war_data.war_id}")
        except discord.DiscordException as e:
            logger.error(f"Failed to send war message: {e}")

    async def _update_existing_message(self, channel: discord.TextChannel, war_data: WarData) -> bool:
        """Update existing war message, return True if successful"""
        if not self.war_message_id:
            return False
            
        try:
            msg = await channel.fetch_message(self.war_message_id)
            embed = await self.create_war_embed(war_data)
            await msg.edit(embed=embed)
            return True
        except discord.NotFound:
            logger.info(f"War message {self.war_message_id} not found, will create new one")
            self.war_message_id = None
            return False
        except discord.DiscordException as e:
            logger.error(f"Failed to update war message: {e}")
            return False

    async def _monitor_loop(self) -> None:
        """Main monitoring loop"""
        logger.info("War monitoring started")
        
        async with TornAPIClient(TORN_API_KEY) as api_client:
            self.api_client = api_client
            
            while self.is_monitoring:
                try:
                    # Get war data
                    war_data = await api_client.get_war_data()
                    if not war_data:
                        await asyncio.sleep(120)
                        continue

                    # Get Discord channel
                    channel = self.client.get_channel(WAR_CHANNEL_ID)
                    if not channel:
                        logger.error(f"Could not find channel {WAR_CHANNEL_ID}")
                        await asyncio.sleep(120)
                        continue

                    # Handle war state changes
                    if war_data.war_id != self.current_war_id:
                        # New war detected
                        logger.info(f"New war detected: {war_data.war_id} (was {self.current_war_id})")
                        self.current_war_id = war_data.war_id
                        self.war_message_id = None
                        await self._send_new_war_message(channel, war_data)
                    else:
                        # Update existing war
                        success = await self._update_existing_message(channel, war_data)
                        if not success:
                            await self._send_new_war_message(channel, war_data)

                    # Update state
                    self.last_update = datetime.now(timezone.utc)
                    self._save_state()

                    # Sleep before next check
                    await asyncio.sleep(120)

                except Exception as e:
                    logger.error(f"Error in monitoring loop: {e}", exc_info=True)
                    await asyncio.sleep(120)

        logger.info("War monitoring stopped")

    async def start_monitoring(self) -> bool:
        """Start war monitoring"""
        if self.is_monitoring:
            logger.info("War monitoring already running")
            return True

        try:
            self.is_monitoring = True
            self.monitor_task = asyncio.create_task(self._monitor_loop())
            return True
        except Exception as e:
            logger.error(f"Failed to start monitoring: {e}")
            self.is_monitoring = False
            return False

    async def stop_monitoring(self) -> None:
        """Stop war monitoring"""
        self.is_monitoring = False
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
        self._save_state()
        logger.info("War monitoring stopped")

    async def get_current_status(self) -> Optional[WarData]:
        """Get current war status"""
        if not self.api_client:
            async with TornAPIClient(TORN_API_KEY) as api_client:
                return await api_client.get_war_data()
        return await self.api_client.get_war_data()


# Global monitor instance
war_monitor: Optional[WarMonitor] = None


async def start(client: discord.Client) -> bool:
    """Initialize and start war monitoring"""
    global war_monitor
    
    try:
        if not all([TORN_API_KEY, FACTION_ID, WAR_CHANNEL_ID]):
            logger.error("Missing required configuration for war monitoring")
            return False

        if war_monitor and war_monitor.is_monitoring:
            logger.info("War monitoring already running")
            return True

        war_monitor = WarMonitor(client)
        return await war_monitor.start_monitoring()
        
    except ConfigError as e:
        logger.error(f"Configuration error: {e}")
        return False
    except Exception as e:
        logger.error(f"Failed to start war monitoring: {e}")
        return False


async def stop() -> None:
    """Stop war monitoring"""
    global war_monitor
    if war_monitor:
        await war_monitor.stop_monitoring()


async def war_status(channel: discord.TextChannel) -> None:
    """Send current war status to channel"""
    if not war_monitor:
        embed = discord.Embed(
            title="❌ War Monitor",
            description="War monitoring is not running",
            color=0xFF0000
        )
        await channel.send(embed=embed)
        return

    # Send loading message
    loading_embed = discord.Embed(
        title="🔄 Checking War Status",
        description="Fetching current war information...",
        color=0x0099FF
    )
    loading_msg = await channel.send(embed=loading_embed)

    try:
        war_data = await war_monitor.get_current_status()
        if war_data:
            embed = await war_monitor.create_war_embed(war_data)
        else:
            embed = discord.Embed(
                title="❌ War Status",
                description="Failed to fetch war data from Torn API",
                color=0xFF0000
            )
        
        await loading_msg.edit(embed=embed)
        
    except Exception as e:
        logger.error(f"Error getting war status: {e}")
        error_embed = discord.Embed(
            title="❌ Error",
            description="An error occurred while fetching war status",
            color=0xFF0000
        )
        await loading_msg.edit(embed=error_embed)