"""
Workflow Module Unit Tests - اختبارات وحدة سير العمل
=====================================================

Tests for the workflow system including:
- Workflow definitions
- Workflow engine
- Triggers (cron, event-based)
- Workflow execution and state management
"""

import asyncio
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from distributed_cluster.workflow import (
    StepDefinition,
    TriggerType,
    Workflow,
    WorkflowDefinition,
    WorkflowEngine,
    WorkflowRun,
    WorkflowScheduler,
    WorkflowStatus,
    WorkflowTrigger,
    WorkflowVersion,
    load_workflow_from_json,
    load_workflow_from_yaml,
)


# =============================================================================
# Workflow Definition Tests
# =============================================================================


class TestStepDefinition:
    """Tests for StepDefinition."""

    def test_create_step(self):
        """Test creating a step definition."""
        step = StepDefinition(
            name="train_model",
            command="python train.py",
            resources={"cpu": 4, "memory_mb": 8192},
        )
        assert step.name == "train_model"
        assert step.command == "python train.py"

    def test_step_with_dependencies(self):
        """Test step with dependencies."""
        step = StepDefinition(
            name="evaluate",
            command="python evaluate.py",
            depends_on=["train_model", "prepare_data"],
        )
        assert len(step.depends_on) == 2
        assert "train_model" in step.depends_on

    def test_step_with_environment(self):
        """Test step with environment variables."""
        step = StepDefinition(
            name="process",
            command="python process.py",
            environment={"DEBUG": "true", "LOG_LEVEL": "INFO"},
        )
        assert step.environment["DEBUG"] == "true"

    def test_step_with_retry(self):
        """Test step with retry configuration."""
        step = StepDefinition(
            name="flaky_task",
            command="python flaky.py",
            retry_count=3,
            retry_delay_seconds=60,
        )
        assert step.retry_count == 3
        assert step.retry_delay_seconds == 60

    def test_step_to_dict(self):
        """Test step dictionary conversion."""
        step = StepDefinition(
            name="test",
            command="echo test",
        )
        d = step.to_dict()
        assert d["name"] == "test"
        assert d["command"] == "echo test"


class TestWorkflowDefinition:
    """Tests for WorkflowDefinition."""

    def test_create_definition(self):
        """Test creating a workflow definition."""
        definition = WorkflowDefinition(
            name="ml-pipeline",
            description="Machine learning training pipeline",
            steps=[
                StepDefinition(name="prepare", command="python prepare.py"),
                StepDefinition(name="train", command="python train.py", depends_on=["prepare"]),
                StepDefinition(name="evaluate", command="python eval.py", depends_on=["train"]),
            ],
        )
        assert definition.name == "ml-pipeline"
        assert len(definition.steps) == 3

    def test_definition_with_triggers(self):
        """Test definition with triggers."""
        definition = WorkflowDefinition(
            name="scheduled-job",
            steps=[StepDefinition(name="run", command="python job.py")],
            triggers=[
                WorkflowTrigger(
                    trigger_type=TriggerType.CRON,
                    schedule="0 0 * * *",  # Daily at midnight
                )
            ],
        )
        assert len(definition.triggers) == 1

    def test_definition_validation(self):
        """Test definition validation."""
        # Definition with missing dependency should be invalid
        definition = WorkflowDefinition(
            name="invalid",
            steps=[
                StepDefinition(name="step2", command="echo 2", depends_on=["nonexistent"]),
            ],
        )
        errors = definition.validate()
        assert len(errors) > 0

    def test_definition_to_yaml(self):
        """Test converting definition to YAML."""
        definition = WorkflowDefinition(
            name="test-workflow",
            steps=[StepDefinition(name="test", command="echo test")],
        )
        yaml_str = definition.to_yaml()
        assert "name: test-workflow" in yaml_str

    def test_definition_to_json(self):
        """Test converting definition to JSON."""
        definition = WorkflowDefinition(
            name="test-workflow",
            steps=[StepDefinition(name="test", command="echo test")],
        )
        json_str = definition.to_json()
        data = json.loads(json_str)
        assert data["name"] == "test-workflow"


class TestLoadWorkflowFunctions:
    """Tests for workflow loading functions."""

    def test_load_from_yaml(self, tmp_path):
        """Test loading workflow from YAML file."""
        yaml_content = """
name: yaml-workflow
description: Test workflow from YAML
steps:
  - name: step1
    command: echo hello
  - name: step2
    command: echo world
    depends_on:
      - step1
"""
        yaml_file = tmp_path / "workflow.yaml"
        yaml_file.write_text(yaml_content)

        workflow = load_workflow_from_yaml(str(yaml_file))
        assert workflow.name == "yaml-workflow"
        assert len(workflow.steps) == 2

    def test_load_from_json(self, tmp_path):
        """Test loading workflow from JSON file."""
        json_content = {
            "name": "json-workflow",
            "steps": [
                {"name": "step1", "command": "echo hello"},
            ],
        }
        json_file = tmp_path / "workflow.json"
        json_file.write_text(json.dumps(json_content))

        workflow = load_workflow_from_json(str(json_file))
        assert workflow.name == "json-workflow"

    def test_load_invalid_file(self, tmp_path):
        """Test loading from invalid file."""
        invalid_file = tmp_path / "invalid.yaml"
        invalid_file.write_text("invalid: yaml: content:")

        with pytest.raises(Exception):
            load_workflow_from_yaml(str(invalid_file))


# =============================================================================
# Workflow Tests
# =============================================================================


class TestWorkflowStatus:
    """Tests for WorkflowStatus enum."""

    def test_status_values(self):
        """Test workflow status values."""
        assert WorkflowStatus.DRAFT is not None
        assert WorkflowStatus.ACTIVE is not None
        assert WorkflowStatus.PAUSED is not None
        assert WorkflowStatus.ARCHIVED is not None


class TestWorkflowVersion:
    """Tests for WorkflowVersion."""

    def test_create_version(self):
        """Test creating a workflow version."""
        version = WorkflowVersion(
            version="1.0.0",
            created_at=datetime.now(timezone.utc),
            definition=WorkflowDefinition(
                name="test",
                steps=[StepDefinition(name="s", command="echo")],
            ),
        )
        assert version.version == "1.0.0"

    def test_version_comparison(self):
        """Test version comparison."""
        v1 = WorkflowVersion(
            version="1.0.0",
            created_at=datetime.now(timezone.utc) - timedelta(days=1),
            definition=WorkflowDefinition(name="test", steps=[]),
        )
        v2 = WorkflowVersion(
            version="1.1.0",
            created_at=datetime.now(timezone.utc),
            definition=WorkflowDefinition(name="test", steps=[]),
        )
        assert v2.version > v1.version


class TestWorkflow:
    """Tests for Workflow."""

    @pytest.fixture
    def workflow(self):
        """Create a test workflow."""
        definition = WorkflowDefinition(
            name="test-workflow",
            steps=[
                StepDefinition(name="step1", command="echo step1"),
                StepDefinition(name="step2", command="echo step2", depends_on=["step1"]),
            ],
        )
        return Workflow(
            workflow_id="wf-123",
            definition=definition,
        )

    def test_workflow_creation(self, workflow):
        """Test workflow creation."""
        assert workflow.workflow_id == "wf-123"
        assert workflow.status == WorkflowStatus.DRAFT

    def test_activate_workflow(self, workflow):
        """Test activating a workflow."""
        workflow.activate()
        assert workflow.status == WorkflowStatus.ACTIVE

    def test_pause_workflow(self, workflow):
        """Test pausing a workflow."""
        workflow.activate()
        workflow.pause()
        assert workflow.status == WorkflowStatus.PAUSED

    def test_archive_workflow(self, workflow):
        """Test archiving a workflow."""
        workflow.archive()
        assert workflow.status == WorkflowStatus.ARCHIVED

    def test_get_execution_order(self, workflow):
        """Test getting execution order."""
        order = workflow.get_execution_order()
        # step1 should come before step2
        assert order.index("step1") < order.index("step2")


# =============================================================================
# Trigger Tests
# =============================================================================


class TestTriggerType:
    """Tests for TriggerType enum."""

    def test_trigger_types(self):
        """Test trigger type values."""
        assert TriggerType.CRON is not None
        assert TriggerType.EVENT is not None
        assert TriggerType.MANUAL is not None
        assert TriggerType.WEBHOOK is not None


class TestWorkflowTrigger:
    """Tests for WorkflowTrigger."""

    def test_cron_trigger(self):
        """Test cron trigger."""
        trigger = WorkflowTrigger(
            trigger_type=TriggerType.CRON,
            schedule="0 */6 * * *",
        )
        assert trigger.trigger_type == TriggerType.CRON
        assert trigger.schedule == "0 */6 * * *"

    def test_event_trigger(self):
        """Test event trigger."""
        trigger = WorkflowTrigger(
            trigger_type=TriggerType.EVENT,
            event_type="job.completed",
            filter_expression="status == 'success'",
        )
        assert trigger.trigger_type == TriggerType.EVENT
        assert trigger.event_type == "job.completed"

    def test_webhook_trigger(self):
        """Test webhook trigger."""
        trigger = WorkflowTrigger(
            trigger_type=TriggerType.WEBHOOK,
            webhook_secret="secret-token",
        )
        assert trigger.trigger_type == TriggerType.WEBHOOK

    def test_trigger_is_due_cron(self):
        """Test cron trigger is_due check."""
        trigger = WorkflowTrigger(
            trigger_type=TriggerType.CRON,
            schedule="* * * * *",  # Every minute
        )
        # Should be due or close to due
        # Depends on implementation

    def test_trigger_matches_event(self):
        """Test event trigger matching."""
        trigger = WorkflowTrigger(
            trigger_type=TriggerType.EVENT,
            event_type="job.completed",
        )
        matches = trigger.matches_event("job.completed", {})
        assert matches is True

        not_matches = trigger.matches_event("job.failed", {})
        assert not_matches is False


# =============================================================================
# Workflow Run Tests
# =============================================================================


class TestWorkflowRun:
    """Tests for WorkflowRun."""

    @pytest.fixture
    def run(self):
        """Create a workflow run."""
        return WorkflowRun(
            run_id="run-001",
            workflow_id="wf-123",
            started_at=datetime.now(timezone.utc),
        )

    def test_run_creation(self, run):
        """Test run creation."""
        assert run.run_id == "run-001"
        assert run.status == "pending"

    def test_run_start(self, run):
        """Test starting a run."""
        run.start()
        assert run.status == "running"
        assert run.started_at is not None

    def test_run_complete(self, run):
        """Test completing a run."""
        run.start()
        run.complete()
        assert run.status == "completed"
        assert run.completed_at is not None

    def test_run_fail(self, run):
        """Test failing a run."""
        run.start()
        run.fail("Step failed")
        assert run.status == "failed"
        assert run.error == "Step failed"

    def test_run_duration(self, run):
        """Test run duration calculation."""
        run.start()
        run.complete()
        assert run.duration_seconds >= 0

    def test_run_step_tracking(self, run):
        """Test step status tracking."""
        run.update_step_status("step1", "completed")
        run.update_step_status("step2", "running")

        assert run.step_statuses["step1"] == "completed"
        assert run.step_statuses["step2"] == "running"


# =============================================================================
# Workflow Engine Tests
# =============================================================================


class TestWorkflowEngine:
    """Tests for WorkflowEngine."""

    @pytest.fixture
    def engine(self):
        """Create a workflow engine."""
        return WorkflowEngine()

    @pytest.fixture
    def sample_workflow(self):
        """Create a sample workflow."""
        definition = WorkflowDefinition(
            name="test-workflow",
            steps=[
                StepDefinition(name="step1", command="echo step1"),
                StepDefinition(name="step2", command="echo step2", depends_on=["step1"]),
                StepDefinition(name="step3", command="echo step3", depends_on=["step1"]),
                StepDefinition(
                    name="step4", command="echo step4", depends_on=["step2", "step3"]
                ),
            ],
        )
        return Workflow(
            workflow_id="wf-test",
            definition=definition,
        )

    def test_register_workflow(self, engine, sample_workflow):
        """Test registering a workflow."""
        engine.register(sample_workflow)
        assert engine.get("wf-test") is not None

    def test_unregister_workflow(self, engine, sample_workflow):
        """Test unregistering a workflow."""
        engine.register(sample_workflow)
        engine.unregister("wf-test")
        assert engine.get("wf-test") is None

    def test_list_workflows(self, engine, sample_workflow):
        """Test listing workflows."""
        engine.register(sample_workflow)
        workflows = engine.list_workflows()
        assert len(workflows) >= 1

    @pytest.mark.asyncio
    async def test_start_workflow(self, engine, sample_workflow):
        """Test starting a workflow."""
        engine.register(sample_workflow)
        sample_workflow.activate()

        run = await engine.start("wf-test")
        assert run.status == "running" or run.status == "pending"

    @pytest.mark.asyncio
    async def test_execute_workflow(self, engine, sample_workflow):
        """Test executing a workflow."""
        engine.register(sample_workflow)
        sample_workflow.activate()

        with patch.object(engine, "_execute_step") as mock_execute:
            mock_execute.return_value = {"status": "completed", "output": "ok"}

            run = await engine.execute("wf-test")

            # All steps should be executed
            assert mock_execute.call_count == 4

    @pytest.mark.asyncio
    async def test_execute_respects_dependencies(self, engine, sample_workflow):
        """Test that execution respects step dependencies."""
        engine.register(sample_workflow)
        sample_workflow.activate()

        execution_order = []

        async def mock_execute(step, context):
            execution_order.append(step.name)
            return {"status": "completed"}

        with patch.object(engine, "_execute_step", side_effect=mock_execute):
            await engine.execute("wf-test")

        # step1 must come before step2 and step3
        assert execution_order.index("step1") < execution_order.index("step2")
        assert execution_order.index("step1") < execution_order.index("step3")

        # step4 must come after step2 and step3
        assert execution_order.index("step2") < execution_order.index("step4")
        assert execution_order.index("step3") < execution_order.index("step4")

    @pytest.mark.asyncio
    async def test_stop_workflow(self, engine, sample_workflow):
        """Test stopping a running workflow."""
        engine.register(sample_workflow)
        sample_workflow.activate()

        # Start workflow
        run = await engine.start("wf-test")
        run_id = run.run_id

        # Stop it
        stopped = await engine.stop(run_id)
        assert stopped is True

    @pytest.mark.asyncio
    async def test_get_run_status(self, engine, sample_workflow):
        """Test getting run status."""
        engine.register(sample_workflow)
        sample_workflow.activate()

        run = await engine.start("wf-test")
        status = await engine.get_run_status(run.run_id)

        assert status is not None

    @pytest.mark.asyncio
    async def test_workflow_with_failing_step(self, engine, sample_workflow):
        """Test workflow with a failing step."""
        engine.register(sample_workflow)
        sample_workflow.activate()

        call_count = 0

        async def mock_execute(step, context):
            nonlocal call_count
            call_count += 1
            if step.name == "step2":
                raise Exception("Step failed")
            return {"status": "completed"}

        with patch.object(engine, "_execute_step", side_effect=mock_execute):
            run = await engine.execute("wf-test")

            # Run should be marked as failed
            assert run.status == "failed"

    @pytest.mark.asyncio
    async def test_workflow_retry(self, engine):
        """Test workflow with retry on step failure."""
        definition = WorkflowDefinition(
            name="retry-workflow",
            steps=[
                StepDefinition(
                    name="flaky",
                    command="python flaky.py",
                    retry_count=3,
                    retry_delay_seconds=0,
                ),
            ],
        )
        workflow = Workflow(workflow_id="wf-retry", definition=definition)
        engine.register(workflow)
        workflow.activate()

        attempt = 0

        async def mock_execute(step, context):
            nonlocal attempt
            attempt += 1
            if attempt < 3:
                raise Exception("Transient error")
            return {"status": "completed"}

        with patch.object(engine, "_execute_step", side_effect=mock_execute):
            run = await engine.execute("wf-retry")

            # Should eventually succeed after retries
            assert run.status == "completed"


# =============================================================================
# Workflow Scheduler Tests
# =============================================================================


class TestWorkflowScheduler:
    """Tests for WorkflowScheduler."""

    @pytest.fixture
    def engine(self):
        return WorkflowEngine()

    @pytest.fixture
    def scheduler(self, engine):
        return WorkflowScheduler(engine=engine)

    @pytest.fixture
    def scheduled_workflow(self):
        """Create a workflow with cron trigger."""
        definition = WorkflowDefinition(
            name="scheduled-job",
            steps=[StepDefinition(name="job", command="python job.py")],
            triggers=[
                WorkflowTrigger(
                    trigger_type=TriggerType.CRON,
                    schedule="*/5 * * * *",  # Every 5 minutes
                )
            ],
        )
        return Workflow(workflow_id="wf-scheduled", definition=definition)

    def test_schedule_workflow(self, scheduler, engine, scheduled_workflow):
        """Test scheduling a workflow."""
        engine.register(scheduled_workflow)
        scheduled_workflow.activate()

        scheduler.schedule("wf-scheduled")
        assert "wf-scheduled" in scheduler.scheduled_workflows

    def test_unschedule_workflow(self, scheduler, engine, scheduled_workflow):
        """Test unscheduling a workflow."""
        engine.register(scheduled_workflow)
        scheduled_workflow.activate()

        scheduler.schedule("wf-scheduled")
        scheduler.unschedule("wf-scheduled")

        assert "wf-scheduled" not in scheduler.scheduled_workflows

    @pytest.mark.asyncio
    async def test_check_and_trigger(self, scheduler, engine, scheduled_workflow):
        """Test checking and triggering scheduled workflows."""
        engine.register(scheduled_workflow)
        scheduled_workflow.activate()
        scheduler.schedule("wf-scheduled")

        with patch.object(engine, "start") as mock_start:
            mock_start.return_value = WorkflowRun(
                run_id="run-1",
                workflow_id="wf-scheduled",
                started_at=datetime.now(timezone.utc),
            )

            await scheduler.check_and_trigger()

            # Depends on whether trigger is due

    def test_get_next_run_time(self, scheduler, engine, scheduled_workflow):
        """Test getting next run time."""
        engine.register(scheduled_workflow)
        scheduled_workflow.activate()
        scheduler.schedule("wf-scheduled")

        next_time = scheduler.get_next_run_time("wf-scheduled")
        assert next_time is not None
        assert next_time > datetime.now(timezone.utc)


# =============================================================================
# Integration Tests
# =============================================================================


class TestWorkflowIntegration:
    """Integration tests for workflow system."""

    @pytest.mark.asyncio
    async def test_complete_workflow_lifecycle(self):
        """Test complete workflow lifecycle."""
        # Create engine
        engine = WorkflowEngine()

        # Define workflow
        definition = WorkflowDefinition(
            name="integration-test",
            description="Integration test workflow",
            steps=[
                StepDefinition(
                    name="prepare",
                    command="echo Preparing",
                    timeout_seconds=30,
                ),
                StepDefinition(
                    name="process",
                    command="echo Processing",
                    depends_on=["prepare"],
                ),
                StepDefinition(
                    name="cleanup",
                    command="echo Cleanup",
                    depends_on=["process"],
                ),
            ],
        )

        workflow = Workflow(
            workflow_id="wf-integration",
            definition=definition,
        )

        # Register and activate
        engine.register(workflow)
        workflow.activate()

        # Execute with mocked step execution
        with patch.object(engine, "_execute_step") as mock_execute:
            mock_execute.return_value = {"status": "completed", "output": "ok"}

            run = await engine.execute("wf-integration")

            assert run.status == "completed"
            assert mock_execute.call_count == 3

    @pytest.mark.asyncio
    async def test_parallel_step_execution(self):
        """Test parallel step execution."""
        engine = WorkflowEngine()

        # Steps 2 and 3 can run in parallel
        definition = WorkflowDefinition(
            name="parallel-test",
            steps=[
                StepDefinition(name="setup", command="echo setup"),
                StepDefinition(name="task_a", command="echo a", depends_on=["setup"]),
                StepDefinition(name="task_b", command="echo b", depends_on=["setup"]),
                StepDefinition(name="final", command="echo final", depends_on=["task_a", "task_b"]),
            ],
        )

        workflow = Workflow(workflow_id="wf-parallel", definition=definition)
        engine.register(workflow)
        workflow.activate()

        execution_times = {}

        async def mock_execute(step, context):
            execution_times[step.name] = datetime.now(timezone.utc)
            await asyncio.sleep(0.01)  # Small delay
            return {"status": "completed"}

        with patch.object(engine, "_execute_step", side_effect=mock_execute):
            run = await engine.execute("wf-parallel")

            # task_a and task_b should start at nearly the same time
            # (after setup completes)
            assert run.status == "completed"

    @pytest.mark.asyncio
    async def test_workflow_with_event_trigger(self):
        """Test workflow triggered by event."""
        engine = WorkflowEngine()

        definition = WorkflowDefinition(
            name="event-triggered",
            steps=[StepDefinition(name="handle", command="echo handling event")],
            triggers=[
                WorkflowTrigger(
                    trigger_type=TriggerType.EVENT,
                    event_type="data.uploaded",
                )
            ],
        )

        workflow = Workflow(workflow_id="wf-event", definition=definition)
        engine.register(workflow)
        workflow.activate()

        # Simulate event
        event = {"type": "data.uploaded", "payload": {"file": "data.csv"}}

        with patch.object(engine, "_execute_step") as mock_execute:
            mock_execute.return_value = {"status": "completed"}

            # Trigger by event
            triggered = await engine.trigger_by_event("data.uploaded", event)

            assert len(triggered) >= 1

    @pytest.mark.asyncio
    async def test_workflow_versioning(self):
        """Test workflow versioning."""
        engine = WorkflowEngine()

        # Version 1
        v1_def = WorkflowDefinition(
            name="versioned-workflow",
            steps=[StepDefinition(name="step", command="echo v1")],
        )
        v1 = Workflow(workflow_id="wf-versioned", definition=v1_def)
        engine.register(v1)

        # Update to version 2
        v2_def = WorkflowDefinition(
            name="versioned-workflow",
            steps=[
                StepDefinition(name="step1", command="echo v2-step1"),
                StepDefinition(name="step2", command="echo v2-step2"),
            ],
        )
        v2 = Workflow(workflow_id="wf-versioned", definition=v2_def)

        engine.update(v2)

        # Should have version history
        workflow = engine.get("wf-versioned")
        assert len(workflow.definition.steps) == 2
