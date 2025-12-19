"""Tests for resource models."""

from distributed_cluster.models.resources import GPUInfo, ResourceSpec


class TestResourceSpec:
    """Tests for ResourceSpec."""

    def test_create_default(self):
        """Test creating default ResourceSpec."""
        spec = ResourceSpec()
        assert spec.cpu_cores == 1.0
        assert spec.memory_mb == 512
        assert spec.gpu_count == 0

    def test_create_with_values(self):
        """Test creating ResourceSpec with values."""
        spec = ResourceSpec(
            cpu_cores=8.0,
            memory_mb=16384,
            gpu_count=2,
            gpu_memory_mb=8192,
        )
        assert spec.cpu_cores == 8.0
        assert spec.memory_mb == 16384
        assert spec.gpu_count == 2
        assert spec.gpu_memory_mb == 8192

    def test_fits_in_true(self):
        """Test fits_in returns True when resources are available."""
        required = ResourceSpec(cpu_cores=2.0, memory_mb=1024)
        available = ResourceSpec(cpu_cores=8.0, memory_mb=16384)
        assert required.fits_in(available)

    def test_fits_in_false_cpu(self):
        """Test fits_in returns False when CPU is insufficient."""
        required = ResourceSpec(cpu_cores=16.0, memory_mb=1024)
        available = ResourceSpec(cpu_cores=8.0, memory_mb=16384)
        assert not required.fits_in(available)

    def test_fits_in_false_memory(self):
        """Test fits_in returns False when memory is insufficient."""
        required = ResourceSpec(cpu_cores=2.0, memory_mb=32768)
        available = ResourceSpec(cpu_cores=8.0, memory_mb=16384)
        assert not required.fits_in(available)

    def test_fits_in_false_gpu(self):
        """Test fits_in returns False when GPU is insufficient."""
        required = ResourceSpec(cpu_cores=2.0, memory_mb=1024, gpu_count=4)
        available = ResourceSpec(cpu_cores=8.0, memory_mb=16384, gpu_count=2)
        assert not required.fits_in(available)

    def test_subtract(self):
        """Test subtracting resources."""
        available = ResourceSpec(cpu_cores=8.0, memory_mb=16384, gpu_count=2)
        used = ResourceSpec(cpu_cores=2.0, memory_mb=4096, gpu_count=1)
        remaining = available.subtract(used)

        assert remaining.cpu_cores == 6.0
        assert remaining.memory_mb == 12288
        assert remaining.gpu_count == 1

    def test_add(self):
        """Test adding resources."""
        current = ResourceSpec(cpu_cores=2.0, memory_mb=4096, gpu_count=1)
        released = ResourceSpec(cpu_cores=2.0, memory_mb=4096, gpu_count=1)
        total = current.add(released)

        assert total.cpu_cores == 4.0
        assert total.memory_mb == 8192
        assert total.gpu_count == 2

    def test_to_dict(self):
        """Test converting to dictionary."""
        spec = ResourceSpec(cpu_cores=4.0, memory_mb=8192, gpu_count=1)
        d = spec.to_dict()

        assert d["cpu_cores"] == 4.0
        assert d["memory_mb"] == 8192
        assert d["gpu_count"] == 1

    def test_from_dict(self):
        """Test creating from dictionary."""
        d = {"cpu_cores": 4.0, "memory_mb": 8192, "gpu_count": 1}
        spec = ResourceSpec.from_dict(d)

        assert spec.cpu_cores == 4.0
        assert spec.memory_mb == 8192
        assert spec.gpu_count == 1


class TestGPUInfo:
    """Tests for GPUInfo."""

    def test_create(self):
        """Test creating GPUInfo."""
        gpu = GPUInfo(
            index=0,
            name="NVIDIA GeForce RTX 3080",
            uuid="GPU-abc123",
            memory_total_mb=10240,
            memory_free_mb=8192,
            memory_used_mb=2048,
            utilization_percent=25.0,
            temperature_c=45.0,
        )

        assert gpu.index == 0
        assert gpu.name == "NVIDIA GeForce RTX 3080"
        assert gpu.memory_total_mb == 10240
        assert gpu.memory_available_mb == 8192

    def test_is_available_true(self):
        """Test GPU is available when utilization is low."""
        gpu = GPUInfo(
            index=0,
            name="GPU",
            uuid="GPU-123",
            memory_total_mb=10240,
            memory_free_mb=8192,
            memory_used_mb=2048,
            utilization_percent=50.0,
        )
        assert gpu.is_available

    def test_is_available_false_high_util(self):
        """Test GPU is unavailable when utilization is high."""
        gpu = GPUInfo(
            index=0,
            name="GPU",
            uuid="GPU-123",
            memory_total_mb=10240,
            memory_free_mb=8192,
            memory_used_mb=2048,
            utilization_percent=95.0,
        )
        assert not gpu.is_available

    def test_is_available_false_low_memory(self):
        """Test GPU is unavailable when memory is low."""
        gpu = GPUInfo(
            index=0,
            name="GPU",
            uuid="GPU-123",
            memory_total_mb=10240,
            memory_free_mb=256,
            memory_used_mb=9984,
            utilization_percent=50.0,
        )
        assert not gpu.is_available
