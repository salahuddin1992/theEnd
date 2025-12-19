#!/usr/bin/env python3
"""
مثال بسيط لاستخدام نظام الحوسبة الموزّعة.
Simple example of using the distributed computing system.

هذا المثال يوضح كيفية:
1. إنشاء Master server
2. إنشاء Worker agent
3. إرسال jobs وتتبع حالتها
"""

import asyncio

import httpx


async def main():
    """Main example function."""
    master_url = "http://localhost:8765"

    # انتظر حتى يكون Master جاهز
    print("Connecting to master...")
    async with httpx.AsyncClient() as client:
        for _ in range(10):
            try:
                resp = await client.get(f"{master_url}/health")
                if resp.status_code == 200:
                    print("Master is ready!")
                    break
            except Exception:
                pass
            await asyncio.sleep(1)
        else:
            print("Master not available")
            return

        # عرض حالة الكلاستر
        print("\n=== Cluster Status ===")
        resp = await client.get(f"{master_url}/stats")
        stats = resp.json()
        print(f"Workers: {stats['active_workers']}/{stats['total_workers']}")
        print(f"CPU: {stats['available_cpu_cores']:.1f}/{stats['total_cpu_cores']:.1f} cores")
        print(f"Memory: {stats['available_memory_gb']:.1f}/{stats['total_memory_gb']:.1f} GB")
        print(f"GPUs: {stats['available_gpus']}/{stats['total_gpus']}")

        # إرسال job بسيط
        print("\n=== Submitting Job ===")
        job_data = {
            "command": "python",
            "args": ["-c", "print('Hello from distributed cluster!')"],
            "name": "hello-world",
            "resources": {
                "cpu_cores": 0.5,
                "memory_mb": 256,
            },
            "timeout_seconds": 60,
        }

        resp = await client.post(f"{master_url}/jobs", json=job_data)
        result = resp.json()
        job_id = result["job_id"]
        print(f"Job submitted: {job_id}")

        # انتظار النتيجة
        print("\n=== Waiting for Result ===")
        for _ in range(30):
            resp = await client.get(f"{master_url}/jobs/{job_id}")
            job = resp.json()
            status = job["status"]
            print(f"  Status: {status}")

            if status in ("completed", "failed", "cancelled", "timeout"):
                break

            await asyncio.sleep(1)

        # عرض النتيجة
        if job.get("result"):
            result = job["result"]
            print("\n=== Result ===")
            print(f"Exit code: {result['exit_code']}")
            print(f"Time: {result['execution_time_seconds']:.2f}s")
            if result.get("stdout"):
                print(f"Output:\n{result['stdout']}")
            if result.get("stderr"):
                print(f"Errors:\n{result['stderr']}")


if __name__ == "__main__":
    asyncio.run(main())
