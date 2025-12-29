"""Example: Create and monitor a task."""

import asyncio
import httpx


async def main():
    """Example of creating and monitoring a task."""
    base_url = "http://localhost:8000/api/v1"
    
    async with httpx.AsyncClient() as client:
        # Create a task
        print("Creating task...")
        response = await client.post(
            f"{base_url}/tasks/",
            json={
                "name": "Example Echo Task",
                "task_type": "echo",
                "payload": {"message": "Hello from TaskFlow!"},
                "priority": "normal",
            }
        )
        
        task = response.json()
        task_id = task["id"]
        print(f"Task created: {task_id}")
        print(f"Status: {task['status']}")
        
        # Poll for completion
        print("\nWaiting for task to complete...")
        for _ in range(30):
            response = await client.get(f"{base_url}/tasks/{task_id}")
            task = response.json()
            
            print(f"Progress: {task['progress']*100:.0f}% - {task['status']}")
            
            if task["status"] in ["success", "failed", "cancelled"]:
                break
            
            await asyncio.sleep(1)
        
        print(f"\nFinal status: {task['status']}")
        if task["status"] == "success":
            print("Task completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
