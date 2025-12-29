#  TaskFlow - Distributed Task Processing System

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green.svg)](https://fastapi.tiangolo.com/)
[![Celery](https://img.shields.io/badge/Celery-5.3+-orange.svg)](https://docs.celeryq.dev/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A production-ready, enterprise-grade distributed task processing system built with **FastAPI** and **Celery**. TaskFlow provides a robust infrastructure for handling background jobs, scheduled tasks, and complex workflows with real-time progress tracking.

##  Features

### Core Capabilities
- ** Task Queue Management** - Submit, cancel, retry, and monitor tasks
- ** Priority Queues** - Critical, high, normal, and low priority levels
- ** Task Scheduling** - Cron-like recurring tasks with APScheduler
- ** Progress Tracking** - Real-time task progress via WebSocket
- ** Dead Letter Queue** - Automatic handling of failed tasks
- ** Task Dependencies** - DAG-based task workflows
- ** Monitoring Dashboard** - Task metrics and analytics API
- **Webhook Notifications** - Task completion callbacks

### Production Features
- ** JWT Authentication** - Secure API access
- ** Multi-tenancy Support** - Isolated task queues per tenant
- ** Structured Logging** - JSON logging with correlation IDs
- ** Health Checks** - Liveness and readiness probes
- ** Docker Ready** - Complete containerization
- **CI/CD Pipeline** - GitHub Actions workflow
- **📖API Documentation** - Interactive Swagger UI

##  Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                           Load Balancer                              │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────────┐
│                         FastAPI Application                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐ │
│  │  REST API   │  │  WebSocket  │  │  Scheduler  │  │   Health   │ │
│  │  Endpoints  │  │   Handler   │  │   Service   │  │   Checks   │ │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └────────────┘ │
└─────────┼────────────────┼────────────────┼─────────────────────────┘
          │                │                │
┌─────────▼────────────────▼────────────────▼─────────────────────────┐
│                            Redis                                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │
│  │   Broker    │  │   Results   │  │   Pub/Sub   │                  │
│  │   Queue     │  │   Backend   │  │   Channel   │                  │
│  └─────────────┘  └─────────────┘  └─────────────┘                  │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────────┐
│                        Celery Workers                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐ │
│  │   Worker    │  │   Worker    │  │   Worker    │  │   Beat     │ │
│  │   (CPU)     │  │   (I/O)     │  │   (Email)   │  │ (Scheduler)│ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────────┐
│                         PostgreSQL                                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │
│  │   Tasks     │  │  Schedules  │  │  Workflows  │                  │
│  └─────────────┘  └─────────────┘  └─────────────┘                  │
└─────────────────────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Docker & Docker Compose
- Redis
- PostgreSQL

### Using Docker (Recommended)

```bash
# Clone the repository
git clone https://github.com/yourusername/taskflow.git
cd taskflow

# Copy environment variables
cp .env.example .env

# Start all services
docker-compose up -d

# Run database migrations
docker-compose exec api alembic upgrade head

# Access the API documentation
open http://localhost:8000/docs
```

### Local Development


### Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Set up environment variables
cp .env.example .env

# Start Redis and PostgreSQL using Docker
docker-compose up -d postgres redis

# Run database migrations
alembic upgrade head

# Start the FastAPI server
uvicorn taskflow.main:app --reload --host 0.0.0.0 --port 8000

# In another terminal, start Celery worker
celery -A taskflow.worker.celery_app worker --loglevel=info

# In another terminal, start Celery beat (scheduler)
celery -A taskflow.worker.celery_app beat --loglevel=info

# Optional: Start Flower monitoring
celery -A taskflow.worker.celery_app flower --port=5555
```

## 📖 API Documentation

Once running, interactive API documentation is available at:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Endpoints Overview

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/tasks` | Submit a new task |
| `GET` | `/api/v1/tasks` | List all tasks |
| `GET` | `/api/v1/tasks/{task_id}` | Get task details |
| `POST` | `/api/v1/tasks/{task_id}/cancel` | Cancel a task |
| `POST` | `/api/v1/tasks/{task_id}/retry` | Retry a failed task |
| `POST` | `/api/v1/schedules` | Create a scheduled task |
| `GET` | `/api/v1/schedules` | List all schedules |
| `POST` | `/api/v1/workflows` | Create a task workflow |
| `POST` | `/api/v1/webhooks` | Register a webhook |
| `GET` | `/api/v1/monitoring/metrics` | Get task metrics |
| `WS` | `/ws/tasks/{task_id}` | Real-time task progress |

### Example: Submit a Task

```bash
curl -X POST "http://localhost:8000/api/v1/tasks" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Process Data",
    "task_type": "compute",
    "payload": {
      "operation": "fibonacci",
      "n": 30
    },
    "priority": "high"
  }'
```

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Process Data",
  "task_type": "compute",
  "status": "queued",
  "priority": "high",
  "progress": 0.0,
  "created_at": "2025-12-29T10:00:00Z"
}
```

### Example: WebSocket Connection

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/tasks/550e8400-e29b-41d4-a716-446655440000');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(`Progress: ${data.progress * 100}% - ${data.message}`);
};
```

### Example: Create Scheduled Task

```bash
curl -X POST "http://localhost:8000/api/v1/schedules" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Daily Backup",
    "task_type": "compute",
    "task_name": "Run Backup",
    "schedule_type": "cron",
    "cron_expression": "0 2 * * *",
    "task_payload": {},
    "timezone": "UTC"
  }'
```

## 🔧 Configuration

All configuration is done via environment variables. See `.env.example` for all available options.

| Variable | Description | Default |
|----------|-------------|---------|
| `TASKFLOW_DATABASE_URL` | PostgreSQL connection URL | `postgresql+asyncpg://...` |
| `TASKFLOW_REDIS_URL` | Redis connection URL | `redis://localhost:6379/0` |
| `TASKFLOW_SECRET_KEY` | JWT signing key | (required) |
| `TASKFLOW_CELERY_BROKER_URL` | Celery broker URL | `redis://localhost:6379/1` |
| `TASKFLOW_LOG_LEVEL` | Logging level | `INFO` |
| `TASKFLOW_SCHEDULER_ENABLED` | Enable APScheduler | `true` |

##  Monitoring

### Flower Dashboard
Access the Flower monitoring dashboard at `http://localhost:5555` to:
- View active workers and their status
- Monitor task queues and priorities
- Inspect task details and results
- View task execution graphs

### Metrics Endpoint
```bash
curl http://localhost:8000/api/v1/monitoring/metrics
```

**Response:**
```json
{
  "total": 1523,
  "by_status": {
    "pending": 12,
    "queued": 8,
    "running": 5,
    "success": 1450,
    "failed": 45,
    "cancelled": 3
  },
  "by_priority": {
    "critical": 3,
    "high": 125,
    "normal": 1200,
    "low": 195
  },
  "average_duration_seconds": 12.34
}
```

### Health Checks

```bash
# Liveness probe
curl http://localhost:8000/live

# Readiness probe
curl http://localhost:8000/ready

# Basic health check
curl http://localhost:8000/health
```

## Testing

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run all tests
pytest

# Run with coverage
pytest --cov=taskflow --cov-report=html

# Run specific test file
pytest tests/test_task_service.py -v

# Run integration tests
pytest tests/ -v
```

## 📁 Project Structure

```
TaskFlow/
├── taskflow/
│   ├── __init__.py
│   ├── main.py              # FastAPI application
│   ├── websocket.py         # WebSocket handler
│   ├── api/
│   │   ├── __init__.py
│   │   ├── schemas.py       # Pydantic models
│   │   └── routes/
│   │       ├── tasks.py     # Task endpoints
│   │       ├── schedules.py # Schedule endpoints
│   │       ├── workflows.py # Workflow endpoints
│   │       ├── webhooks.py  # Webhook endpoints
│   │       ├── monitoring.py # Metrics endpoints
│   │       └── health.py    # Health checks
│   ├── core/
│   │   ├── config.py        # Settings management
│   │   ├── logging.py       # Structured logging
│   │   └── exceptions.py    # Custom exceptions
│   ├── database/
│   │   ├── session.py       # Database session
│   │   ├── repository.py    # Generic repository
│   │   └── redis.py         # Redis client
│   ├── models/
│   │   ├── base.py          # Base model
│   │   ├── task.py          # Task models
│   │   ├── schedule.py      # Schedule models
│   │   ├── workflow.py      # Workflow models
│   │   └── webhook.py       # Webhook models
│   ├── services/
│   │   ├── task_service.py      # Task business logic
│   │   ├── schedule_service.py  # Schedule logic
│   │   ├── workflow_service.py  # Workflow logic
│   │   └── webhook_service.py   # Webhook logic
│   └── worker/
│       ├── celery_app.py    # Celery configuration
│       └── tasks.py         # Task handlers
├── alembic/
│   ├── versions/            # Database migrations
│   └── env.py
├── tests/
│   ├── conftest.py          # Test fixtures
│   └── test_task_service.py
├── examples/
│   ├── basic_task.py
│   ├── scheduled_task.py
│   └── webhook_setup.py
├── docker-compose.yml       # Docker services
├── Dockerfile               # Application container
├── alembic.ini              # Alembic config
├── pyproject.toml           # Project dependencies
├── .env.example             # Example environment
├── start.sh                 # Quick start script
└── README.md
```

##  Deployment

### Production Checklist

- [ ] Set strong `TASKFLOW_SECRET_KEY`
- [ ] Configure production database URL
- [ ] Set `TASKFLOW_DEBUG=false`
- [ ] Configure CORS origins
- [ ] Enable HTTPS
- [ ] Set up monitoring and alerting
- [ ] Configure log aggregation
- [ ] Set up database backups
- [ ] Scale Celery workers based on load

### Kubernetes Deployment

Example deployment manifests are available in the `k8s/` directory:

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secrets.yaml
kubectl apply -f k8s/postgres.yaml
kubectl apply -f k8s/redis.yaml
kubectl apply -f k8s/api-deployment.yaml
kubectl apply -f k8s/worker-deployment.yaml
kubectl apply -f k8s/beat-deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/ingress.yaml
```

##  Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests (`pytest`)
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [FastAPI](https://fastapi.tiangolo.com/) - Modern, fast web framework
- [Celery](https://docs.celeryq.dev/) - Distributed task queue
- [APScheduler](https://apscheduler.readthedocs.io/) - Advanced Python scheduler
- [Redis](https://redis.io/) - In-memory data store
- [PostgreSQL](https://www.postgresql.org/) - Relational database
- [SQLAlchemy](https://www.sqlalchemy.org/) - Python SQL toolkit
- [Pydantic](https://docs.pydantic.dev/) - Data validation
- [Structlog](https://www.structlog.org/) - Structured logging

## 📞 Support

For questions and support:
-  Email: support@taskflow.dev
-  Discord: [Join our community](https://discord.gg/taskflow)
-  Issues: [GitHub Issues](https://github.com/yourusername/taskflow/issues)

---

**⭐ If you find this project useful, please consider giving it a star on GitHub!**

