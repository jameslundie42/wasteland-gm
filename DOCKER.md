# Docker Setup for Wasteland GM

This directory contains Docker configuration for containerized deployment of Wasteland GM.

## Files

- **Dockerfile** - Production-ready multi-stage build for Wasteland GM
- **docker-compose.yml** - Development/deployment orchestration
- **.dockerignore** - Optimize build context
- **validate-docker.sh** - Quick validation script

## Quick Start

### Option 1: Local Development (No Docker)
```bash
pip install -r requirements.txt
echo "ANTHROPIC_API_KEY=your_key" > .env
python main.py
```

### Option 2: Docker Compose (Recommended for Consistency)
```bash
echo "ANTHROPIC_API_KEY=your_key" > .env
docker-compose up
```

### Option 3: Pure Docker
```bash
# Build image
docker build -t wasteland-gm:latest .

# Run container
docker run -it \
  -e ANTHROPIC_API_KEY=your_key \
  -v $(pwd)/campaigns:/app/campaigns \
  -v $(pwd)/characters:/app/characters \
  -v $(pwd)/agents:/app/agents \
  -v $(pwd)/data:/app/data \
  wasteland-gm:latest
```

## Environment Variables

Required:
- `ANTHROPIC_API_KEY` - Your Anthropic API key

Optional (future):
- `SERVER_MODE=true` - Enable multiplayer server mode
- `SERVER_PORT=8080` - Server port for multiplayer

## Volumes

The Docker setup preserves game data between sessions:

```
/app/campaigns/    # Saved campaigns
/app/characters/   # Character YAML files
/app/agents/       # Agent configurations
/app/data/         # Game data (skills, perks, items, actions)
```

All changes made during gameplay are automatically persisted to your host machine.

## Building the Image

```bash
# Build with default tag
docker build -t wasteland-gm:latest .

# Build with specific tag
docker build -t wasteland-gm:v1.0 .

# Build and push to registry
docker build -t myregistry/wasteland-gm:latest .
docker push myregistry/wasteland-gm:latest
```

## Size & Performance

- **Base Image**: `python:3.14-slim` (~160MB)
- **Final Image**: ~210MB
- **Build Time**: <1 minute (after first pull)
- **Memory Usage**: ~100-150MB during gameplay
- **Startup Time**: <5 seconds

## Running Commands Inside Container

```bash
# Check items loaded
docker-compose exec wasteland-gm python -c \
  "from data.item_database import ItemDatabase; db = ItemDatabase.get_instance(); print(f'Items: {len(db.items)}')"

# Run tests
docker-compose exec wasteland-gm python test_items_integration.py

# Interactive Python shell
docker-compose exec wasteland-gm python

# View logs
docker-compose logs -f wasteland-gm
```

## Troubleshooting

### "Cannot connect to Docker daemon"
- Ensure Docker Desktop is running
- On Linux: `sudo systemctl start docker`

### "Permission denied while trying to connect to Docker daemon socket"
- Add user to docker group: `sudo usermod -aG docker $USER`
- Then restart Docker: `sudo systemctl restart docker`

### "API key not found"
- Ensure `.env` file exists in project root
- Verify `ANTHROPIC_API_KEY` is set: `grep ANTHROPIC .env`

### "Port already in use" (for future server mode)
- Change port in `docker-compose.yml`:
  ```yaml
  ports:
    - "8081:8080"  # Use 8081 instead of 8080
  ```

## Future: Multiplayer Server Mode

When deploying as a server:

1. Uncomment server settings in `docker-compose.yml`
2. Implement HTTP API wrapper around `Session` class
3. Add WebSocket support for real-time updates
4. Use managed database for persistence (PostgreSQL/MongoDB)
5. Consider load balancing for multiple instances

Example scalable deployment:
```yaml
# Future docker-compose.yml for production
version: '3.8'

services:
  wasteland-gm:
    build: .
    environment:
      - SERVER_MODE=true
      - SERVER_PORT=8080
      - DATABASE_URL=postgresql://db:5432/wasteland
    depends_on:
      - db
    deploy:
      replicas: 3  # Scale to 3 instances

  db:
    image: postgres:15-alpine
    environment:
      - POSTGRES_DB=wasteland
    volumes:
      - db_data:/var/lib/postgresql/data

volumes:
  db_data:
```

## Image Details

```dockerfile
FROM python:3.14-slim
# Base: Official Python 3.14 slim (~160MB)

WORKDIR /app
# Set working directory

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*
# Install only git (minimal dependencies)

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Cache layer: Install Python packages

COPY . .
# Copy application code

RUN mkdir -p /app/data/campaigns /app/data/characters /app/data/agents
# Create game data directories

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
# Python optimizations

CMD ["python", "main.py"]
# Default entry point
```

## Publishing to Docker Hub

```bash
# Login to Docker Hub
docker login

# Build with your username
docker build -t yourusername/wasteland-gm:latest .

# Push to registry
docker push yourusername/wasteland-gm:latest

# Others can now run:
docker run -it -e ANTHROPIC_API_KEY=key yourusername/wasteland-gm:latest
```

---

For questions or issues, see the main [README.md](../README.md) or open an issue on GitHub.
