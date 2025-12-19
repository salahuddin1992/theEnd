"""
Lease Management Integration Tests
==================================

Tests for job lease management and idempotency.
"""

import time
from datetime import datetime, timedelta

import pytest

from distributed_cluster.models.lease import (
    Lease,
    LeaseConfig,
    LeaseManager,
    LeaseState,
)


class TestLeaseBasic:
    """Basic lease tests."""

    def test_lease_creation(self):
        """Test lease can be created."""
        lease = Lease(
            lease_id="lease-1",
            job_id="job-1",
            worker_id="worker-1",
            state=LeaseState.ACTIVE,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(minutes=5),
        )

        assert lease.lease_id == "lease-1"
        assert lease.state == LeaseState.ACTIVE

    def test_lease_is_expired(self):
        """Test lease expiration check."""
        # Not expired
        active_lease = Lease(
            lease_id="lease-1",
            job_id="job-1",
            worker_id="worker-1",
            state=LeaseState.ACTIVE,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(minutes=5),
        )
        assert not active_lease.is_expired

        # Expired
        expired_lease = Lease(
            lease_id="lease-2",
            job_id="job-2",
            worker_id="worker-1",
            state=LeaseState.ACTIVE,
            created_at=datetime.utcnow() - timedelta(minutes=10),
            expires_at=datetime.utcnow() - timedelta(minutes=5),
        )
        assert expired_lease.is_expired


class TestLeaseManager:
    """Tests for LeaseManager."""

    @pytest.fixture
    def lease_manager(self) -> LeaseManager:
        """Create a lease manager for testing."""
        config = LeaseConfig(
            default_duration_seconds=60,
            max_duration_seconds=300,
            max_renewals=5,
        )
        return LeaseManager(config)

    def test_create_lease(self, lease_manager: LeaseManager):
        """Test creating a lease."""
        lease = lease_manager.create_lease(
            job_id="job-1",
            worker_id="worker-1",
            duration_seconds=60
        )

        assert lease is not None
        assert lease.job_id == "job-1"
        assert lease.worker_id == "worker-1"
        assert lease.state == LeaseState.ACTIVE
        assert lease.expires_at > datetime.utcnow()

    def test_create_duplicate_lease_fails(self, lease_manager: LeaseManager):
        """Test that creating duplicate lease for same job fails."""
        lease1 = lease_manager.create_lease("job-1", "worker-1", 60)
        assert lease1 is not None

        # Try to create another lease for same job
        lease2 = lease_manager.create_lease("job-1", "worker-2", 60)
        assert lease2 is None

    def test_get_lease(self, lease_manager: LeaseManager):
        """Test getting a lease."""
        created = lease_manager.create_lease("job-1", "worker-1", 60)

        retrieved = lease_manager.get_lease(created.lease_id)
        assert retrieved is not None
        assert retrieved.lease_id == created.lease_id

    def test_get_nonexistent_lease(self, lease_manager: LeaseManager):
        """Test getting non-existent lease."""
        retrieved = lease_manager.get_lease("nonexistent-lease")
        assert retrieved is None

    def test_renew_lease(self, lease_manager: LeaseManager):
        """Test renewing a lease."""
        lease = lease_manager.create_lease("job-1", "worker-1", 60)
        original_expires = lease.expires_at

        # Wait a bit then renew
        time.sleep(0.1)
        renewed = lease_manager.renew_lease(lease.lease_id, "worker-1")

        assert renewed is not None
        assert renewed.expires_at > original_expires
        assert renewed.renewal_count == 1

    def test_renew_lease_wrong_worker(self, lease_manager: LeaseManager):
        """Test that wrong worker cannot renew lease."""
        lease = lease_manager.create_lease("job-1", "worker-1", 60)

        # Try to renew with different worker
        renewed = lease_manager.renew_lease(lease.lease_id, "worker-2")
        assert renewed is None

    def test_renew_lease_max_renewals(self, lease_manager: LeaseManager):
        """Test max renewal limit."""
        config = LeaseConfig(
            default_duration_seconds=60,
            max_renewals=2,
        )
        manager = LeaseManager(config)

        lease = manager.create_lease("job-1", "worker-1", 60)

        # Renew twice (should succeed)
        manager.renew_lease(lease.lease_id, "worker-1")
        manager.renew_lease(lease.lease_id, "worker-1")

        # Third renewal should fail
        result = manager.renew_lease(lease.lease_id, "worker-1")
        assert result is None

    def test_release_lease(self, lease_manager: LeaseManager):
        """Test releasing a lease."""
        lease = lease_manager.create_lease("job-1", "worker-1", 60)

        released = lease_manager.release_lease(lease.lease_id, "worker-1")
        assert released is True

        # Check lease state
        retrieved = lease_manager.get_lease(lease.lease_id)
        assert retrieved.state == LeaseState.RELEASED

    def test_release_lease_idempotent(self, lease_manager: LeaseManager):
        """Test that releasing lease is idempotent."""
        lease = lease_manager.create_lease("job-1", "worker-1", 60)

        # Release multiple times
        result1 = lease_manager.release_lease(lease.lease_id, "worker-1")
        result2 = lease_manager.release_lease(lease.lease_id, "worker-1")
        result3 = lease_manager.release_lease(lease.lease_id, "worker-1")

        assert result1 is True
        assert result2 is True  # Idempotent - still returns True
        assert result3 is True

    def test_release_lease_wrong_worker(self, lease_manager: LeaseManager):
        """Test that wrong worker cannot release lease."""
        lease = lease_manager.create_lease("job-1", "worker-1", 60)

        released = lease_manager.release_lease(lease.lease_id, "worker-2")
        assert released is False

        # Lease should still be active
        retrieved = lease_manager.get_lease(lease.lease_id)
        assert retrieved.state == LeaseState.ACTIVE

    def test_revoke_lease(self, lease_manager: LeaseManager):
        """Test revoking a lease (admin operation)."""
        lease = lease_manager.create_lease("job-1", "worker-1", 60)

        revoked = lease_manager.revoke_lease(lease.lease_id)
        assert revoked is True

        retrieved = lease_manager.get_lease(lease.lease_id)
        assert retrieved.state == LeaseState.REVOKED

    def test_check_expired_leases(self, lease_manager: LeaseManager):
        """Test checking for expired leases."""
        # Create a lease that expires immediately
        config = LeaseConfig(default_duration_seconds=0)  # 0 seconds = expired immediately
        manager = LeaseManager(config)

        lease = manager.create_lease("job-1", "worker-1", 0)

        # Wait a moment
        time.sleep(0.1)

        expired = manager.check_expired_leases()

        assert len(expired) == 1
        assert expired[0].lease_id == lease.lease_id
        assert expired[0].state == LeaseState.EXPIRED

    def test_get_lease_by_job(self, lease_manager: LeaseManager):
        """Test getting lease by job ID."""
        lease = lease_manager.create_lease("job-1", "worker-1", 60)

        by_job = lease_manager.get_lease_by_job("job-1")
        assert by_job is not None
        assert by_job.lease_id == lease.lease_id

    def test_get_leases_by_worker(self, lease_manager: LeaseManager):
        """Test getting leases by worker ID."""
        lease_manager.create_lease("job-1", "worker-1", 60)
        lease_manager.create_lease("job-2", "worker-1", 60)
        lease_manager.create_lease("job-3", "worker-2", 60)

        worker1_leases = lease_manager.get_leases_by_worker("worker-1")
        assert len(worker1_leases) == 2

        worker2_leases = lease_manager.get_leases_by_worker("worker-2")
        assert len(worker2_leases) == 1


class TestLeaseIdempotency:
    """Tests specifically for idempotency guarantees."""

    @pytest.fixture
    def lease_manager(self) -> LeaseManager:
        return LeaseManager()

    def test_idempotency_key_prevents_duplicates(self, lease_manager: LeaseManager):
        """Test that idempotency key prevents duplicate operations."""
        # Create lease with idempotency key
        lease1 = lease_manager.create_lease(
            "job-1", "worker-1", 60,
            idempotency_key="create-job-1-attempt-1"
        )
        assert lease1 is not None

        # Same idempotency key should return same lease, not create new
        lease2 = lease_manager.create_lease(
            "job-1", "worker-1", 60,
            idempotency_key="create-job-1-attempt-1"
        )

        # Should get back the same lease
        assert lease2 is not None
        assert lease2.lease_id == lease1.lease_id

    def test_concurrent_release_safety(self, lease_manager: LeaseManager):
        """Test that concurrent releases are safe."""
        lease = lease_manager.create_lease("job-1", "worker-1", 60)

        # Simulate concurrent releases
        results = []
        for _ in range(5):
            result = lease_manager.release_lease(lease.lease_id, "worker-1")
            results.append(result)

        # All should return True (idempotent)
        assert all(results)

        # Final state should be RELEASED
        final = lease_manager.get_lease(lease.lease_id)
        assert final.state == LeaseState.RELEASED
