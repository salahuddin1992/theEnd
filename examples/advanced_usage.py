#!/usr/bin/env python3
"""
Advanced Usage Examples - أمثلة استخدام متقدمة
=============================================

This file demonstrates advanced features of the Distributed Computing System.
هذا الملف يوضح الميزات المتقدمة لنظام الحوسبة الموزّعة.
"""

import asyncio

import httpx

# =============================================================================
# Basic Configuration
# =============================================================================

MASTER_URL = "http://localhost:8765"


# =============================================================================
# 1. Job Templates - قوالب المهام
# =============================================================================


async def create_and_use_template():
    """
    Create a job template and use it for consistent job submissions.
    إنشاء قالب مهمة واستخدامه لإرسال مهام متسقة.
    """
    async with httpx.AsyncClient(base_url=MASTER_URL) as client:
        # Create a template for ML training jobs
        template = {
            "name": "gpu-training",
            "description": "Template for GPU-based ML training",
            "resources": {
                "cpu_cores": 4.0,
                "memory_mb": 8192,
                "gpu_count": 1,
            },
            "docker_image": "pytorch/pytorch:2.0-cuda11.8-cudnn8-runtime",
            "timeout_seconds": 86400,  # 24 hours
            "environment": {
                "CUDA_VISIBLE_DEVICES": "0",
                "WANDB_MODE": "offline",
            },
        }

        # Create template
        response = await client.post("/templates", json=template)
        print(f"Template created: {response.json()}")

        # Submit jobs using the template
        for epoch in [10, 50, 100]:
            job = {
                "template": "gpu-training",
                "command": f"python train.py --epochs {epoch}",
                "name": f"training-epochs-{epoch}",
                "environment": {
                    "EPOCHS": str(epoch),
                },
            }
            response = await client.post("/jobs", json=job)
            print(f"Job submitted: {response.json()}")


# =============================================================================
# 2. Priority Queues - طوابير الأولوية
# =============================================================================


async def setup_priority_queues():
    """
    Set up priority queues for different workloads.
    إعداد طوابير أولوية لأنواع مختلفة من المهام.
    """
    async with httpx.AsyncClient(base_url=MASTER_URL) as client:
        # Create high priority queue for production jobs
        await client.post(
            "/queues",
            json={
                "name": "production",
                "priority": 100,
                "weight": 3,
                "max_concurrent_jobs": 100,
            },
        )

        # Create normal priority queue for development
        await client.post(
            "/queues",
            json={
                "name": "development",
                "priority": 50,
                "weight": 1,
                "max_concurrent_jobs": 50,
            },
        )

        # Create low priority queue for batch processing
        await client.post(
            "/queues",
            json={
                "name": "batch",
                "priority": 10,
                "weight": 1,
                "max_concurrent_jobs": 200,
            },
        )

        # Submit jobs to different queues
        # High priority - production inference
        await client.post(
            "/jobs",
            json={
                "command": "python inference.py --model production",
                "name": "production-inference",
                "queue": "production",
                "resources": {"cpu_cores": 2, "memory_mb": 4096, "gpu_count": 1},
            },
        )

        # Normal priority - development testing
        await client.post(
            "/jobs",
            json={
                "command": "pytest tests/ -v",
                "name": "dev-tests",
                "queue": "development",
                "resources": {"cpu_cores": 4, "memory_mb": 2048},
            },
        )

        # Low priority - batch data processing
        for i in range(10):
            await client.post(
                "/jobs",
                json={
                    "command": f"python process_data.py --batch {i}",
                    "name": f"batch-{i}",
                    "queue": "batch",
                    "resources": {"cpu_cores": 1, "memory_mb": 1024},
                },
            )

        print("Priority queues configured!")


# =============================================================================
# 3. Worker Pools - مجموعات العمال
# =============================================================================


async def setup_worker_pools():
    """
    Organize workers into pools for different workloads.
    تنظيم العمال في مجموعات لأنواع مختلفة من المهام.
    """
    async with httpx.AsyncClient(base_url=MASTER_URL) as client:
        # Create GPU pool
        await client.post(
            "/pools",
            json={
                "name": "gpu-pool",
                "description": "Workers with GPU for ML workloads",
                "min_workers": 1,
                "max_workers": 10,
                "labels": ["gpu", "ml", "cuda"],
                "autoscale_enabled": True,
            },
        )

        # Create CPU pool
        await client.post(
            "/pools",
            json={
                "name": "cpu-pool",
                "description": "CPU-only workers for general workloads",
                "min_workers": 2,
                "max_workers": 50,
                "labels": ["cpu", "general"],
                "autoscale_enabled": True,
            },
        )

        # Create high-memory pool
        await client.post(
            "/pools",
            json={
                "name": "highmem-pool",
                "description": "High memory workers for data processing",
                "min_workers": 0,
                "max_workers": 5,
                "labels": ["highmem", "data"],
                "autoscale_enabled": True,
            },
        )

        print("Worker pools configured!")


# =============================================================================
# 4. Real-time Monitoring - المراقبة الحية
# =============================================================================


async def monitor_cluster_realtime():
    """
    Monitor cluster in real-time using WebSocket.
    مراقبة الكلاستر بشكل حي باستخدام WebSocket.
    """
    import websockets

    async with websockets.connect("ws://localhost:8765/ws") as ws:
        print("Connected to cluster WebSocket")

        # Send ping to keep alive
        async def send_ping():
            while True:
                await asyncio.sleep(30)
                await ws.send("ping")

        ping_task = asyncio.create_task(send_ping())

        try:
            while True:
                message = await ws.recv()

                if message == "pong":
                    continue

                import json

                data = json.loads(message)

                if data["type"] == "initial_state":
                    print("\n=== Initial Cluster State ===")
                    stats = data["stats"]
                    print(f"Workers: {stats.get('active_workers', 0)}/{stats.get('total_workers', 0)}")
                    print(f"Jobs Running: {stats.get('running_jobs', 0)}")
                    print(f"Jobs Pending: {stats.get('pending_jobs', 0)}")

                elif data["type"] == "event":
                    event = data["event"]
                    print(f"\n[{event['timestamp']}] {event['event_type']}")
                    print(f"  Data: {event.get('data', {})}")

        except asyncio.CancelledError:
            pass
        finally:
            ping_task.cancel()


# =============================================================================
# 5. Batch Job Submission - إرسال مهام جماعية
# =============================================================================


async def submit_batch_jobs():
    """
    Submit multiple jobs efficiently.
    إرسال مهام متعددة بكفاءة.
    """
    async with httpx.AsyncClient(base_url=MASTER_URL) as client:
        # Prepare batch of jobs
        jobs = []
        for i in range(100):
            jobs.append(
                {
                    "command": f"python process.py --item {i}",
                    "name": f"batch-item-{i}",
                    "resources": {
                        "cpu_cores": 1.0,
                        "memory_mb": 512,
                    },
                    "priority": 25,  # Low priority
                    "labels": {
                        "batch_id": "batch-001",
                        "item_index": str(i),
                    },
                }
            )

        # Submit jobs (could be done in parallel)
        job_ids = []
        for job in jobs:
            response = await client.post("/jobs", json=job)
            job_ids.append(response.json()["job_id"])
            print(f"Submitted job {len(job_ids)}/{len(jobs)}")

        print(f"\nSubmitted {len(job_ids)} jobs")

        # Monitor batch progress
        while True:
            completed = 0
            failed = 0
            running = 0

            for job_id in job_ids:
                response = await client.get(f"/jobs/{job_id}")
                status = response.json()["status"]

                if status == "completed":
                    completed += 1
                elif status == "failed":
                    failed += 1
                elif status == "running":
                    running += 1

            print(f"Progress: {completed} completed, {running} running, {failed} failed")

            if completed + failed == len(job_ids):
                break

            await asyncio.sleep(5)

        print(f"\nBatch complete! {completed} succeeded, {failed} failed")


# =============================================================================
# 6. Job with Dependencies (DAG) - مهام مترابطة
# =============================================================================


async def submit_dag_workflow():
    """
    Submit a workflow with job dependencies.
    إرسال سير عمل مع تبعيات بين المهام.
    """
    async with httpx.AsyncClient(base_url=MASTER_URL) as client:
        # Step 1: Data download
        download_job = {
            "command": "python download_data.py",
            "name": "data-download",
            "resources": {"cpu_cores": 1, "memory_mb": 512},
        }
        r1 = await client.post("/jobs", json=download_job)
        download_id = r1.json()["job_id"]
        print(f"Data download job: {download_id}")

        # Wait for download to complete
        while True:
            r = await client.get(f"/jobs/{download_id}")
            if r.json()["status"] in ("completed", "failed"):
                break
            await asyncio.sleep(2)

        if r.json()["status"] != "completed":
            print("Download failed, aborting workflow")
            return

        # Step 2: Parallel preprocessing
        preprocess_ids = []
        for split in ["train", "val", "test"]:
            job = {
                "command": f"python preprocess.py --split {split}",
                "name": f"preprocess-{split}",
                "resources": {"cpu_cores": 4, "memory_mb": 4096},
                "labels": {"depends_on": download_id},
            }
            r = await client.post("/jobs", json=job)
            preprocess_ids.append(r.json()["job_id"])

        print(f"Preprocessing jobs: {preprocess_ids}")

        # Wait for all preprocessing
        for job_id in preprocess_ids:
            while True:
                r = await client.get(f"/jobs/{job_id}")
                if r.json()["status"] in ("completed", "failed"):
                    break
                await asyncio.sleep(2)

        # Step 3: Training (depends on all preprocessing)
        train_job = {
            "command": "python train.py --epochs 100",
            "name": "model-training",
            "resources": {"cpu_cores": 8, "memory_mb": 16384, "gpu_count": 1},
            "priority": 100,
            "labels": {"depends_on": ",".join(preprocess_ids)},
        }
        r = await client.post("/jobs", json=train_job)
        train_id = r.json()["job_id"]
        print(f"Training job: {train_id}")

        # Wait for training
        while True:
            r = await client.get(f"/jobs/{train_id}")
            status = r.json()["status"]
            if status in ("completed", "failed"):
                break
            print(f"Training status: {status}")
            await asyncio.sleep(10)

        # Step 4: Evaluation
        eval_job = {
            "command": "python evaluate.py",
            "name": "model-evaluation",
            "resources": {"cpu_cores": 4, "memory_mb": 8192, "gpu_count": 1},
            "labels": {"depends_on": train_id},
        }
        r = await client.post("/jobs", json=eval_job)
        eval_id = r.json()["job_id"]
        print(f"Evaluation job: {eval_id}")

        print("\nWorkflow submitted successfully!")


# =============================================================================
# 7. Resource Quotas - حصص الموارد
# =============================================================================


async def setup_user_quotas():
    """
    Set up resource quotas for users/teams.
    إعداد حصص الموارد للمستخدمين/الفرق.
    """
    async with httpx.AsyncClient(base_url=MASTER_URL) as client:
        # Note: This requires the quota management endpoint
        quotas = [
            {
                "user_id": "team-ml",
                "max_concurrent_jobs": 50,
                "max_cpu_cores": 100,
                "max_memory_gb": 200,
                "max_gpus": 8,
            },
            {
                "user_id": "team-data",
                "max_concurrent_jobs": 100,
                "max_cpu_cores": 200,
                "max_memory_gb": 500,
                "max_gpus": 0,
            },
            {
                "user_id": "team-research",
                "max_concurrent_jobs": 20,
                "max_cpu_cores": 50,
                "max_memory_gb": 100,
                "max_gpus": 4,
            },
        ]

        for quota in quotas:
            try:
                await client.post("/quotas", json=quota)
                print(f"Quota set for {quota['user_id']}")
            except Exception as e:
                print(f"Error setting quota: {e}")


# =============================================================================
# 8. Custom Metrics - مقاييس مخصصة
# =============================================================================


async def get_custom_metrics():
    """
    Get detailed cluster metrics.
    الحصول على مقاييس تفصيلية للكلاستر.
    """
    async with httpx.AsyncClient(base_url=MASTER_URL) as client:
        # Get cluster stats
        stats = (await client.get("/stats")).json()

        print("\n=== Cluster Metrics ===")
        print(f"Total Workers: {stats.get('total_workers', 0)}")
        print(f"Active Workers: {stats.get('active_workers', 0)}")
        print(f"Total CPU Cores: {stats.get('total_cpu_cores', 0)}")
        print(f"Available CPU Cores: {stats.get('available_cpu_cores', 0)}")
        available = stats.get("available_cpu_cores", 0)
        total = max(stats.get("total_cpu_cores", 1), 1)
        print(f"CPU Utilization: {100 - (available / total * 100):.1f}%")

        print(f"\nTotal Memory: {stats.get('total_memory_gb', 0):.1f} GB")
        print(f"Available Memory: {stats.get('available_memory_gb', 0):.1f} GB")

        print(f"\nTotal GPUs: {stats.get('total_gpus', 0)}")
        print(f"Available GPUs: {stats.get('available_gpus', 0)}")

        print("\n=== Job Metrics ===")
        print(f"Total Jobs: {stats.get('total_jobs', 0)}")
        print(f"Pending: {stats.get('pending_jobs', 0)}")
        print(f"Running: {stats.get('running_jobs', 0)}")
        print(f"Completed: {stats.get('completed_jobs', 0)}")
        print(f"Failed: {stats.get('failed_jobs', 0)}")

        # Get workers detail
        workers = (await client.get("/workers")).json().get("workers", [])
        print("\n=== Worker Details ===")
        for w in workers:
            print(f"\n{w.get('hostname', 'unknown')} ({w.get('status', 'unknown')})")
            res = w.get("total_resources", {})
            print(f"  CPU: {res.get('cpu_cores', 0)} cores")
            print(f"  Memory: {res.get('memory_mb', 0)} MB")
            print(f"  GPU: {res.get('gpu_count', 0)}")
            print(f"  Active Jobs: {len(w.get('active_jobs', []))}")


# =============================================================================
# Main Entry Point
# =============================================================================


async def main():
    """Run examples."""
    print("=" * 60)
    print("Distributed Computing System - Advanced Examples")
    print("=" * 60)

    # Uncomment the example you want to run:

    # await create_and_use_template()
    # await setup_priority_queues()
    # await setup_worker_pools()
    # await monitor_cluster_realtime()
    # await submit_batch_jobs()
    # await submit_dag_workflow()
    # await setup_user_quotas()
    await get_custom_metrics()


if __name__ == "__main__":
    asyncio.run(main())
