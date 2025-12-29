#!/bin/bash
# Quick start script for TaskFlow

set -e

echo "🚀 Starting TaskFlow..."

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "📝 Creating .env file..."
    cp .env.example .env
fi

# Start services
echo "🐳 Starting Docker services..."
docker-compose up -d

# Wait for services to be healthy
echo "⏳ Waiting for services to be ready..."
sleep 10

# Run migrations
echo "📊 Running database migrations..."
docker-compose exec -T api alembic upgrade head

echo ""
echo "✅ TaskFlow is ready!"
echo ""
echo "🌐 API:          http://localhost:8000"
echo "📚 API Docs:     http://localhost:8000/docs"
echo "🌺 Flower:       http://localhost:5555"
echo "💚 Health Check: http://localhost:8000/health"
echo ""
echo "To view logs: docker-compose logs -f"
echo "To stop:      docker-compose down"
