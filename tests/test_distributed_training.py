# -*- coding: utf-8 -*-
"""
Tests for Distributed Training Module
======================================

اختبارات وحدة التدريب الموزع.
"""

import asyncio
import os
import tempfile
import pytest
import numpy as np
from datetime import datetime

from distributed_cluster.ml.distributed_training import (
    TrainingConfig,
    TrainingStrategy,
    AggregationMethod,
    TrainingStatus,
    WorkerState,
    TrainingMetrics,
    GradientUpdate,
    SyncSGDAggregator,
    RingAllReduceAggregator,
    FederatedAvgAggregator,
    ParameterServer,
    DistributedTrainer,
    TrainingJobManager,
    DataSharder,
    ModelPartitioner,
    create_training_config,
    simulate_training_step,
)


# =============================================================================
# Training Config Tests
# =============================================================================


class TestTrainingConfig:
    """Tests for TrainingConfig class."""

    def test_create_config(self):
        """Test creating training configuration."""
        config = TrainingConfig(
            job_id="test-job-123",
            model_name="test-model",
            strategy=TrainingStrategy.DATA_PARALLEL,
            aggregation=AggregationMethod.SYNC_SGD,
            num_workers=4,
            batch_size=32,
            epochs=10,
            learning_rate=0.001,
        )

        assert config.job_id == "test-job-123"
        assert config.num_workers == 4
        assert config.strategy == TrainingStrategy.DATA_PARALLEL

    def test_config_to_dict(self):
        """Test config serialization."""
        config = create_training_config(
            job_id="test-job",
            model_name="bert",
            num_workers=8,
        )

        data = config.to_dict()

        assert data["job_id"] == "test-job"
        assert data["model_name"] == "bert"
        assert data["num_workers"] == 8


# =============================================================================
# Gradient Aggregator Tests
# =============================================================================


class TestGradientAggregators:
    """Tests for gradient aggregation methods."""

    def create_updates(self, num_workers: int, grad_shape: tuple) -> list:
        """Create test gradient updates."""
        updates = []
        for i in range(num_workers):
            gradients = {
                "layer1": np.random.randn(*grad_shape),
                "layer2": np.random.randn(*grad_shape),
            }
            updates.append(GradientUpdate(
                worker_id=f"worker-{i}",
                step=0,
                gradients=gradients,
                loss=1.0 - i * 0.1,
                samples_in_batch=32,
            ))
        return updates

    @pytest.mark.asyncio
    async def test_sync_sgd_aggregator(self):
        """Test synchronous SGD aggregation."""
        aggregator = SyncSGDAggregator()
        updates = self.create_updates(4, (10, 10))

        result = await aggregator.aggregate(updates)

        assert "layer1" in result
        assert "layer2" in result
        assert result["layer1"].shape == (10, 10)

    @pytest.mark.asyncio
    async def test_ring_allreduce_aggregator(self):
        """Test Ring AllReduce aggregation."""
        aggregator = RingAllReduceAggregator(num_workers=4)
        updates = self.create_updates(4, (10, 10))

        result = await aggregator.aggregate(updates)

        assert "layer1" in result
        # Result should be average of all gradients
        expected_shape = updates[0].gradients["layer1"].shape
        assert result["layer1"].shape == expected_shape

    @pytest.mark.asyncio
    async def test_federated_avg_aggregator(self):
        """Test Federated Averaging aggregation."""
        aggregator = FederatedAvgAggregator()
        updates = self.create_updates(4, (10, 10))

        # Give different sample counts
        for i, update in enumerate(updates):
            update.samples_in_batch = 32 * (i + 1)

        result = await aggregator.aggregate(updates)

        assert "layer1" in result
        # Weighted average based on samples

    @pytest.mark.asyncio
    async def test_empty_updates(self):
        """Test aggregation with empty updates."""
        aggregator = SyncSGDAggregator()
        result = await aggregator.aggregate([])
        assert result == {}


# =============================================================================
# Parameter Server Tests
# =============================================================================


class TestParameterServer:
    """Tests for ParameterServer class."""

    @pytest.fixture
    def server(self):
        """Create a parameter server instance."""
        return ParameterServer(
            aggregation_method=AggregationMethod.SYNC_SGD,
            num_workers=2,
        )

    @pytest.mark.asyncio
    async def test_initialize_parameters(self, server):
        """Test parameter initialization."""
        params = {
            "weights": np.random.randn(100, 50),
            "bias": np.random.randn(50),
        }

        await server.initialize_parameters(params)

        retrieved = await server.get_parameters()
        assert "weights" in retrieved
        assert "bias" in retrieved
        assert retrieved["weights"].shape == (100, 50)

    @pytest.mark.asyncio
    async def test_submit_gradients_partial(self, server):
        """Test partial gradient submission."""
        await server.initialize_parameters({
            "layer": np.zeros((10, 10)),
        })

        update = GradientUpdate(
            worker_id="worker-0",
            step=0,
            gradients={"layer": np.ones((10, 10))},
            loss=1.0,
            samples_in_batch=32,
        )

        # Only one worker submitted, should return None
        result = await server.submit_gradients(update)
        assert result is None

    @pytest.mark.asyncio
    async def test_submit_gradients_complete(self, server):
        """Test complete gradient submission."""
        await server.initialize_parameters({
            "layer": np.zeros((10, 10)),
        })

        # Submit from all workers
        for i in range(2):
            update = GradientUpdate(
                worker_id=f"worker-{i}",
                step=0,
                gradients={"layer": np.ones((10, 10)) * (i + 1)},
                loss=1.0,
                samples_in_batch=32,
            )
            result = await server.submit_gradients(update)

        # Last submission should trigger aggregation
        assert result is not None
        assert "layer" in result

    @pytest.mark.asyncio
    async def test_apply_gradients(self, server):
        """Test gradient application."""
        initial_params = {"layer": np.ones((10, 10)) * 10}
        await server.initialize_parameters(initial_params)

        gradients = {"layer": np.ones((10, 10))}
        await server.apply_gradients(gradients, learning_rate=0.1)

        updated = await server.get_parameters()
        # params -= lr * gradients -> 10 - 0.1 * 1 = 9.9
        assert np.allclose(updated["layer"], 9.9)


# =============================================================================
# Distributed Trainer Tests
# =============================================================================


class TestDistributedTrainer:
    """Tests for DistributedTrainer class."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return create_training_config(
            job_id="test-training",
            model_name="test-model",
            num_workers=2,
            batch_size=32,
            epochs=2,
            learning_rate=0.01,
            dataset_size=1000,
        )

    @pytest.fixture
    def trainer(self, config):
        """Create trainer instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield DistributedTrainer(config=config, checkpoint_dir=tmpdir)

    @pytest.mark.asyncio
    async def test_initialize(self, trainer):
        """Test trainer initialization."""
        params = {
            "layer1": np.random.randn(100, 50),
            "layer2": np.random.randn(50, 10),
        }

        await trainer.initialize(params)

        assert trainer._status == TrainingStatus.TRAINING
        assert trainer._metrics.total_steps > 0

    @pytest.mark.asyncio
    async def test_register_worker(self, trainer):
        """Test worker registration."""
        params = {"layer": np.random.randn(10, 10)}
        await trainer.initialize(params)

        worker_params = await trainer.register_worker("worker-1", rank=0)

        assert "layer" in worker_params
        assert "worker-1" in trainer._workers

    @pytest.mark.asyncio
    async def test_submit_training_update(self, trainer):
        """Test submitting training updates."""
        params = {"layer": np.random.randn(10, 10)}
        await trainer.initialize(params)

        await trainer.register_worker("worker-0", rank=0)
        await trainer.register_worker("worker-1", rank=1)

        # Submit from both workers
        for i in range(2):
            result = await trainer.submit_training_update(
                worker_id=f"worker-{i}",
                step=0,
                gradients={"layer": np.random.randn(10, 10) * 0.01},
                loss=1.0,
                samples=32,
            )

        # Second submission should return updated params
        assert result is not None

    @pytest.mark.asyncio
    async def test_get_status(self, trainer):
        """Test getting training status."""
        params = {"layer": np.random.randn(10, 10)}
        await trainer.initialize(params)

        status = await trainer.get_status()

        assert "job_id" in status
        assert "status" in status
        assert "metrics" in status

    @pytest.mark.asyncio
    async def test_complete_training(self, trainer):
        """Test completing training."""
        params = {"layer": np.random.randn(10, 10)}
        await trainer.initialize(params)

        result = await trainer.complete_training()

        assert result["status"] == "completed"
        assert trainer._status == TrainingStatus.COMPLETED


# =============================================================================
# Training Job Manager Tests
# =============================================================================


class TestTrainingJobManager:
    """Tests for TrainingJobManager class."""

    @pytest.fixture
    def manager(self):
        """Create manager instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield TrainingJobManager(checkpoint_base_dir=tmpdir)

    @pytest.mark.asyncio
    async def test_create_job(self, manager):
        """Test creating a training job."""
        config = create_training_config(
            job_id="job-1",
            model_name="model-1",
        )

        job_id = await manager.create_job(config)
        assert job_id == "job-1"

        job = await manager.get_job("job-1")
        assert job is not None

    @pytest.mark.asyncio
    async def test_list_jobs(self, manager):
        """Test listing jobs."""
        for i in range(3):
            config = create_training_config(
                job_id=f"job-{i}",
                model_name=f"model-{i}",
            )
            await manager.create_job(config)

        jobs = await manager.list_jobs()
        assert len(jobs) == 3

    @pytest.mark.asyncio
    async def test_cancel_job(self, manager):
        """Test cancelling a job."""
        config = create_training_config(
            job_id="cancel-job",
            model_name="model",
        )
        await manager.create_job(config)

        result = await manager.cancel_job("cancel-job")
        assert result is True

        job = await manager.get_job("cancel-job")
        assert job._status == TrainingStatus.CANCELLED


# =============================================================================
# Data Sharding Tests
# =============================================================================


class TestDataSharder:
    """Tests for DataSharder utility."""

    def test_shard_indices_basic(self):
        """Test basic index sharding."""
        indices = DataSharder.shard_indices(
            total_samples=100,
            num_shards=4,
            shard_id=0,
            shuffle=False,
        )

        assert len(indices) == 25

    def test_shard_indices_uneven(self):
        """Test sharding with uneven distribution."""
        all_indices = []
        for shard_id in range(3):
            indices = DataSharder.shard_indices(
                total_samples=100,
                num_shards=3,
                shard_id=shard_id,
                shuffle=False,
            )
            all_indices.extend(indices)

        # All samples should be covered
        assert len(all_indices) == 100
        assert set(all_indices) == set(range(100))

    def test_shard_indices_shuffled(self):
        """Test shuffled sharding."""
        indices1 = DataSharder.shard_indices(
            total_samples=100,
            num_shards=4,
            shard_id=0,
            shuffle=True,
            seed=42,
        )
        indices2 = DataSharder.shard_indices(
            total_samples=100,
            num_shards=4,
            shard_id=0,
            shuffle=True,
            seed=42,
        )

        # Same seed should give same result
        assert indices1 == indices2

    def test_create_batch_iterator(self):
        """Test batch iterator creation."""
        indices = list(range(100))
        batches = list(DataSharder.create_batch_iterator(indices, batch_size=32))

        assert len(batches) == 3  # 32 + 32 + 32 = 96 (drop last 4)
        assert all(len(b) == 32 for b in batches)

    def test_compute_shard_hash(self):
        """Test consistent shard hashing."""
        data = b"test_data"
        shard1 = DataSharder.compute_shard_hash(data, 4)
        shard2 = DataSharder.compute_shard_hash(data, 4)

        assert shard1 == shard2
        assert 0 <= shard1 < 4


# =============================================================================
# Model Partitioner Tests
# =============================================================================


class TestModelPartitioner:
    """Tests for ModelPartitioner utility."""

    def test_partition_layers_basic(self):
        """Test basic layer partitioning."""
        layers = ["layer1", "layer2", "layer3", "layer4"]
        partitions = ModelPartitioner.partition_layers(layers, num_partitions=2)

        assert len(partitions) == 2
        assert len(partitions[0]) == 2
        assert len(partitions[1]) == 2

    def test_partition_by_memory(self):
        """Test memory-based partitioning."""
        layers = [
            ("large_layer", 1000000),
            ("medium_layer", 500000),
            ("small_layer1", 100000),
            ("small_layer2", 100000),
        ]

        partitions = ModelPartitioner.partition_by_memory(layers, num_partitions=2)

        # Should balance memory across partitions
        assert len(partitions) == 2
        # Large layer should be in one partition, medium + smalls in other


# =============================================================================
# Integration Tests
# =============================================================================


class TestDistributedTrainingIntegration:
    """Integration tests for distributed training."""

    @pytest.mark.asyncio
    async def test_full_training_loop(self):
        """Test complete training loop."""
        config = create_training_config(
            job_id="integration-test",
            model_name="test-model",
            num_workers=2,
            batch_size=32,
            epochs=1,
            learning_rate=0.01,
            dataset_size=320,  # 10 steps
            checkpoint_interval=5,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            trainer = DistributedTrainer(config=config, checkpoint_dir=tmpdir)

            # Initialize with random parameters
            params = {
                "layer1": np.random.randn(100, 50) * 0.01,
                "layer2": np.random.randn(50, 10) * 0.01,
            }
            await trainer.initialize(params)

            # Register workers
            for i in range(2):
                await trainer.register_worker(f"worker-{i}", rank=i)

            # Run training steps
            for step in range(5):
                for worker_id in ["worker-0", "worker-1"]:
                    await simulate_training_step(
                        trainer, worker_id, step, config.batch_size
                    )

            # Complete training
            result = await trainer.complete_training()

            assert result["status"] == "completed"
            assert result["checkpoints"] >= 1

    @pytest.mark.asyncio
    async def test_checkpoint_and_resume(self):
        """Test checkpoint saving and resumption."""
        config = create_training_config(
            job_id="checkpoint-test",
            model_name="test-model",
            num_workers=1,
            checkpoint_interval=2,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            trainer = DistributedTrainer(config=config, checkpoint_dir=tmpdir)

            params = {"layer": np.ones((10, 10))}
            await trainer.initialize(params)
            await trainer.register_worker("worker-0", rank=0)

            # Run some steps to trigger checkpoint
            for step in range(3):
                await simulate_training_step(trainer, "worker-0", step, 32)

            # Should have checkpoints
            assert len(trainer._checkpoints) > 0

            # Get checkpoint ID
            checkpoint_id = trainer._checkpoints[0].checkpoint_id

            # Create new trainer and load checkpoint
            trainer2 = DistributedTrainer(config=config, checkpoint_dir=tmpdir)
            trainer2._checkpoints = trainer._checkpoints

            loaded = await trainer2.load_checkpoint(checkpoint_id)
            assert loaded is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
