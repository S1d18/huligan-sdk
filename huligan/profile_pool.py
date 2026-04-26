"""
Profile Pool Manager

For 1000+ accounts: Use pool of N pre-generated profiles with rotation.
Much more efficient than 1000 separate browser launches.
"""
import random
import logging
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass

from .fingerprint import FingerprintGenerator

logger = logging.getLogger(__name__)


@dataclass
class ProfilePoolConfig:
    """Profile pool configuration"""
    pool_size: int = 100  # Number of pre-generated profiles
    pool_dir: Path = Path("profiles_pool")
    platforms: List[str] = None  # ["Win32", "MacIntel", "Linux x86_64"]

    def __post_init__(self):
        if self.platforms is None:
            self.platforms = ["Win32"]  # Default to Windows only


class ProfilePool:
    """
    Manages pool of pre-generated fingerprint profiles.

    Usage:
        # Create pool
        pool = ProfilePool(ProfilePoolConfig(pool_size=100))
        pool.generate_pool()

        # Get random profile
        profile_path = pool.get_random()

        # Get profile by index (for round-robin)
        profile_path = pool.get_by_index(account_id % 100)
    """

    def __init__(self, config: ProfilePoolConfig):
        self.config = config
        self.profiles: List[Path] = []
        self._current_index = 0

    def generate_pool(self, force: bool = False):
        """
        Generate pool of unique profiles.

        Args:
            force: Regenerate even if pool exists
        """
        self.config.pool_dir.mkdir(parents=True, exist_ok=True)

        # Check if pool already exists
        existing = list(self.config.pool_dir.glob("profile_*.conf"))
        if existing and not force:
            logger.info(f"Using existing pool: {len(existing)} profiles in {self.config.pool_dir}")
            self.profiles = sorted(existing)
            return

        logger.info(f"Generating pool of {self.config.pool_size} unique profiles")

        generator = FingerprintGenerator()
        self.profiles = []

        for i in range(self.config.pool_size):
            platform = random.choice(self.config.platforms)
            profile_path = self.config.pool_dir / f"profile_{i:04d}_{platform}.conf"

            profile = generator.generate(platform=platform)
            profile_path.write_text(profile.to_conf(), encoding='utf-8')
            self.profiles.append(profile_path)

            if (i + 1) % 10 == 0:
                logger.info(f"Generated {i + 1}/{self.config.pool_size} profiles")

        logger.info(f"Pool generation complete: {len(self.profiles)} profiles")

    def get_random(self) -> Path:
        """Get random profile from pool"""
        if not self.profiles:
            raise RuntimeError("Profile pool is empty. Call generate_pool() first.")
        return random.choice(self.profiles)

    def get_by_index(self, index: int) -> Path:
        """
        Get profile by index (for round-robin distribution).

        Args:
            index: Index (will be wrapped with modulo)

        Returns:
            Path to profile
        """
        if not self.profiles:
            raise RuntimeError("Profile pool is empty. Call generate_pool() first.")
        return self.profiles[index % len(self.profiles)]

    def get_next(self) -> Path:
        """Get next profile in round-robin order"""
        profile = self.get_by_index(self._current_index)
        self._current_index += 1
        return profile

    def __len__(self):
        return len(self.profiles)
