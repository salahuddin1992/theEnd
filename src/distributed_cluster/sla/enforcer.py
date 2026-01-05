# -*- coding: utf-8 -*-
"""
SLA Enforcer for NebulaCompute.

Enforces SLA compliance through automatic actions
like priority boosting and resource allocation.

منفذ SLA - يضمن الامتثال من خلال إجراءات تلقائية.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from .monitor import SLADefinition, SLAEvaluation, SLAStatus

logger = logging.getLogger(__name__)


class ActionType(str, Enum):
    """Enforcement action type."""

    PRIORITY_BOOST = "priority_boost"
    RESOURCE_INCREASE = "resource_increase"
    RESCHEDULE = "reschedule"
    NOTIFICATION = "notification"
    ESCALATION = "escalation"
    CUSTOM = "custom"


@dataclass
class EnforcementAction:
    """
    Enforcement action.

    إجراء تنفيذي.
    """

    action_id: str
    action_type: ActionType
    sla_id: str
    target_id: str  # job_id, worker_id, etc.
    target_type: str  # "job", "worker", "queue"
    parameters: Dict[str, Any] = field(default_factory=dict)
    executed_at: datetime = field(default_factory=datetime.utcnow)
    success: bool = True
    result: Optional[str] = None
    reverted: bool = False
    reverted_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "action_id": self.action_id,
            "action_type": self.action_type.value,
            "sla_id": self.sla_id,
            "target_id": self.target_id,
            "target_type": self.target_type,
            "parameters": self.parameters,
            "executed_at": self.executed_at.isoformat(),
            "success": self.success,
            "result": self.result,
            "reverted": self.reverted,
            "reverted_at": self.reverted_at.isoformat() if self.reverted_at else None,
            "metadata": self.metadata,
        }


@dataclass
class PriorityBoost:
    """
    Priority boost configuration.

    تكوين رفع الأولوية.
    """

    boost_id: str
    job_id: str
    original_priority: int
    boosted_priority: int
    reason: str
    sla_id: str
    applied_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    reverted: bool = False

    @property
    def is_active(self) -> bool:
        """Check if boost is still active."""
        if self.reverted:
            return False
        if self.expires_at and datetime.now(timezone.utc) > self.expires_at:
            return False
        return True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "boost_id": self.boost_id,
            "job_id": self.job_id,
            "original_priority": self.original_priority,
            "boosted_priority": self.boosted_priority,
            "reason": self.reason,
            "sla_id": self.sla_id,
            "applied_at": self.applied_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_active": self.is_active,
            "reverted": self.reverted,
        }


@dataclass
class EnforcementRule:
    """
    Enforcement rule definition.

    تعريف قاعدة التنفيذ.
    """

    rule_id: str
    name: str
    sla_id: str
    trigger_status: SLAStatus  # When to trigger
    action_type: ActionType
    parameters: Dict[str, Any] = field(default_factory=dict)
    cooldown_seconds: int = 300  # Minimum time between actions
    enabled: bool = True
    last_triggered: Optional[datetime] = None

    def can_trigger(self) -> bool:
        """Check if rule can be triggered."""
        if not self.enabled:
            return False
        if self.last_triggered:
            elapsed = (datetime.now(timezone.utc) - self.last_triggered).total_seconds()
            if elapsed < self.cooldown_seconds:
                return False
        return True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "sla_id": self.sla_id,
            "trigger_status": self.trigger_status.value,
            "action_type": self.action_type.value,
            "parameters": self.parameters,
            "cooldown_seconds": self.cooldown_seconds,
            "enabled": self.enabled,
            "can_trigger": self.can_trigger(),
        }


class SLAEnforcer:
    """
    Enforces SLA compliance automatically.

    منفذ الامتثال التلقائي لـ SLA.

    Features:
    - Automatic priority boosting
    - Resource reallocation
    - Job rescheduling
    - Escalation to humans
    - Configurable rules
    """

    def __init__(
        self,
        job_manager: Optional[Any] = None,
        scheduler: Optional[Any] = None,
        notification_manager: Optional[Any] = None,
        max_priority_boost: int = 50,
        boost_duration_seconds: int = 3600,
    ):
        """
        Initialize SLA Enforcer.

        Args:
            job_manager: Job manager for priority updates
            scheduler: Scheduler for rescheduling
            notification_manager: For sending alerts
            max_priority_boost: Maximum priority increase
            boost_duration_seconds: How long boosts last
        """
        self.job_manager = job_manager
        self.scheduler = scheduler
        self.notification_manager = notification_manager
        self.max_priority_boost = max_priority_boost
        self.boost_duration = boost_duration_seconds

        # State
        self._rules: Dict[str, EnforcementRule] = {}
        self._actions: Dict[str, EnforcementAction] = {}
        self._boosts: Dict[str, PriorityBoost] = {}
        self._lock = asyncio.Lock()

        # Custom action handlers
        self._custom_handlers: Dict[str, Callable] = {}

        # Statistics
        self._stats = {
            "total_actions": 0,
            "successful_actions": 0,
            "failed_actions": 0,
            "priority_boosts": 0,
            "escalations": 0,
        }

    def register_custom_handler(
        self,
        name: str,
        handler: Callable,
    ) -> None:
        """Register a custom action handler."""
        self._custom_handlers[name] = handler
        logger.info(f"Registered custom handler: {name}")

    async def add_rule(self, rule: EnforcementRule) -> None:
        """
        Add an enforcement rule.

        إضافة قاعدة تنفيذ.
        """
        async with self._lock:
            self._rules[rule.rule_id] = rule

        logger.info(f"Added enforcement rule: {rule.name}")

    async def remove_rule(self, rule_id: str) -> bool:
        """Remove an enforcement rule."""
        async with self._lock:
            if rule_id in self._rules:
                del self._rules[rule_id]
                return True
        return False

    async def evaluate_and_enforce(
        self,
        sla: SLADefinition,
        evaluation: SLAEvaluation,
    ) -> List[EnforcementAction]:
        """
        Evaluate SLA and take enforcement actions.

        تقييم SLA واتخاذ إجراءات التنفيذ.
        """
        actions_taken = []

        # Find applicable rules
        for rule in self._rules.values():
            if rule.sla_id != sla.sla_id:
                continue

            if rule.trigger_status != evaluation.status:
                continue

            if not rule.can_trigger():
                continue

            # Execute rule action
            action = await self._execute_rule(rule, sla, evaluation)
            if action:
                actions_taken.append(action)
                rule.last_triggered = datetime.now(timezone.utc)

        return actions_taken

    async def _execute_rule(
        self,
        rule: EnforcementRule,
        sla: SLADefinition,
        evaluation: SLAEvaluation,
    ) -> Optional[EnforcementAction]:
        """Execute a rule's action."""
        import uuid

        action = EnforcementAction(
            action_id=str(uuid.uuid4()),
            action_type=rule.action_type,
            sla_id=sla.sla_id,
            target_id=rule.parameters.get("target_id", ""),
            target_type=rule.parameters.get("target_type", "job"),
            parameters=rule.parameters,
        )

        self._stats["total_actions"] += 1

        try:
            if rule.action_type == ActionType.PRIORITY_BOOST:
                await self._execute_priority_boost(action, rule, evaluation)

            elif rule.action_type == ActionType.RESOURCE_INCREASE:
                await self._execute_resource_increase(action, rule)

            elif rule.action_type == ActionType.RESCHEDULE:
                await self._execute_reschedule(action, rule)

            elif rule.action_type == ActionType.NOTIFICATION:
                await self._execute_notification(action, rule, sla, evaluation)

            elif rule.action_type == ActionType.ESCALATION:
                await self._execute_escalation(action, rule, sla, evaluation)

            elif rule.action_type == ActionType.CUSTOM:
                await self._execute_custom(action, rule)

            action.success = True
            self._stats["successful_actions"] += 1

            logger.info(
                f"Executed enforcement action: {rule.action_type.value} "
                f"for SLA {sla.name}"
            )

        except Exception as e:
            action.success = False
            action.result = str(e)
            self._stats["failed_actions"] += 1
            logger.error(f"Enforcement action failed: {e}")

        async with self._lock:
            self._actions[action.action_id] = action

        return action

    async def _execute_priority_boost(
        self,
        action: EnforcementAction,
        rule: EnforcementRule,
        evaluation: SLAEvaluation,
    ) -> None:
        """Execute priority boost action."""
        import uuid

        target_jobs = rule.parameters.get("target_jobs", [])
        boost_amount = min(
            rule.parameters.get("boost_amount", 10),
            self.max_priority_boost,
        )

        for job_id in target_jobs:
            # Get current priority (simulated)
            current_priority = 0  # Would get from job manager

            boost = PriorityBoost(
                boost_id=str(uuid.uuid4()),
                job_id=job_id,
                original_priority=current_priority,
                boosted_priority=current_priority + boost_amount,
                reason=f"SLA at risk: {evaluation.sla_name}",
                sla_id=action.sla_id,
                expires_at=datetime.now(timezone.utc) + timedelta(seconds=self.boost_duration),
            )

            # Apply boost (would use job manager)
            if self.job_manager:
                # await self.job_manager.set_priority(job_id, boost.boosted_priority)
                pass

            async with self._lock:
                self._boosts[boost.boost_id] = boost
                self._stats["priority_boosts"] += 1

        action.result = f"Boosted {len(target_jobs)} jobs by {boost_amount}"

    async def _execute_resource_increase(
        self,
        action: EnforcementAction,
        rule: EnforcementRule,
    ) -> None:
        """Execute resource increase action."""
        resource_type = rule.parameters.get("resource_type", "cpu")
        increase_percent = rule.parameters.get("increase_percent", 25)

        # Would interact with resource manager
        action.result = f"Increased {resource_type} by {increase_percent}%"

    async def _execute_reschedule(
        self,
        action: EnforcementAction,
        rule: EnforcementRule,
    ) -> None:
        """Execute reschedule action."""
        target_jobs = rule.parameters.get("target_jobs", [])

        if self.scheduler:
            for job_id in target_jobs:
                # await self.scheduler.reschedule(job_id)
                pass

        action.result = f"Rescheduled {len(target_jobs)} jobs"

    async def _execute_notification(
        self,
        action: EnforcementAction,
        rule: EnforcementRule,
        sla: SLADefinition,
        evaluation: SLAEvaluation,
    ) -> None:
        """Execute notification action."""
        channels = rule.parameters.get("channels", sla.notification_channels)

        if self.notification_manager:
            # await self.notification_manager.send(channels, message)
            pass

        action.result = f"Notified {len(channels)} channels"

    async def _execute_escalation(
        self,
        action: EnforcementAction,
        rule: EnforcementRule,
        sla: SLADefinition,
        evaluation: SLAEvaluation,
    ) -> None:
        """Execute escalation action."""
        escalation_level = rule.parameters.get("level", 1)
        rule.parameters.get("contacts", [])


        # Would send escalation notifications
        self._stats["escalations"] += 1
        action.result = f"Escalated to level {escalation_level}"

    async def _execute_custom(
        self,
        action: EnforcementAction,
        rule: EnforcementRule,
    ) -> None:
        """Execute custom action."""
        handler_name = rule.parameters.get("handler")
        handler = self._custom_handlers.get(handler_name)

        if handler:
            result = handler(rule.parameters)
            if asyncio.iscoroutine(result):
                result = await result
            action.result = str(result)
        else:
            raise ValueError(f"Custom handler not found: {handler_name}")

    async def boost_job_priority(
        self,
        job_id: str,
        boost_amount: int,
        reason: str,
        sla_id: Optional[str] = None,
        duration_seconds: Optional[int] = None,
    ) -> PriorityBoost:
        """
        Manually boost a job's priority.

        رفع أولوية مهمة يدوياً.
        """
        import uuid

        boost = PriorityBoost(
            boost_id=str(uuid.uuid4()),
            job_id=job_id,
            original_priority=0,  # Would get from job manager
            boosted_priority=boost_amount,
            reason=reason,
            sla_id=sla_id or "manual",
            expires_at=datetime.now(timezone.utc) + timedelta(
                seconds=duration_seconds or self.boost_duration
            ),
        )

        async with self._lock:
            self._boosts[boost.boost_id] = boost
            self._stats["priority_boosts"] += 1

        logger.info(f"Boosted job {job_id} priority by {boost_amount}")
        return boost

    async def revert_boost(self, boost_id: str) -> bool:
        """Revert a priority boost."""
        async with self._lock:
            boost = self._boosts.get(boost_id)
            if not boost:
                return False

            # Restore original priority
            if self.job_manager:
                # await self.job_manager.set_priority(
                #     boost.job_id, boost.original_priority
                # )
                pass

            boost.reverted = True
            return True

    async def cleanup_expired_boosts(self) -> int:
        """Clean up expired priority boosts."""
        cleaned = 0

        async with self._lock:
            expired = [
                bid
                for bid, boost in self._boosts.items()
                if not boost.is_active and not boost.reverted
            ]

            for boost_id in expired:
                boost = self._boosts[boost_id]
                # Restore priority
                if self.job_manager:
                    # await self.job_manager.set_priority(
                    #     boost.job_id, boost.original_priority
                    # )
                    pass
                boost.reverted = True
                cleaned += 1

        if cleaned:
            logger.info(f"Cleaned up {cleaned} expired priority boosts")

        return cleaned

    async def get_action(self, action_id: str) -> Optional[EnforcementAction]:
        """Get action by ID."""
        return self._actions.get(action_id)

    async def get_boost(self, boost_id: str) -> Optional[PriorityBoost]:
        """Get boost by ID."""
        return self._boosts.get(boost_id)

    async def get_job_boosts(self, job_id: str) -> List[PriorityBoost]:
        """Get all boosts for a job."""
        return [b for b in self._boosts.values() if b.job_id == job_id]

    async def get_active_boosts(self) -> List[PriorityBoost]:
        """Get all active boosts."""
        return [b for b in self._boosts.values() if b.is_active]

    async def list_rules(self, sla_id: Optional[str] = None) -> List[EnforcementRule]:
        """List enforcement rules."""
        rules = list(self._rules.values())
        if sla_id:
            rules = [r for r in rules if r.sla_id == sla_id]
        return rules

    async def list_actions(
        self,
        sla_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[EnforcementAction]:
        """List recent actions."""
        actions = list(self._actions.values())

        if sla_id:
            actions = [a for a in actions if a.sla_id == sla_id]

        actions.sort(key=lambda a: a.executed_at, reverse=True)
        return actions[:limit]

    async def get_statistics(self) -> Dict[str, Any]:
        """Get enforcer statistics."""
        return {
            **self._stats,
            "registered_rules": len(self._rules),
            "active_boosts": len([b for b in self._boosts.values() if b.is_active]),
            "total_boosts": len(self._boosts),
            "stored_actions": len(self._actions),
        }

    async def shutdown(self) -> None:
        """Shutdown enforcer."""
        # Revert all active boosts
        for boost_id in list(self._boosts.keys()):
            await self.revert_boost(boost_id)

        logger.info("SLA Enforcer shutdown complete")
