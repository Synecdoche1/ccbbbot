#!/usr/bin/env python3
"""
Bounty module for Torn bot - monitors faction member bounties and provides notifications
Enhanced version with better error handling, async operations, and improved features
"""

import discord
import aiohttp
import asyncio
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Set, Tuple, Any
from dataclasses import dataclass, asdict
from enum import Enum
import logging
import hashlib

logger = logging.getLogger(__name__)


class BountyType(Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    EXPIRED = "expired"


@dataclass
class FactionMember:
    id: int
    name: str
    level: int = 0
    status: str = "unknown"
    last_action: Optional[datetime] = None


@dataclass 
class BountyInfo:
    target_id: int
    target_name: str
    reward: int
    quantity: int
    lister_id: Optional[int]
    lister_name: Optional[str]
    is_anonymous: bool
    reason: str
    posted_time: Optional[datetime] = None
    bounty_type: BountyType = BountyType.ACTIVE

    @property
    def unique_key(self) -> str:
        """Generate unique key for bounty deduplication"""
        lister = "anon" if self.is_anonymous else str(self.lister_id or self.lister_name or "unknown").strip().lower()
        reason_normalized = " ".join(self.reason.strip().split()).lower() if self.reason else ""
        
        # Create hash of key components to avoid very long keys
        key_data = f"{self.target_id}|{self.reward}|{self.quantity}|{lister}|{reason_normalized}"
        return hashlib.md5(key_data.encode()).hexdigest()

    @property
    def profile_url(self) -> str:
        return f"https://www.torn.com/profiles.php?XID={self.target_id}"

    @property 
    def formatted_reward(self) -> str:
        return f"${self.reward:,}"

    @property
    def formatted_reason(self) -> str:
        if not self.reason:
            return "No reason provided"
        reason = self.reason.strip()
        return reason[:197] + "..." if len(reason) > 200 else reason

    @property
    def lister_display(self) -> str:
        if self.is_anonymous:
            return "Anonymous"
        return self.lister_name or f"User {self.lister_id}" if self.lister_id else "Unknown"


class ConfigError(Exception):
    """Custom exception for configuration errors"""
    pass


class APIError(Exception):
    """Custom exception for API-related errors"""
    pass


def load_config() -> Tuple[str, int]:
    """Load and validate configuration"""
    try:
        from config import TORN_API_KEY, FACTION_ID
    except ImportError:
        TORN_API_KEY = os.getenv("TORN_API_KEY")
        FACTION_ID = int(os.getenv("FACTION_ID", 0))

    if not TORN_API_KEY:
        raise ConfigError("TORN_API_KEY is required")
    if not FACTION_ID:
        raise ConfigError("FACTION_ID is required")

    return TORN_API_KEY, FACTION_ID


# Load config with error handling
try:
    TORN_API_KEY, FACTION_ID = load_config()
except ConfigError as e:
    logger.error(f"Configuration error: {e}")
    TORN_API_KEY, FACTION_ID = None, None


class TornAPIClient:
    """Async Torn API client with rate limiting and error handling"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = None
        self.rate_limit_delay = 1.1
        self.last_request = 0
        self.request_count = 0
        self.start_time = asyncio.get_event_loop().time()

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={
                'User-Agent': 'Torn Bounty Bot/2.0',
                'Accept': 'application/json'
            }
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def _make_request(self, url: str, retries: int = 3) -> Optional[Dict]:
        """Make rate-limited API request with retry logic"""
        if not self.session:
            raise APIError("API client not initialized")

        # Rate limiting
        now = asyncio.get_event_loop().time()
        time_since_last = now - self.last_request
        if time_since_last < self.rate_limit_delay:
            await asyncio.sleep(self.rate_limit_delay - time_since_last)

        for attempt in range(retries):
            try:
                self.last_request = asyncio.get_event_loop().time()
                self.request_count += 1

                async with self.session.get(f"{url}?key={self.api_key}") as resp:
                    if resp.status == 200:
                        return await resp.json()
                    elif resp.status == 429:  # Rate limited
                        wait_time = min(2 ** attempt, 60)  # Max 60s wait
                        logger.warning(f"Rate limited, waiting {wait_time}s")
                        await asyncio.sleep(wait_time)
                        continue
                    elif resp.status in [502, 503, 504]:  # Server errors
                        if attempt < retries - 1:
                            await asyncio.sleep(2 ** attempt)
                            continue
                    elif resp.status == 403:
                        raise APIError("Invalid API key or insufficient permissions")
                    elif resp.status == 404:
                        return None
                        
                    logger.error(f"API error {resp.status} for {url}")
                    if attempt < retries - 1:
                        await asyncio.sleep(2 ** attempt)
                        continue
                        
            except aiohttp.ClientError as e:
                if attempt < retries - 1:
                    logger.warning(f"Request failed, retrying: {e}")
                    await asyncio.sleep(2 ** attempt)
                    continue
                logger.error(f"API request failed after {retries} attempts: {e}")
                
        raise APIError(f"Failed to fetch data from {url} after {retries} attempts")

    async def get_faction_members(self) -> Dict[int, FactionMember]:
        """Get faction members with their details"""
        try:
            data = await self._make_request(f"https://api.torn.com/v2/faction/members")
            if not data:
                return {}
                
            members = {}
            members_data = data.get("members", {})
            
            # Handle both dict and list formats for members data
            if isinstance(members_data, dict):
                # If it's a dict, iterate over values
                member_list = members_data.values()
            elif isinstance(members_data, list):
                # If it's a list, use directly
                member_list = members_data
            else:
                logger.error(f"Unexpected members data format: {type(members_data)}")
                return {}
                
            for member_data in member_list:
                if not isinstance(member_data, dict):
                    logger.warning(f"Skipping invalid member data: {member_data}")
                    continue
                    
                member_id = member_data.get("id")
                if not member_id:
                    logger.warning(f"Member missing ID: {member_data}")
                    continue
                    
                member = FactionMember(
                    id=member_id,
                    name=member_data.get("name", "Unknown"),
                    level=member_data.get("level", 0),
                    status=member_data.get("status", {}).get("description", "unknown") 
                           if isinstance(member_data.get("status"), dict) 
                           else str(member_data.get("status", "unknown"))
                )
                
                # Parse last action if available
                last_action_data = member_data.get("last_action")
                if last_action_data and isinstance(last_action_data, dict):
                    timestamp = last_action_data.get("timestamp")
                    if timestamp:
                        try:
                            member.last_action = datetime.fromtimestamp(
                                timestamp, 
                                tz=timezone.utc
                            )
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Invalid timestamp for member {member_id}: {e}")
                
                members[member.id] = member
                
            logger.info(f"Retrieved {len(members)} faction members")
            return members
            
        except APIError as e:
            logger.error(f"Failed to get faction members: {e}")
            return {}
        except Exception as e:
            logger.error(f"Unexpected error getting faction members: {e}")
            return {}

    async def get_user_bounties(self, user_id: int) -> List[BountyInfo]:
        """Get bounties for a specific user"""
        try:
            data = await self._make_request(f"https://api.torn.com/v2/user/{user_id}/bounties")
            if not data:
                return []
                
            bounties = []
            bounties_data = data.get("bounties", [])
            
            # Ensure bounties_data is a list
            if not isinstance(bounties_data, list):
                logger.error(f"Expected bounties list, got {type(bounties_data)}")
                return []
                
            for bounty_data in bounties_data:
                if not isinstance(bounty_data, dict):
                    logger.warning(f"Skipping invalid bounty data: {bounty_data}")
                    continue
                    
                bounty = BountyInfo(
                    target_id=bounty_data.get("target_id", user_id),
                    target_name=bounty_data.get("target_name", "Unknown"),
                    reward=bounty_data.get("reward", 0),
                    quantity=bounty_data.get("quantity", 1),
                    lister_id=bounty_data.get("lister_id"),
                    lister_name=bounty_data.get("lister_name"),
                    is_anonymous=bounty_data.get("is_anonymous", False),
                    reason=bounty_data.get("reason", ""),
                    bounty_type=BountyType.ACTIVE
                )
                
                # Parse posted time if available
                posted_timestamp = bounty_data.get("posted")
                if posted_timestamp:
                    try:
                        bounty.posted_time = datetime.fromtimestamp(
                            posted_timestamp,
                            tz=timezone.utc
                        )
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Invalid posted timestamp for bounty: {e}")
                
                bounties.append(bounty)
                
            return bounties
            
        except APIError as e:
            logger.error(f"Failed to get bounties for user {user_id}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error getting bounties for user {user_id}: {e}")
            return []

    @property
    def stats(self) -> Dict[str, Any]:
        """Get API client statistics"""
        uptime = asyncio.get_event_loop().time() - self.start_time
        return {
            "requests_made": self.request_count,
            "uptime_seconds": uptime,
            "requests_per_minute": (self.request_count / uptime * 60) if uptime > 0 else 0
        }


class BountyMonitor:
    """Enhanced bounty monitor with better state management"""
    
    def __init__(self, client: discord.Client):
        self.client = client
        self.api_client = None
        
        # Configuration
        if not all([TORN_API_KEY, FACTION_ID]):
            raise ConfigError("Missing required configuration")
            
        # State management
        self.is_monitoring = False
        self.monitor_task = None
        self.last_check = None
        self.check_interval = 300  # 5 minutes default
        
        # Data storage
        self.data_dir = Path("data")
        self.data_dir.mkdir(exist_ok=True)
        self.cache_file = self.data_dir / "bounty_cache.json"
        self.stats_file = self.data_dir / "bounty_stats.json"
        
        # Cache and statistics
        self.known_bounty_keys: Set[str] = set()
        self.total_bounties_found = 0
        self.total_checks_performed = 0
        
        self._load_cache()

    def _load_cache(self) -> None:
        """Load bounty cache from file"""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, "r") as f:
                    data = json.load(f)
                    self.known_bounty_keys = set(data.get("known_keys", []))
                    self.total_bounties_found = data.get("total_found", 0)
                    self.total_checks_performed = data.get("total_checks", 0)
                    
                    # Parse last check time
                    last_check_str = data.get("last_check")
                    if last_check_str:
                        try:
                            self.last_check = datetime.fromisoformat(last_check_str)
                        except ValueError as e:
                            logger.warning(f"Invalid last_check format: {e}")
                            
                logger.info(f"Loaded cache with {len(self.known_bounty_keys)} known bounties")
        except Exception as e:
            logger.error(f"Failed to load bounty cache: {e}")

    def _save_cache(self) -> None:
        """Save bounty cache to file"""
        try:
            cache_data = {
                "known_keys": sorted(list(self.known_bounty_keys)),
                "total_found": self.total_bounties_found,
                "total_checks": self.total_checks_performed,
                "last_check": self.last_check.isoformat() if self.last_check else None
            }
            
            with open(self.cache_file, "w") as f:
                json.dump(cache_data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save bounty cache: {e}")

    def _clean_old_cache_entries(self, max_age_days: int = 7) -> None:
        """Remove old cache entries to prevent unlimited growth"""
        # This is a simple implementation - in practice you might want to store
        # timestamps with cache entries for more precise cleanup
        if len(self.known_bounty_keys) > 10000:  # Arbitrary limit
            # Keep only the most recent 5000 entries
            keys_list = list(self.known_bounty_keys)
            self.known_bounty_keys = set(keys_list[-5000:])
            logger.info("Cleaned old cache entries")

    async def create_bounty_embed(self, new_bounties: List[BountyInfo], is_test: bool = False) -> discord.Embed:
        """Create Discord embed for bounty notifications"""
        if not new_bounties:
            embed = discord.Embed(
                title="🎯 Bounty Check Complete",
                description="🎉 No new bounties found on faction members!",
                color=0x00FF00,
                timestamp=datetime.now(timezone.utc)
            )
        else:
            total_value = sum(b.reward * b.quantity for b in new_bounties)
            
            embed = discord.Embed(
                title=f"🎯 {'Test ' if is_test else ''}New Bounties on Faction Members",
                color=0xFF0000,
                description=f"Found **{len(new_bounties)} new bounties** worth **${total_value:,}** total!",
                timestamp=datetime.now(timezone.utc)
            )
            
            # Add bounties (limit to 10 to avoid embed limits)
            displayed_bounties = new_bounties[:10]
            for bounty in displayed_bounties:
                field_name = f"{bounty.target_name} - {bounty.formatted_reward}"
                if bounty.quantity > 1:
                    field_name += f" (×{bounty.quantity})"
                    
                field_value = (
                    f"👤 **[Profile]({bounty.profile_url})** • "
                    f"Lister: {bounty.lister_display}\n"
                    f"Reason: {bounty.formatted_reason}"
                )
                
                embed.add_field(name=field_name, value=field_value, inline=False)
            
            if len(new_bounties) > 10:
                embed.add_field(
                    name="➕ Additional Bounties",
                    value=f"... and {len(new_bounties) - 10} more bounties not shown",
                    inline=False
                )
        
        embed.set_footer(text=f"Faction {FACTION_ID} • Torn Bounty Tracker")
        return embed

    async def create_stats_embed(self) -> discord.Embed:
        """Create statistics embed"""
        embed = discord.Embed(
            title="📊 Bounty Monitor Statistics",
            color=0x0099FF,
            timestamp=datetime.now(timezone.utc)
        )
        
        # Monitor stats
        embed.add_field(
            name="🔍 Monitor Status",
            value=f"{'🟢 Running' if self.is_monitoring else '🔴 Stopped'}",
            inline=True
        )
        
        embed.add_field(
            name="⏱️ Check Interval",
            value=f"{self.check_interval // 60}m {self.check_interval % 60}s",
            inline=True
        )
        
        if self.last_check:
            time_since = datetime.now(timezone.utc) - self.last_check
            embed.add_field(
                name="🕐 Last Check",
                value=f"{int(time_since.total_seconds() // 60)}m ago",
                inline=True
            )
        
        # Cache stats  
        embed.add_field(
            name="💾 Cache Size",
            value=f"{len(self.known_bounty_keys):,} entries",
            inline=True
        )
        
        embed.add_field(
            name="🎯 Total Found",
            value=f"{self.total_bounties_found:,} bounties",
            inline=True
        )
        
        embed.add_field(
            name="🔄 Total Checks",
            value=f"{self.total_checks_performed:,} checks",
            inline=True
        )
        
        # API stats if available
        if self.api_client:
            api_stats = self.api_client.stats
            embed.add_field(
                name="🌐 API Requests",
                value=f"{api_stats['requests_made']:,} total\n{api_stats['requests_per_minute']:.1f}/min avg",
                inline=False
            )
        
        embed.set_footer(text="Torn Bounty Bot")
        return embed

    async def check_bounties(self, test_count: int = 0) -> List[BountyInfo]:
        """Check for new bounties on faction members"""
        new_bounties = []
        
        if test_count > 0:
            # Generate test bounties
            for i in range(1, test_count + 1):
                test_bounty = BountyInfo(
                    target_id=999999 + i,
                    target_name=f"TestPlayer{i}",
                    reward=1000 * i,
                    quantity=1,
                    lister_id=None,
                    lister_name="Tester",
                    is_anonymous=False,
                    reason=f"Test bounty #{i}",
                    posted_time=datetime.now(timezone.utc)
                )
                
                if test_bounty.unique_key not in self.known_bounty_keys:
                    new_bounties.append(test_bounty)
                    self.known_bounty_keys.add(test_bounty.unique_key)
        else:
            # Real bounty check
            async with TornAPIClient(TORN_API_KEY) as api_client:
                self.api_client = api_client
                
                # Get faction members
                members = await api_client.get_faction_members()
                if not members:
                    logger.warning("No faction members found")
                    return []
                
                logger.info(f"Checking bounties for {len(members)} members")
                
                # Check each member for bounties (with progress logging for large factions)
                member_count = len(members)
                processed_count = 0
                
                for member_id, member in members.items():
                    try:
                        user_bounties = await api_client.get_user_bounties(member_id)
                        
                        for bounty in user_bounties:
                            bounty.target_name = member.name
                            
                            if bounty.unique_key not in self.known_bounty_keys:
                                new_bounties.append(bounty)
                                self.known_bounty_keys.add(bounty.unique_key)
                        
                        processed_count += 1
                        
                        # Log progress for large factions
                        if member_count > 50 and processed_count % 10 == 0:
                            logger.info(f"Processed {processed_count}/{member_count} members")
                                
                    except Exception as e:
                        logger.error(f"Error checking bounties for {member.name} ({member_id}): {e}")
                        continue
        
        # Update statistics
        self.total_checks_performed += 1
        if new_bounties:
            self.total_bounties_found += len(new_bounties)
            
        self.last_check = datetime.now(timezone.utc)
        self._save_cache()
        self._clean_old_cache_entries()
        
        return new_bounties

    async def _monitor_loop(self, channel_id: int) -> None:
        """Main monitoring loop"""
        logger.info(f"Bounty monitoring started for channel {channel_id}")
        
        while self.is_monitoring:
            try:
                channel = self.client.get_channel(channel_id)
                if not channel:
                    logger.error(f"Could not find channel {channel_id}")
                    await asyncio.sleep(60)
                    continue
                
                # Check for new bounties
                new_bounties = await self.check_bounties()
                
                if new_bounties or self.total_checks_performed % 12 == 1:  # Show "no bounties" every hour
                    embed = await self.create_bounty_embed(new_bounties)
                    await channel.send(embed=embed)
                    
                    if new_bounties:
                        logger.info(f"Posted {len(new_bounties)} new bounties to channel")
                
                await asyncio.sleep(self.check_interval)
                
            except Exception as e:
                logger.error(f"Error in bounty monitor loop: {e}", exc_info=True)
                await asyncio.sleep(60)  # Shorter sleep on error
        
        logger.info("Bounty monitoring stopped")

    async def start_monitoring(self, channel_id: int, interval: int = 300) -> bool:
        """Start bounty monitoring"""
        if self.is_monitoring:
            logger.info("Bounty monitoring already running")
            return True
            
        try:
            self.check_interval = interval
            self.is_monitoring = True
            self.monitor_task = asyncio.create_task(self._monitor_loop(channel_id))
            return True
        except Exception as e:
            logger.error(f"Failed to start bounty monitoring: {e}")
            self.is_monitoring = False
            return False

    async def stop_monitoring(self) -> None:
        """Stop bounty monitoring"""
        self.is_monitoring = False
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
        self._save_cache()
        logger.info("Bounty monitoring stopped")


# Global monitor instance
bounty_monitor: Optional[BountyMonitor] = None


async def start(client: discord.Client, channel_id: int, interval: int = 300) -> bool:
    """Initialize and start bounty monitoring"""
    global bounty_monitor
    
    try:
        if not all([TORN_API_KEY, FACTION_ID]):
            logger.error("Missing required configuration for bounty monitoring")
            return False

        if bounty_monitor and bounty_monitor.is_monitoring:
            logger.info("Bounty monitoring already running")
            return True

        await client.wait_until_ready()
        
        bounty_monitor = BountyMonitor(client)
        return await bounty_monitor.start_monitoring(channel_id, interval)
        
    except ConfigError as e:
        logger.error(f"Configuration error: {e}")
        return False
    except Exception as e:
        logger.error(f"Failed to start bounty monitoring: {e}")
        return False


async def stop() -> None:
    """Stop bounty monitoring"""
    global bounty_monitor
    if bounty_monitor:
        await bounty_monitor.stop_monitoring()


async def bounties(channel: discord.TextChannel, test_count: int = 0) -> None:
    """Manual bounty check command"""
    if not bounty_monitor:
        # Create temporary monitor for manual check
        try:
            temp_monitor = BountyMonitor(channel.guild.me)
        except Exception as e:
            logger.error(f"Failed to create temporary monitor: {e}")
            error_embed = discord.Embed(
                title="❌ Configuration Error",
                description="Unable to initialize bounty monitor. Check configuration.",
                color=0xFF0000
            )
            await channel.send(embed=error_embed)
            return
        
        # Send status message
        status_embed = discord.Embed(
            title="🔍 Bounty Check",
            description="Checking for bounties on faction members...",
            color=0x0099FF
        )
        status_msg = await channel.send(embed=status_embed)
        
        try:
            new_bounties = await temp_monitor.check_bounties(test_count)
            embed = await temp_monitor.create_bounty_embed(new_bounties, is_test=test_count > 0)
            await status_msg.edit(embed=embed)
            
        except Exception as e:
            logger.error(f"Error in manual bounty check: {e}")
            error_embed = discord.Embed(
                title="❌ Error",
                description=f"An error occurred while checking bounties: {str(e)}",
                color=0xFF0000
            )
            await status_msg.edit(embed=error_embed)
    else:
        # Use existing monitor
        status_embed = discord.Embed(
            title="🔍 Bounty Check",
            description="Checking for bounties on faction members...",
            color=0x0099FF
        )
        status_msg = await channel.send(embed=status_embed)
        
        try:
            new_bounties = await bounty_monitor.check_bounties(test_count)
            embed = await bounty_monitor.create_bounty_embed(new_bounties, is_test=test_count > 0)
            await status_msg.edit(embed=embed)
            
        except Exception as e:
            logger.error(f"Error in manual bounty check: {e}")
            error_embed = discord.Embed(
                title="❌ Error", 
                description=f"An error occurred while checking bounties: {str(e)}",
                color=0xFF0000
            )
            await status_msg.edit(embed=error_embed)


async def bounty_stats(channel: discord.TextChannel) -> None:
    """Show bounty monitoring statistics"""
    if not bounty_monitor:
        embed = discord.Embed(
            title="❌ Bounty Monitor",
            description="Bounty monitoring is not running",
            color=0xFF0000
        )
        await channel.send(embed=embed)
        return
    
    embed = await bounty_monitor.create_stats_embed()
    await channel.send(embed=embed)