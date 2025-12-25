"""
Feature Store - مخزن الميزات
============================

Feature store for managing ML features with online and offline storage.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

logger = logging.getLogger(__name__)


class FeatureType(str, Enum):
    """Feature data types."""
    INT = "int"
    FLOAT = "float"
    STRING = "string"
    BOOL = "bool"
    ARRAY = "array"
    EMBEDDING = "embedding"
    TIMESTAMP = "timestamp"


class FeatureSource(str, Enum):
    """Feature data sources."""
    BATCH = "batch"
    STREAMING = "streaming"
    REQUEST = "request"
    DERIVED = "derived"


@dataclass
class Feature:
    """Represents a single feature."""
    name: str
    dtype: FeatureType
    description: str = ""

    # Feature metadata
    source: FeatureSource = FeatureSource.BATCH
    entity: str = ""  # e.g., "user", "item"
    tags: List[str] = field(default_factory=list)

    # Validation
    nullable: bool = False
    default_value: Any = None

    # Statistics
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    mean: Optional[float] = None
    stddev: Optional[float] = None

    # Freshness
    max_age_seconds: Optional[int] = None

    def validate(self, value: Any) -> bool:
        """Validate a feature value."""
        if value is None:
            return self.nullable

        if self.dtype == FeatureType.INT:
            return isinstance(value, int)
        elif self.dtype == FeatureType.FLOAT:
            return isinstance(value, (int, float))
        elif self.dtype == FeatureType.STRING:
            return isinstance(value, str)
        elif self.dtype == FeatureType.BOOL:
            return isinstance(value, bool)
        elif self.dtype == FeatureType.ARRAY:
            return isinstance(value, (list, tuple))
        elif self.dtype == FeatureType.EMBEDDING:
            return isinstance(value, (list, tuple)) and all(isinstance(v, (int, float)) for v in value)

        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "dtype": self.dtype.value,
            "description": self.description,
            "source": self.source.value,
            "entity": self.entity,
            "tags": self.tags,
            "nullable": self.nullable,
            "default_value": self.default_value,
        }


@dataclass
class FeatureGroup:
    """A group of related features."""
    name: str
    entity: str
    features: List[Feature]
    description: str = ""

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    version: int = 1
    tags: List[str] = field(default_factory=list)

    # Source configuration
    source_config: Dict[str, Any] = field(default_factory=dict)

    def get_feature(self, name: str) -> Optional[Feature]:
        """Get a feature by name."""
        for feature in self.features:
            if feature.name == name:
                return feature
        return None

    def feature_names(self) -> List[str]:
        """Get all feature names."""
        return [f.name for f in self.features]


@dataclass
class FeatureSet:
    """A set of features for model training/inference."""
    name: str
    feature_groups: List[str]  # References to feature groups
    features: List[str]  # feature_group:feature_name format
    description: str = ""

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    version: int = 1


@dataclass
class FeatureVector:
    """A vector of feature values for an entity."""
    entity_id: str
    entity_type: str
    features: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def get(self, feature_name: str, default: Any = None) -> Any:
        """Get a feature value."""
        return self.features.get(feature_name, default)

    def to_list(self, feature_names: List[str]) -> List[Any]:
        """Convert to ordered list."""
        return [self.features.get(name) for name in feature_names]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "features": self.features,
            "timestamp": self.timestamp.isoformat(),
        }


class FeatureStoreBackend(ABC):
    """Abstract backend for feature storage."""

    @abstractmethod
    async def get_features(
        self,
        entity_type: str,
        entity_ids: List[str],
        feature_names: List[str],
    ) -> Dict[str, FeatureVector]:
        """Get features for entities."""
        pass

    @abstractmethod
    async def set_features(
        self,
        entity_type: str,
        entity_id: str,
        features: Dict[str, Any],
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Set features for an entity."""
        pass

    @abstractmethod
    async def delete_features(
        self,
        entity_type: str,
        entity_id: str,
    ) -> None:
        """Delete features for an entity."""
        pass


class OnlineFeatureStore(FeatureStoreBackend):
    """
    Online feature store for low-latency feature serving.

    Uses in-memory storage with optional Redis backend.
    """

    def __init__(self, redis_client: Any = None, ttl_seconds: int = 3600):
        self._redis = redis_client
        self._ttl = ttl_seconds
        self._cache: Dict[str, FeatureVector] = {}
        self._lock = asyncio.Lock()

    def _make_key(self, entity_type: str, entity_id: str) -> str:
        """Create storage key."""
        return f"features:{entity_type}:{entity_id}"

    async def get_features(
        self,
        entity_type: str,
        entity_ids: List[str],
        feature_names: List[str],
    ) -> Dict[str, FeatureVector]:
        """Get features for entities."""
        results = {}

        for entity_id in entity_ids:
            key = self._make_key(entity_type, entity_id)

            # Try cache first
            if key in self._cache:
                fv = self._cache[key]
                # Filter to requested features
                filtered = {k: v for k, v in fv.features.items() if k in feature_names}
                results[entity_id] = FeatureVector(
                    entity_id=entity_id,
                    entity_type=entity_type,
                    features=filtered,
                    timestamp=fv.timestamp,
                )
                continue

            # Try Redis
            if self._redis:
                try:
                    data = await self._redis.hgetall(key)
                    if data:
                        features = {k: json.loads(v) for k, v in data.items() if k in feature_names}
                        results[entity_id] = FeatureVector(
                            entity_id=entity_id,
                            entity_type=entity_type,
                            features=features,
                        )
                except Exception as e:
                    logger.error(f"Redis get error: {e}")

        return results

    async def set_features(
        self,
        entity_type: str,
        entity_id: str,
        features: Dict[str, Any],
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Set features for an entity."""
        key = self._make_key(entity_type, entity_id)
        ts = timestamp or datetime.utcnow()

        # Update cache
        async with self._lock:
            self._cache[key] = FeatureVector(
                entity_id=entity_id,
                entity_type=entity_type,
                features=features,
                timestamp=ts,
            )

        # Update Redis
        if self._redis:
            try:
                pipe = self._redis.pipeline()
                for k, v in features.items():
                    pipe.hset(key, k, json.dumps(v))
                pipe.expire(key, self._ttl)
                await pipe.execute()
            except Exception as e:
                logger.error(f"Redis set error: {e}")

    async def delete_features(
        self,
        entity_type: str,
        entity_id: str,
    ) -> None:
        """Delete features for an entity."""
        key = self._make_key(entity_type, entity_id)

        async with self._lock:
            self._cache.pop(key, None)

        if self._redis:
            try:
                await self._redis.delete(key)
            except Exception as e:
                logger.error(f"Redis delete error: {e}")


class OfflineFeatureStore(FeatureStoreBackend):
    """
    Offline feature store for historical features and training data.

    Uses file-based or database storage.
    """

    def __init__(
        self,
        storage_path: str = "./feature_store",
        database_url: Optional[str] = None,
    ):
        self._storage_path = Path(storage_path)
        self._storage_path.mkdir(parents=True, exist_ok=True)
        self._db_url = database_url
        self._conn = None

    def _get_entity_path(self, entity_type: str, entity_id: str) -> Path:
        """Get file path for entity features."""
        entity_dir = self._storage_path / entity_type
        entity_dir.mkdir(exist_ok=True)
        return entity_dir / f"{entity_id}.json"

    async def get_features(
        self,
        entity_type: str,
        entity_ids: List[str],
        feature_names: List[str],
    ) -> Dict[str, FeatureVector]:
        """Get features for entities."""
        results = {}

        for entity_id in entity_ids:
            path = self._get_entity_path(entity_type, entity_id)

            if path.exists():
                with open(path, "r") as f:
                    data = json.load(f)

                features = {k: v for k, v in data.get("features", {}).items() if k in feature_names}
                results[entity_id] = FeatureVector(
                    entity_id=entity_id,
                    entity_type=entity_type,
                    features=features,
                    timestamp=datetime.fromisoformat(data.get("timestamp", datetime.utcnow().isoformat())),
                )

        return results

    async def set_features(
        self,
        entity_type: str,
        entity_id: str,
        features: Dict[str, Any],
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Set features for an entity."""
        path = self._get_entity_path(entity_type, entity_id)
        ts = timestamp or datetime.utcnow()

        data = {
            "entity_id": entity_id,
            "entity_type": entity_type,
            "features": features,
            "timestamp": ts.isoformat(),
        }

        with open(path, "w") as f:
            json.dump(data, f)

    async def delete_features(
        self,
        entity_type: str,
        entity_id: str,
    ) -> None:
        """Delete features for an entity."""
        path = self._get_entity_path(entity_type, entity_id)
        if path.exists():
            path.unlink()

    async def get_historical_features(
        self,
        entity_type: str,
        entity_ids: List[str],
        feature_names: List[str],
        start_time: datetime,
        end_time: datetime,
    ) -> List[FeatureVector]:
        """Get historical features within a time range."""
        # For file-based storage, this is simplified
        # In production, use a time-series database
        results = await self.get_features(entity_type, entity_ids, feature_names)
        return [
            fv for fv in results.values()
            if start_time <= fv.timestamp <= end_time
        ]

    async def materialize_features(
        self,
        feature_group: FeatureGroup,
        entity_ids: Optional[List[str]] = None,
    ) -> int:
        """Materialize features from source to offline store."""
        # This would connect to source systems (databases, streams)
        # and write features to the offline store
        logger.info(f"Materializing features for group: {feature_group.name}")
        return 0


class FeatureStore:
    """
    Feature Store - مخزن الميزات.

    Unified interface for managing ML features with both online
    and offline storage.

    Example:
        store = FeatureStore()

        # Define a feature group
        user_features = FeatureGroup(
            name="user_features",
            entity="user",
            features=[
                Feature(name="age", dtype=FeatureType.INT),
                Feature(name="total_purchases", dtype=FeatureType.FLOAT),
                Feature(name="embedding", dtype=FeatureType.EMBEDDING),
            ]
        )
        store.register_feature_group(user_features)

        # Set features
        await store.set_features(
            entity_type="user",
            entity_id="user-123",
            features={"age": 25, "total_purchases": 1500.0}
        )

        # Get features
        vectors = await store.get_online_features(
            entity_type="user",
            entity_ids=["user-123"],
            feature_names=["age", "total_purchases"]
        )
    """

    def __init__(
        self,
        online_store: Optional[OnlineFeatureStore] = None,
        offline_store: Optional[OfflineFeatureStore] = None,
    ):
        self._online = online_store or OnlineFeatureStore()
        self._offline = offline_store or OfflineFeatureStore()
        self._feature_groups: Dict[str, FeatureGroup] = {}
        self._feature_sets: Dict[str, FeatureSet] = {}

    def register_feature_group(self, group: FeatureGroup) -> None:
        """Register a feature group."""
        self._feature_groups[group.name] = group
        logger.info(f"Registered feature group: {group.name}")

    def get_feature_group(self, name: str) -> Optional[FeatureGroup]:
        """Get a feature group by name."""
        return self._feature_groups.get(name)

    def list_feature_groups(self) -> List[str]:
        """List all feature group names."""
        return list(self._feature_groups.keys())

    def register_feature_set(self, feature_set: FeatureSet) -> None:
        """Register a feature set."""
        self._feature_sets[feature_set.name] = feature_set
        logger.info(f"Registered feature set: {feature_set.name}")

    def get_feature_set(self, name: str) -> Optional[FeatureSet]:
        """Get a feature set by name."""
        return self._feature_sets.get(name)

    async def get_online_features(
        self,
        entity_type: str,
        entity_ids: List[str],
        feature_names: List[str],
    ) -> Dict[str, FeatureVector]:
        """Get features from online store."""
        return await self._online.get_features(entity_type, entity_ids, feature_names)

    async def get_offline_features(
        self,
        entity_type: str,
        entity_ids: List[str],
        feature_names: List[str],
    ) -> Dict[str, FeatureVector]:
        """Get features from offline store."""
        return await self._offline.get_features(entity_type, entity_ids, feature_names)

    async def set_features(
        self,
        entity_type: str,
        entity_id: str,
        features: Dict[str, Any],
        online: bool = True,
        offline: bool = True,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Set features in stores."""
        if online:
            await self._online.set_features(entity_type, entity_id, features, timestamp)
        if offline:
            await self._offline.set_features(entity_type, entity_id, features, timestamp)

    async def delete_features(
        self,
        entity_type: str,
        entity_id: str,
        online: bool = True,
        offline: bool = True,
    ) -> None:
        """Delete features from stores."""
        if online:
            await self._online.delete_features(entity_type, entity_id)
        if offline:
            await self._offline.delete_features(entity_type, entity_id)

    async def get_training_data(
        self,
        feature_set_name: str,
        entity_type: str,
        entity_ids: List[str],
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Get training data from offline store."""
        feature_set = self._feature_sets.get(feature_set_name)
        if not feature_set:
            raise ValueError(f"Feature set not found: {feature_set_name}")

        # Parse feature names
        feature_names = []
        for f in feature_set.features:
            if ":" in f:
                _, name = f.split(":", 1)
                feature_names.append(name)
            else:
                feature_names.append(f)

        vectors = await self._offline.get_features(entity_type, entity_ids, feature_names)
        return [fv.to_dict() for fv in vectors.values()]

    async def materialize(
        self,
        feature_group_name: str,
        entity_ids: Optional[List[str]] = None,
    ) -> int:
        """Materialize features from source to stores."""
        group = self._feature_groups.get(feature_group_name)
        if not group:
            raise ValueError(f"Feature group not found: {feature_group_name}")

        return await self._offline.materialize_features(group, entity_ids)

    def compute_feature_hash(self, feature_names: List[str]) -> str:
        """Compute hash of feature names for versioning."""
        sorted_names = sorted(feature_names)
        return hashlib.md5(json.dumps(sorted_names).encode()).hexdigest()[:12]

    def validate_features(
        self,
        feature_group_name: str,
        features: Dict[str, Any],
    ) -> Tuple[bool, List[str]]:
        """Validate features against schema."""
        group = self._feature_groups.get(feature_group_name)
        if not group:
            return False, [f"Feature group not found: {feature_group_name}"]

        errors = []
        for name, value in features.items():
            feature = group.get_feature(name)
            if not feature:
                errors.append(f"Unknown feature: {name}")
                continue

            if not feature.validate(value):
                errors.append(f"Invalid value for {name}: expected {feature.dtype.value}")

        return len(errors) == 0, errors
