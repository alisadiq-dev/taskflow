"""Example: Create a recurring task schedule."""

import asyncio
import httpx


async def main():
    """Example of creating a scheduled task."""
    base_url = "http://localhost:8000/api/v1"
    
    async with httpx.AsyncClient() as client:
        # Create a schedule that runs every 5 minutes
        print("Creating schedule...")
        response = await client.post(
            f"{base_url}/schedules/",
            json={
                "name": "Daily Report",
                "task_type": "email",
                "task_name": "Send Daily Report",
                "schedule_type": "cron",
                "cron_expression": "0 9 * * *",  # Every day at 9 AM
                "task_payload": {
                    "to": "admin@example.com",
                    "subject": "Daily Report",
                },
                "timezone": "UTC",
            }
        )
        
        schedule = response.json()
        print(f"Schedule created: {schedule['id']}")
        print(f"Next run: {schedule['next_run_at']}")


if __name__ == "__main__":
    asyncio.run(main())
