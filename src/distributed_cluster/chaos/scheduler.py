# -*- coding: utf-8 -*-
"""
Chaos Scheduler for NebulaCompute.

Schedules and manages chaos experiments including
Game Days and continuous chaos.

جدولة تجارب الفوضى.
"""

import asyncio
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from .engine import ChaosEngine, ExperimentStatus

logger = logging.getLogger(__name__)


class ScheduleType(str, Enum):
    """Schedule type."""

    ONE_TIME = "one_time"
    RECURRING = "recurring"
    CONTINUOUS = "continuous"


class RecurrencePattern(str, Enum):
    """Recurrence pattern."""

    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


@dataclass
class Schedule:
    """
    Experiment schedule.

    جدولة التجربة.
    """

    schedule_id: str
    experiment_id: str
    schedule_type: ScheduleType
    start_time: datetime
    end_time: Optional[datetime] = None
    recurrence: Optional[RecurrencePattern] = None
    enabled: bool = True
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    run_count: int = 0
    max_runs: Optional[int] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def calculate_next_run(self) -> Optional[datetime]:
        """Calculate next run time."""
        if self.schedule_type == ScheduleType.ONE_TIME:
            return self.start_time if not self.last_run else None

        if not self.last_run:
            return self.start_time

        if self.recurrence == RecurrencePattern.HOURLY:
            return self.last_run + timedelta(hours=1)
        elif self.recurrence == RecurrencePattern.DAILY:
            return self.last_run + timedelta(days=1)
        elif self.recurrence == RecurrencePattern.WEEKLY:
            return self.last_run + timedelta(weeks=1)
        elif self.recurrence == RecurrencePattern.MONTHLY:
            # Approximate month as 30 days
            return self.last_run + timedelta(days=30)

        return None

    def should_run(self, now: datetime) -> bool:
        """Check if schedule should run."""
        if not self.enabled:
            return False

        if self.max_runs and self.run_count >= self.max_runs:
            return False

        if self.end_time and now > self.end_time:
            return False

        next_run = self.next_run or self.calculate_next_run()
        return next_run is not None and now >= next_run

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "schedule_id": self.schedule_id,
            "experiment_id": self.experiment_id,
            "schedule_type": self.schedule_type.value,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "recurrence": self.recurrence.value if self.recurrence else None,
            "enabled": self.enabled,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "run_count": self.run_count,
            "max_runs": self.max_runs,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class GameDay:
    """
    Chaos Game Day definition.

    يوم لعبة الفوضى - سلسلة تجارب مخططة.
    """

    game_day_id: str
    name: str
    description: str
    experiments: List[str]  # Experiment IDs in order
    scheduled_start: datetime
    estimated_duration_hours: float
    status: str = "scheduled"
    created_by: Optional[str] = None
    participants: List[str] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    results: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "game_day_id": self.game_day_id,
            "name": self.name,
            "description": self.description,
            "experiments": self.experiments,
            "scheduled_start": self.scheduled_start.isoformat(),
            "estimated_duration_hours": self.estimated_duration_hours,
            "status": self.status,
            "created_by": self.created_by,
            "participants": self.participants,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "results": self.results,
            "metadata": self.metadata,
        }


class ChaosScheduler:
    """
    Schedules and runs chaos experiments.

    جدولة وتشغيل تجارب الفوضى.

    Features:
    - One-time and recurring schedules
    - Continuous chaos mode
    - Game Day management
    - Maintenance window awareness
    - Random experiment selection
    """

    def __init__(
        self,
        chaos_engine: ChaosEngine,
        check_interval_seconds: float = 60.0,
        maintenance_windows: Optional[List[Dict[str, Any]]] = None,
        enable_continuous_chaos: bool = False,
        continuous_chaos_interval: int = 3600,
    ):
        """
        Initialize Chaos Scheduler.

        Args:
            chaos_engine: Chaos engine instance
            check_interval_seconds: How often to check schedules
            maintenance_windows: Time windows to avoid chaos
            enable_continuous_chaos: Enable continuous random chaos
            continuous_chaos_interval: Interval for continuous chaos
        """
        self.engine = chaos_engine
        self.check_interval = check_interval_seconds
        self.maintenance_windows = maintenance_windows or []
        self.continuous_chaos = enable_continuous_chaos
        self.continuous_interval = continuous_chaos_interval

        # State
        self._schedules: Dict[str, Schedule] = {}
        self._game_days: Dict[str, GameDay] = {}
        self._running = False
        self._scheduler_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

        # Statistics
        self._stats = {
            "total_scheduled_runs": 0,
            "successful_runs": 0,
            "skipped_runs": 0,
            "game_days_completed": 0,
        }

    async def start(self) -> None:
        """Start the scheduler."""
        if self._running:
            return

        self._running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info("Chaos Scheduler started")

    async def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False

        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass

        logger.info("Chaos Scheduler stopped")

    async def _scheduler_loop(self) -> None:
        """Main scheduler loop."""
        while self._running:
            try:
                now = datetime.utcnow()

                # Check maintenance windows
                if self._in_maintenance_window(now):
                    logger.debug("In maintenance window, skipping chaos")
                    await asyncio.sleep(self.check_interval)
                    continue

                # Process schedules
                await self._process_schedules(now)

                # Continuous chaos
                if self.continuous_chaos:
                    await self._maybe_run_continuous_chaos(now)

                await asyncio.sleep(self.check_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                await asyncio.sleep(self.check_interval)

    async def _process_schedules(self, now: datetime) -> None:
        """Process due schedules."""
        async with self._lock:
            for schedule in self._schedules.values():
                if schedule.should_run(now):
                    await self._run_scheduled_experiment(schedule)

    async def _run_scheduled_experiment(self, schedule: Schedule) -> None:
        """Run a scheduled experiment."""
        self._stats["total_scheduled_runs"] += 1

        try:
            result = await self.engine.run_experiment(
                schedule.experiment_id,
                wait=True,
            )

            schedule.last_run = datetime.utcnow()
            schedule.run_count += 1
            schedule.next_run = schedule.calculate_next_run()

            if result and result.success:
                self._stats["successful_runs"] += 1
            else:
                self._stats["skipped_runs"] += 1

        except Exception as e:
            logger.error(f"Failed to run scheduled experiment: {e}")
            self._stats["skipped_runs"] += 1

    async def _maybe_run_continuous_chaos(self, now: datetime) -> None:
        """Maybe run continuous chaos."""
        # Check if enough time has passed since last continuous run
        last_continuous = getattr(self, "_last_continuous_run", None)

        if last_continuous:
            elapsed = (now - last_continuous).total_seconds()
            if elapsed < self.continuous_interval:
                return

        # Select random experiment
        experiments = await self.engine.list_experiments(
            status=ExperimentStatus.SCHEDULED
        )

        if experiments:
            experiment = random.choice(experiments)
            logger.info(f"Continuous chaos: running {experiment.name}")

            try:
                await self.engine.run_experiment(experiment.experiment_id, wait=False)
            except Exception as e:
                logger.error(f"Continuous chaos failed: {e}")

        self._last_continuous_run = now

    def _in_maintenance_window(self, now: datetime) -> bool:
        """Check if currently in maintenance window."""
        for window in self.maintenance_windows:
            start_hour = window.get("start_hour", 0)
            end_hour = window.get("end_hour", 0)
            days = window.get("days", list(range(7)))

            if now.weekday() in days:
                if start_hour <= now.hour < end_hour:
                    return True

        return False

    async def create_schedule(
        self,
        experiment_id: str,
        schedule_type: ScheduleType,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        recurrence: Optional[RecurrencePattern] = None,
        max_runs: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Schedule:
        """
        Create an experiment schedule.

        إنشاء جدولة تجربة.
        """
        import uuid

        schedule = Schedule(
            schedule_id=str(uuid.uuid4()),
            experiment_id=experiment_id,
            schedule_type=schedule_type,
            start_time=start_time,
            end_time=end_time,
            recurrence=recurrence,
            max_runs=max_runs,
            metadata=metadata or {},
        )

        schedule.next_run = schedule.calculate_next_run()

        async with self._lock:
            self._schedules[schedule.schedule_id] = schedule

        logger.info(f"Created schedule for experiment {experiment_id}")
        return schedule

    async def delete_schedule(self, schedule_id: str) -> bool:
        """Delete a schedule."""
        async with self._lock:
            if schedule_id in self._schedules:
                del self._schedules[schedule_id]
                return True
        return False

    async def pause_schedule(self, schedule_id: str) -> bool:
        """Pause a schedule."""
        schedule = self._schedules.get(schedule_id)
        if schedule:
            schedule.enabled = False
            return True
        return False

    async def resume_schedule(self, schedule_id: str) -> bool:
        """Resume a schedule."""
        schedule = self._schedules.get(schedule_id)
        if schedule:
            schedule.enabled = True
            return True
        return False

    async def get_schedule(self, schedule_id: str) -> Optional[Schedule]:
        """Get a schedule by ID."""
        return self._schedules.get(schedule_id)

    async def list_schedules(self) -> List[Schedule]:
        """List all schedules."""
        return list(self._schedules.values())

    async def create_game_day(
        self,
        name: str,
        description: str,
        experiments: List[str],
        scheduled_start: datetime,
        estimated_duration_hours: float,
        created_by: Optional[str] = None,
        participants: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> GameDay:
        """
        Create a Chaos Game Day.

        إنشاء يوم لعبة الفوضى.
        """
        import uuid

        game_day = GameDay(
            game_day_id=str(uuid.uuid4()),
            name=name,
            description=description,
            experiments=experiments,
            scheduled_start=scheduled_start,
            estimated_duration_hours=estimated_duration_hours,
            created_by=created_by,
            participants=participants or [],
            metadata=metadata or {},
        )

        async with self._lock:
            self._game_days[game_day.game_day_id] = game_day

        logger.info(f"Created Game Day: {name} with {len(experiments)} experiments")
        return game_day

    async def start_game_day(
        self,
        game_day_id: str,
    ) -> bool:
        """
        Start a Game Day.

        بدء يوم لعبة الفوضى.
        """
        game_day = self._game_days.get(game_day_id)
        if not game_day:
            return False

        game_day.status = "running"
        game_day.started_at = datetime.utcnow()
        game_day.results = {"experiments": {}}

        logger.info(f"Starting Game Day: {game_day.name}")

        # Run experiments in order
        for experiment_id in game_day.experiments:
            try:
                result = await self.engine.run_experiment(experiment_id, wait=True)
                game_day.results["experiments"][experiment_id] = (
                    result.to_dict() if result else None
                )
            except Exception as e:
                logger.error(f"Game Day experiment failed: {e}")
                game_day.results["experiments"][experiment_id] = {"error": str(e)}

        game_day.status = "completed"
        game_day.completed_at = datetime.utcnow()
        self._stats["game_days_completed"] += 1

        logger.info(f"Game Day completed: {game_day.name}")
        return True

    async def cancel_game_day(self, game_day_id: str) -> bool:
        """Cancel a Game Day."""
        game_day = self._game_days.get(game_day_id)
        if not game_day:
            return False

        game_day.status = "cancelled"
        game_day.completed_at = datetime.utcnow()
        return True

    async def get_game_day(self, game_day_id: str) -> Optional[GameDay]:
        """Get a Game Day by ID."""
        return self._game_days.get(game_day_id)

    async def list_game_days(self) -> List[GameDay]:
        """List all Game Days."""
        return list(self._game_days.values())

    async def get_statistics(self) -> Dict[str, Any]:
        """Get scheduler statistics."""
        return {
            **self._stats,
            "active_schedules": len([s for s in self._schedules.values() if s.enabled]),
            "total_schedules": len(self._schedules),
            "upcoming_game_days": len(
                [g for g in self._game_days.values() if g.status == "scheduled"]
            ),
            "continuous_chaos_enabled": self.continuous_chaos,
            "running": self._running,
        }

    async def shutdown(self) -> None:
        """Shutdown scheduler."""
        await self.stop()
        logger.info("Chaos Scheduler shutdown complete")
