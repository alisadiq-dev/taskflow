"""Test task service."""

import pytest
from taskflow.models.task import TaskPriority


@pytest.mark.asyncio
async def test_create_task(task_service):
    """Test creating a task."""
    task = await task_service.create_task(
        name="Test Task",
        task_type="echo",
        payload={"message": "Hello, World!"},
        priority=TaskPriority.NORMAL,
    )
    
    assert task.id is not None
    assert task.name == "Test Task"
    assert task.task_type == "echo"
    assert task.priority == TaskPriority.NORMAL


@pytest.mark.asyncio
async def test_get_task(task_service):
    """Test retrieving a task."""
    task = await task_service.create_task(
        name="Test Task",
        task_type="echo",
        payload={},
    )
    
    retrieved = await task_service.get_task(task.id)
    assert retrieved.id == task.id
    assert retrieved.name == task.name


@pytest.mark.asyncio
async def test_list_tasks(task_service):
    """Test listing tasks."""
    # Create multiple tasks
    for i in range(3):
        await task_service.create_task(
            name=f"Task {i}",
            task_type="echo",
            payload={},
        )
    
    tasks = await task_service.list_tasks()
    assert len(tasks) >= 3
