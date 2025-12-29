"""Example: Create a webhook for task notifications."""

import asyncio
import httpx


async def main():
    """Example of creating a webhook."""
    base_url = "http://localhost:8000/api/v1"
    
    async with httpx.AsyncClient() as client:
        # Create a webhook that triggers on task completion
        print("Creating webhook...")
        response = await client.post(
            f"{base_url}/webhooks/",
            json={
                "name": "Task Completion Webhook",
                "url": "https://webhook.site/your-unique-url",
                "events": [
                    "task.success",
                    "task.failed",
                ],
                "secret": "my-webhook-secret",
            }
        )
        
        webhook = response.json()
        print(f"Webhook created: {webhook['id']}")
        print(f"URL: {webhook['url']}")
        print(f"Events: {webhook['events']}")


if __name__ == "__main__":
    asyncio.run(main())
