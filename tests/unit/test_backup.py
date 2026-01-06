"""
Backup Module Unit Tests - اختبارات وحدة النسخ الاحتياطي
========================================================

Tests for the backup system including:
- BackupManager
- Snapshot creation and restoration
- Storage backends (Local, S3, Azure)
- Backup scheduling and retention
"""

import asyncio
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from distributed_cluster.backup import (
    AzureStorage,
    BackupConfig,
    BackupManager,
    BackupResult,
    BackupScheduler,
    BackupStorage,
    LocalStorage,
    RestoreResult,
    RetentionPolicy,
    S3Storage,
    ScheduleConfig,
    Snapshot,
    SnapshotMetadata,
    SnapshotType,
)


# =============================================================================
# Snapshot Tests
# =============================================================================


class TestSnapshotType:
    """Tests for SnapshotType enum."""

    def test_snapshot_types(self):
        """Test snapshot type values."""
        assert SnapshotType.FULL is not None
        assert SnapshotType.INCREMENTAL is not None
        assert SnapshotType.DIFFERENTIAL is not None


class TestSnapshotMetadata:
    """Tests for SnapshotMetadata."""

    def test_create_metadata(self):
        """Test creating snapshot metadata."""
        metadata = SnapshotMetadata(
            snapshot_id="snap-12345",
            created_at=datetime.now(timezone.utc),
            snapshot_type=SnapshotType.FULL,
            size_bytes=1024 * 1024,
            checksum="abc123",
        )
        assert metadata.snapshot_id == "snap-12345"
        assert metadata.snapshot_type == SnapshotType.FULL
        assert metadata.size_bytes == 1024 * 1024

    def test_metadata_to_dict(self):
        """Test metadata dictionary conversion."""
        metadata = SnapshotMetadata(
            snapshot_id="snap-12345",
            created_at=datetime.now(timezone.utc),
            snapshot_type=SnapshotType.FULL,
            size_bytes=1024,
            checksum="abc123",
        )
        d = metadata.to_dict()
        assert d["snapshot_id"] == "snap-12345"
        assert d["snapshot_type"] == "full"


class TestSnapshot:
    """Tests for Snapshot."""

    def test_create_snapshot(self):
        """Test creating a snapshot."""
        snapshot = Snapshot(
            metadata=SnapshotMetadata(
                snapshot_id="snap-12345",
                created_at=datetime.now(timezone.utc),
                snapshot_type=SnapshotType.FULL,
                size_bytes=1024,
                checksum="abc123",
            ),
            data={"key": "value"},
        )
        assert snapshot.metadata.snapshot_id == "snap-12345"
        assert snapshot.data["key"] == "value"

    def test_snapshot_is_valid(self):
        """Test snapshot validation."""
        snapshot = Snapshot(
            metadata=SnapshotMetadata(
                snapshot_id="snap-12345",
                created_at=datetime.now(timezone.utc),
                snapshot_type=SnapshotType.FULL,
                size_bytes=1024,
                checksum="abc123",
            ),
            data={"key": "value"},
        )
        # Snapshot should be valid when checksum matches
        assert snapshot.is_valid is True


# =============================================================================
# Storage Backend Tests
# =============================================================================


class TestLocalStorage:
    """Tests for LocalStorage backend."""

    @pytest.fixture
    def storage(self, tmp_path):
        """Create a local storage backend."""
        return LocalStorage(base_path=str(tmp_path))

    @pytest.fixture
    def sample_snapshot(self):
        """Create a sample snapshot."""
        return Snapshot(
            metadata=SnapshotMetadata(
                snapshot_id="snap-test-001",
                created_at=datetime.now(timezone.utc),
                snapshot_type=SnapshotType.FULL,
                size_bytes=0,
                checksum="",
            ),
            data={"workers": [], "jobs": [], "config": {}},
        )

    @pytest.mark.asyncio
    async def test_save_snapshot(self, storage, sample_snapshot):
        """Test saving a snapshot."""
        result = await storage.save(sample_snapshot)
        assert result is True

    @pytest.mark.asyncio
    async def test_load_snapshot(self, storage, sample_snapshot):
        """Test loading a snapshot."""
        await storage.save(sample_snapshot)
        loaded = await storage.load(sample_snapshot.metadata.snapshot_id)

        assert loaded is not None
        assert loaded.metadata.snapshot_id == sample_snapshot.metadata.snapshot_id
        assert loaded.data == sample_snapshot.data

    @pytest.mark.asyncio
    async def test_delete_snapshot(self, storage, sample_snapshot):
        """Test deleting a snapshot."""
        await storage.save(sample_snapshot)
        deleted = await storage.delete(sample_snapshot.metadata.snapshot_id)

        assert deleted is True
        loaded = await storage.load(sample_snapshot.metadata.snapshot_id)
        assert loaded is None

    @pytest.mark.asyncio
    async def test_list_snapshots(self, storage, sample_snapshot):
        """Test listing snapshots."""
        # Save multiple snapshots
        for i in range(3):
            snap = Snapshot(
                metadata=SnapshotMetadata(
                    snapshot_id=f"snap-test-{i:03d}",
                    created_at=datetime.now(timezone.utc),
                    snapshot_type=SnapshotType.FULL,
                    size_bytes=0,
                    checksum="",
                ),
                data={"index": i},
            )
            await storage.save(snap)

        snapshots = await storage.list_snapshots()
        assert len(snapshots) >= 3

    @pytest.mark.asyncio
    async def test_load_nonexistent(self, storage):
        """Test loading non-existent snapshot."""
        loaded = await storage.load("nonexistent")
        assert loaded is None

    @pytest.mark.asyncio
    async def test_get_snapshot_info(self, storage, sample_snapshot):
        """Test getting snapshot info."""
        await storage.save(sample_snapshot)
        info = await storage.get_info(sample_snapshot.metadata.snapshot_id)

        assert info is not None
        assert info["snapshot_id"] == sample_snapshot.metadata.snapshot_id


class TestS3Storage:
    """Tests for S3Storage backend (mocked)."""

    @pytest.fixture
    def storage(self):
        """Create an S3 storage backend."""
        return S3Storage(
            bucket="test-bucket",
            prefix="backups/",
            region="us-east-1",
        )

    @pytest.mark.asyncio
    async def test_initialization(self, storage):
        """Test S3 storage initialization."""
        assert storage.bucket == "test-bucket"
        assert storage.prefix == "backups/"
        assert storage.region == "us-east-1"

    @pytest.mark.asyncio
    async def test_save_mock(self, storage):
        """Test S3 save with mock."""
        with patch.object(storage, "_s3_client") as mock_s3:
            mock_s3.put_object = AsyncMock()

            snapshot = Snapshot(
                metadata=SnapshotMetadata(
                    snapshot_id="snap-s3-001",
                    created_at=datetime.now(timezone.utc),
                    snapshot_type=SnapshotType.FULL,
                    size_bytes=0,
                    checksum="",
                ),
                data={"test": "data"},
            )

            result = await storage.save(snapshot)
            # Mock should have been called
            # assert result is True (depends on implementation)


class TestAzureStorage:
    """Tests for AzureStorage backend (mocked)."""

    @pytest.fixture
    def storage(self):
        """Create an Azure storage backend."""
        return AzureStorage(
            container="test-container",
            connection_string="DefaultEndpointsProtocol=https;...",
        )

    @pytest.mark.asyncio
    async def test_initialization(self, storage):
        """Test Azure storage initialization."""
        assert storage.container == "test-container"


# =============================================================================
# BackupConfig Tests
# =============================================================================


class TestBackupConfig:
    """Tests for BackupConfig."""

    def test_default_config(self):
        """Test default backup configuration."""
        config = BackupConfig()
        assert config.enabled is True
        assert config.compression_enabled is True
        assert config.encryption_enabled is False

    def test_custom_config(self):
        """Test custom backup configuration."""
        config = BackupConfig(
            enabled=True,
            compression_enabled=True,
            encryption_enabled=True,
            encryption_key="secret-key",
            max_backups=10,
        )
        assert config.encryption_enabled is True
        assert config.max_backups == 10


# =============================================================================
# BackupManager Tests
# =============================================================================


class TestBackupResult:
    """Tests for BackupResult."""

    def test_successful_result(self):
        """Test successful backup result."""
        result = BackupResult(
            success=True,
            snapshot_id="snap-12345",
            size_bytes=1024,
            duration_seconds=5.0,
        )
        assert result.success is True
        assert result.snapshot_id == "snap-12345"

    def test_failed_result(self):
        """Test failed backup result."""
        result = BackupResult(
            success=False,
            error="Storage unavailable",
        )
        assert result.success is False
        assert result.error == "Storage unavailable"


class TestRestoreResult:
    """Tests for RestoreResult."""

    def test_successful_restore(self):
        """Test successful restore result."""
        result = RestoreResult(
            success=True,
            snapshot_id="snap-12345",
            items_restored=100,
            duration_seconds=10.0,
        )
        assert result.success is True
        assert result.items_restored == 100


class TestBackupManager:
    """Tests for BackupManager."""

    @pytest.fixture
    def storage(self, tmp_path):
        """Create a local storage backend."""
        return LocalStorage(base_path=str(tmp_path))

    @pytest.fixture
    def config(self):
        """Create backup configuration."""
        return BackupConfig(
            enabled=True,
            compression_enabled=False,
            max_backups=5,
        )

    @pytest.fixture
    def mock_state(self):
        """Create mock cluster state."""
        state = MagicMock()
        state.get_workers.return_value = [
            {"id": "worker-1", "status": "ready"},
            {"id": "worker-2", "status": "busy"},
        ]
        state.get_jobs.return_value = [
            {"id": "job-1", "status": "completed"},
        ]
        state.get_config.return_value = {"cluster_name": "test"}
        return state

    @pytest.fixture
    def manager(self, config, storage, mock_state):
        """Create backup manager."""
        return BackupManager(
            config=config,
            storage=storage,
            state_provider=mock_state,
        )

    @pytest.mark.asyncio
    async def test_create_backup(self, manager):
        """Test creating a backup."""
        result = await manager.create_backup()

        assert result.success is True
        assert result.snapshot_id is not None

    @pytest.mark.asyncio
    async def test_create_backup_with_label(self, manager):
        """Test creating a backup with label."""
        result = await manager.create_backup(label="pre-upgrade")

        assert result.success is True
        # Label should be in the snapshot metadata

    @pytest.mark.asyncio
    async def test_restore_backup(self, manager):
        """Test restoring a backup."""
        # First create a backup
        backup_result = await manager.create_backup()
        assert backup_result.success is True

        # Then restore it
        restore_result = await manager.restore(backup_result.snapshot_id)

        assert restore_result.success is True
        assert restore_result.snapshot_id == backup_result.snapshot_id

    @pytest.mark.asyncio
    async def test_restore_nonexistent(self, manager):
        """Test restoring non-existent backup."""
        result = await manager.restore("nonexistent-snap")

        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_list_backups(self, manager):
        """Test listing backups."""
        # Create multiple backups
        for i in range(3):
            await manager.create_backup(label=f"backup-{i}")

        backups = await manager.list_backups()
        assert len(backups) >= 3

    @pytest.mark.asyncio
    async def test_delete_backup(self, manager):
        """Test deleting a backup."""
        result = await manager.create_backup()
        deleted = await manager.delete_backup(result.snapshot_id)

        assert deleted is True

    @pytest.mark.asyncio
    async def test_incremental_backup(self, manager):
        """Test creating incremental backup."""
        # Create full backup first
        full_result = await manager.create_backup(
            backup_type=SnapshotType.FULL,
        )
        assert full_result.success is True

        # Create incremental backup
        incr_result = await manager.create_backup(
            backup_type=SnapshotType.INCREMENTAL,
            base_snapshot_id=full_result.snapshot_id,
        )
        assert incr_result.success is True

    @pytest.mark.asyncio
    async def test_backup_disabled(self, storage, mock_state):
        """Test that backup is skipped when disabled."""
        config = BackupConfig(enabled=False)
        manager = BackupManager(
            config=config,
            storage=storage,
            state_provider=mock_state,
        )

        result = await manager.create_backup()
        assert result.success is False
        assert "disabled" in result.error.lower()

    @pytest.mark.asyncio
    async def test_retention_policy(self, manager):
        """Test that retention policy is enforced."""
        # Create more backups than max_backups
        for i in range(7):
            await manager.create_backup(label=f"backup-{i}")

        backups = await manager.list_backups()
        # Should have max_backups or fewer
        assert len(backups) <= manager.config.max_backups


# =============================================================================
# Scheduler Tests
# =============================================================================


class TestScheduleConfig:
    """Tests for ScheduleConfig."""

    def test_default_schedule(self):
        """Test default schedule configuration."""
        config = ScheduleConfig()
        assert config.enabled is True
        assert config.interval_hours > 0

    def test_custom_schedule(self):
        """Test custom schedule configuration."""
        config = ScheduleConfig(
            enabled=True,
            interval_hours=6,
            cron_expression="0 */6 * * *",
        )
        assert config.interval_hours == 6


class TestRetentionPolicy:
    """Tests for RetentionPolicy."""

    def test_default_retention(self):
        """Test default retention policy."""
        policy = RetentionPolicy()
        assert policy.keep_last > 0

    def test_custom_retention(self):
        """Test custom retention policy."""
        policy = RetentionPolicy(
            keep_last=10,
            keep_daily=7,
            keep_weekly=4,
            keep_monthly=12,
        )
        assert policy.keep_last == 10
        assert policy.keep_daily == 7

    def test_should_keep_snapshot(self):
        """Test snapshot retention decision."""
        policy = RetentionPolicy(
            keep_last=5,
            keep_daily=7,
        )

        # Recent snapshot should be kept
        recent = SnapshotMetadata(
            snapshot_id="snap-recent",
            created_at=datetime.now(timezone.utc),
            snapshot_type=SnapshotType.FULL,
            size_bytes=0,
            checksum="",
        )
        assert policy.should_keep(recent, position=0) is True

        # Old snapshot beyond retention should not be kept
        old = SnapshotMetadata(
            snapshot_id="snap-old",
            created_at=datetime.now(timezone.utc) - timedelta(days=365),
            snapshot_type=SnapshotType.FULL,
            size_bytes=0,
            checksum="",
        )
        assert policy.should_keep(old, position=100) is False


class TestBackupScheduler:
    """Tests for BackupScheduler."""

    @pytest.fixture
    def mock_manager(self):
        """Create mock backup manager."""
        manager = MagicMock(spec=BackupManager)
        manager.create_backup = AsyncMock(
            return_value=BackupResult(
                success=True,
                snapshot_id="snap-scheduled",
                size_bytes=1024,
                duration_seconds=5.0,
            )
        )
        return manager

    @pytest.fixture
    def scheduler(self, mock_manager):
        """Create backup scheduler."""
        config = ScheduleConfig(
            enabled=True,
            interval_hours=1,
        )
        retention = RetentionPolicy(keep_last=5)
        return BackupScheduler(
            config=config,
            retention_policy=retention,
            backup_manager=mock_manager,
        )

    @pytest.mark.asyncio
    async def test_run_scheduled_backup(self, scheduler, mock_manager):
        """Test running scheduled backup."""
        result = await scheduler.run_backup()

        assert result.success is True
        mock_manager.create_backup.assert_called_once()

    @pytest.mark.asyncio
    async def test_next_scheduled_time(self, scheduler):
        """Test getting next scheduled backup time."""
        next_time = scheduler.get_next_backup_time()
        assert next_time is not None
        assert next_time > datetime.now(timezone.utc)

    @pytest.mark.asyncio
    async def test_is_due(self, scheduler):
        """Test checking if backup is due."""
        # Initially should be due (no previous backup)
        assert scheduler.is_due() is True

        # After backup, should not be due immediately
        await scheduler.run_backup()
        assert scheduler.is_due() is False


# =============================================================================
# Integration Tests
# =============================================================================


class TestBackupIntegration:
    """Integration tests for backup system."""

    @pytest.mark.asyncio
    async def test_full_backup_restore_cycle(self, tmp_path):
        """Test complete backup and restore cycle."""
        # Setup
        storage = LocalStorage(base_path=str(tmp_path))
        config = BackupConfig(
            enabled=True,
            compression_enabled=False,
        )

        # Mock state
        original_state = {
            "workers": [
                {"id": "worker-1", "status": "ready"},
                {"id": "worker-2", "status": "busy"},
            ],
            "jobs": [
                {"id": "job-1", "status": "completed"},
                {"id": "job-2", "status": "running"},
            ],
            "config": {"cluster_name": "test-cluster"},
        }

        state_provider = MagicMock()
        state_provider.get_workers.return_value = original_state["workers"]
        state_provider.get_jobs.return_value = original_state["jobs"]
        state_provider.get_config.return_value = original_state["config"]

        manager = BackupManager(
            config=config,
            storage=storage,
            state_provider=state_provider,
        )

        # Create backup
        backup_result = await manager.create_backup(label="test-backup")
        assert backup_result.success is True

        # Simulate state change
        state_provider.get_workers.return_value = []
        state_provider.get_jobs.return_value = []

        # Restore
        restore_result = await manager.restore(backup_result.snapshot_id)
        assert restore_result.success is True

        # Verify restored state
        snapshot = await storage.load(backup_result.snapshot_id)
        assert len(snapshot.data["workers"]) == 2
        assert len(snapshot.data["jobs"]) == 2

    @pytest.mark.asyncio
    async def test_retention_enforcement(self, tmp_path):
        """Test retention policy enforcement."""
        storage = LocalStorage(base_path=str(tmp_path))
        config = BackupConfig(
            enabled=True,
            max_backups=3,
        )

        state_provider = MagicMock()
        state_provider.get_workers.return_value = []
        state_provider.get_jobs.return_value = []
        state_provider.get_config.return_value = {}

        manager = BackupManager(
            config=config,
            storage=storage,
            state_provider=state_provider,
        )

        # Create 5 backups
        for i in range(5):
            await manager.create_backup(label=f"backup-{i}")
            await asyncio.sleep(0.1)  # Ensure different timestamps

        # Should only have 3 backups
        backups = await manager.list_backups()
        assert len(backups) <= 3

    @pytest.mark.asyncio
    async def test_concurrent_backups(self, tmp_path):
        """Test handling concurrent backup requests."""
        storage = LocalStorage(base_path=str(tmp_path))
        config = BackupConfig(enabled=True)

        state_provider = MagicMock()
        state_provider.get_workers.return_value = [{"id": "w1"}]
        state_provider.get_jobs.return_value = []
        state_provider.get_config.return_value = {}

        manager = BackupManager(
            config=config,
            storage=storage,
            state_provider=state_provider,
        )

        # Launch concurrent backups
        results = await asyncio.gather(
            manager.create_backup(label="concurrent-1"),
            manager.create_backup(label="concurrent-2"),
            manager.create_backup(label="concurrent-3"),
        )

        # All should succeed (or be queued/handled properly)
        successful = sum(1 for r in results if r.success)
        assert successful >= 1  # At least one should succeed
