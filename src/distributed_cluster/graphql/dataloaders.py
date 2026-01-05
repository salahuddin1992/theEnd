"""
GraphQL DataLoaders - محملات البيانات
=====================================

Efficient batch loading for GraphQL resolvers.

Author: NebulaCompute Team
License: MIT
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable, Dict, Generic, List, Optional, TypeVar

logger = logging.getLogger(__name__)

K = TypeVar("K")  # Key type
V = TypeVar("V")  # Value type


class DataLoader(Generic[K, V]):
    """
    محمّل البيانات العام
    Generic DataLoader

    يجمع الطلبات ويحملها بكفاءة دفعة واحدة.
    Batches and caches data loading requests.
    """

    def __init__(
        self,
        batch_load_fn: Callable[[List[K]], Any],
        cache: bool = True,
        max_batch_size: int = 100,
    ):
        self._batch_load_fn = batch_load_fn
        self._cache_enabled = cache
        self._max_batch_size = max_batch_size
        self._cache: Dict[K, V] = {}
        self._queue: List[tuple[K, asyncio.Future]] = []
        self._batch_scheduled = False

    async def load(self, key: K) -> Optional[V]:
        """
        تحميل قيمة بالمفتاح
        Load value by key
        """
        # Check cache first
        if self._cache_enabled and key in self._cache:
            return self._cache[key]

        # Create future for this request
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._queue.append((key, future))

        # Schedule batch if not already scheduled
        if not self._batch_scheduled:
            self._batch_scheduled = True
            asyncio.get_event_loop().call_soon(lambda: asyncio.create_task(self._dispatch_batch()))

        return await future

    async def load_many(self, keys: List[K]) -> List[Optional[V]]:
        """
        تحميل عدة قيم
        Load multiple values
        """
        return await asyncio.gather(*[self.load(key) for key in keys])

    async def _dispatch_batch(self) -> None:
        """
        تنفيذ الدفعة
        Dispatch batch
        """
        self._batch_scheduled = False

        if not self._queue:
            return

        # Take items from queue
        batch = self._queue[: self._max_batch_size]
        self._queue = self._queue[self._max_batch_size :]

        keys = [item[0] for item in batch]
        futures = [item[1] for item in batch]

        try:
            # Load batch
            values = await self._batch_load_fn(keys)

            # Handle results
            if len(values) != len(keys):
                error = ValueError(f"DataLoader batch function returned {len(values)} values " f"for {len(keys)} keys")
                for future in futures:
                    if not future.done():
                        future.set_exception(error)
                return

            # Set results
            for key, value, future in zip(keys, values, futures):
                if self._cache_enabled:
                    self._cache[key] = value
                if not future.done():
                    future.set_result(value)

        except Exception as e:
            # Set exception for all futures
            for future in futures:
                if not future.done():
                    future.set_exception(e)

        # Schedule next batch if queue is not empty
        if self._queue and not self._batch_scheduled:
            self._batch_scheduled = True
            asyncio.get_event_loop().call_soon(lambda: asyncio.create_task(self._dispatch_batch()))

    def clear(self, key: Optional[K] = None) -> None:
        """
        مسح الذاكرة المؤقتة
        Clear cache
        """
        if key is None:
            self._cache.clear()
        elif key in self._cache:
            del self._cache[key]

    def prime(self, key: K, value: V) -> None:
        """
        تعبئة الذاكرة المؤقتة مسبقاً
        Prime cache
        """
        if self._cache_enabled:
            self._cache[key] = value


class DataLoaders:
    """
    مجموعة محملات البيانات
    Collection of DataLoaders

    يوفر محملات لجميع الكيانات.
    Provides loaders for all entities.
    """

    def __init__(self, services: Any = None):
        self.services = services

        # Job loader
        self.job_loader = DataLoader(self._batch_load_jobs)

        # Worker loader
        self.worker_loader = DataLoader(self._batch_load_workers)

        # Tenant loader
        self.tenant_loader = DataLoader(self._batch_load_tenants)

        # Backup loader
        self.backup_loader = DataLoader(self._batch_load_backups)

        # Job by worker loader
        self.jobs_by_worker_loader = DataLoader(
            self._batch_load_jobs_by_worker,
            cache=False,  # Don't cache list queries
        )

        # Jobs by tenant loader
        self.jobs_by_tenant_loader = DataLoader(
            self._batch_load_jobs_by_tenant,
            cache=False,
        )

    async def _batch_load_jobs(self, job_ids: List[str]) -> List[Optional[Any]]:
        """تحميل دفعة من المهام"""
        if not self.services or not self.services.job_service:
            return [None] * len(job_ids)

        try:
            jobs = await self.services.job_service.get_jobs_by_ids(job_ids)
            # Create a map for quick lookup
            job_map = {job.id: job for job in jobs if job}
            return [job_map.get(job_id) for job_id in job_ids]
        except Exception as e:
            logger.error(f"Error batch loading jobs: {e}")
            return [None] * len(job_ids)

    async def _batch_load_workers(self, worker_ids: List[str]) -> List[Optional[Any]]:
        """تحميل دفعة من العمال"""
        if not self.services or not self.services.worker_service:
            return [None] * len(worker_ids)

        try:
            workers = await self.services.worker_service.get_workers_by_ids(worker_ids)
            worker_map = {worker.id: worker for worker in workers if worker}
            return [worker_map.get(worker_id) for worker_id in worker_ids]
        except Exception as e:
            logger.error(f"Error batch loading workers: {e}")
            return [None] * len(worker_ids)

    async def _batch_load_tenants(self, tenant_ids: List[str]) -> List[Optional[Any]]:
        """تحميل دفعة من المستأجرين"""
        if not self.services or not self.services.tenant_service:
            return [None] * len(tenant_ids)

        try:
            tenants = await self.services.tenant_service.get_tenants_by_ids(tenant_ids)
            tenant_map = {tenant.id: tenant for tenant in tenants if tenant}
            return [tenant_map.get(tenant_id) for tenant_id in tenant_ids]
        except Exception as e:
            logger.error(f"Error batch loading tenants: {e}")
            return [None] * len(tenant_ids)

    async def _batch_load_backups(self, backup_ids: List[str]) -> List[Optional[Any]]:
        """تحميل دفعة من النسخ الاحتياطية"""
        if not self.services or not self.services.backup_service:
            return [None] * len(backup_ids)

        try:
            backups = await self.services.backup_service.get_backups_by_ids(backup_ids)
            backup_map = {backup.id: backup for backup in backups if backup}
            return [backup_map.get(backup_id) for backup_id in backup_ids]
        except Exception as e:
            logger.error(f"Error batch loading backups: {e}")
            return [None] * len(backup_ids)

    async def _batch_load_jobs_by_worker(self, worker_ids: List[str]) -> List[List[Any]]:
        """تحميل مهام كل عامل"""
        if not self.services or not self.services.job_service:
            return [[] for _ in worker_ids]

        try:
            # Get all jobs for all workers in one query
            all_jobs = await self.services.job_service.get_jobs_by_worker_ids(worker_ids)

            # Group by worker
            jobs_by_worker: Dict[str, List] = defaultdict(list)
            for job in all_jobs:
                if job.worker_id:
                    jobs_by_worker[job.worker_id].append(job)

            return [jobs_by_worker.get(worker_id, []) for worker_id in worker_ids]
        except Exception as e:
            logger.error(f"Error batch loading jobs by worker: {e}")
            return [[] for _ in worker_ids]

    async def _batch_load_jobs_by_tenant(self, tenant_ids: List[str]) -> List[List[Any]]:
        """تحميل مهام كل مستأجر"""
        if not self.services or not self.services.job_service:
            return [[] for _ in tenant_ids]

        try:
            all_jobs = await self.services.job_service.get_jobs_by_tenant_ids(tenant_ids)

            jobs_by_tenant: Dict[str, List] = defaultdict(list)
            for job in all_jobs:
                if job.tenant_id:
                    jobs_by_tenant[job.tenant_id].append(job)

            return [jobs_by_tenant.get(tenant_id, []) for tenant_id in tenant_ids]
        except Exception as e:
            logger.error(f"Error batch loading jobs by tenant: {e}")
            return [[] for _ in tenant_ids]

    def clear_all(self) -> None:
        """مسح جميع الذاكرة المؤقتة"""
        self.job_loader.clear()
        self.worker_loader.clear()
        self.tenant_loader.clear()
        self.backup_loader.clear()
        self.jobs_by_worker_loader.clear()
        self.jobs_by_tenant_loader.clear()
