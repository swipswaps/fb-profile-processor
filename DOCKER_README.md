# FB Profile Processor - Docker Setup

Run the Facebook Profile Processor dashboard in Docker with full Firefox enrichment support.

## Quick Start

### Option 1: Using Docker Compose (Recommended)

```bash
# Clone the repository
git clone https://github.com/swipswaps/fb-profile-processor.git
cd fb-profile-processor

# Start the application
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the application
docker-compose down
```

Access the dashboard at: **http://localhost:8501**

### Option 2: Using Docker directly

```bash
# Build the image
docker build -t fb-profile-processor .

# Run the container
docker run -d \
  --name fb-profile-processor \
  -p 8501:8501 \
  -v $(pwd)/data:/app/data \
  fb-profile-processor

# View logs
docker logs -f fb-profile-processor

# Stop and remove
docker stop fb-profile-processor
docker rm fb-profile-processor
```

## Features

- ✅ **Streamlit Dashboard**: Full web interface
- ✅ **Firefox Integration**: Automated browser enrichment
- ✅ **Database Persistence**: SQLite data stored in `./data` volume
- ✅ **Export Functionality**: Excel, CSV, SQL exports
- ✅ **Health Checks**: Automatic container health monitoring

## Configuration

### Environment Variables

Edit `docker-compose.yml` to configure:

```yaml
environment:
  - STREAMLIT_SERVER_PORT=8501
  - BROWSER_TYPE=firefox
  - ENABLE_API=false  # Set to true if you have Facebook API credentials
```

### Volume Mounts

**Database persistence:**
```yaml
volumes:
  - ./data:/app/data
```
Your database files are stored in `./data` directory on your host machine.

**Firefox profile (optional):**
```yaml
volumes:
  - ~/.mozilla:/root/.mozilla:ro
```
Mount your Firefox profile to use existing cookies/sessions (read-only).

## Architecture

```
┌─────────────────────────────────────┐
│  Docker Container                   │
│  ┌───────────────────────────────┐  │
│  │  Streamlit Dashboard          │  │
│  │  Port: 8501                   │  │
│  └───────────────────────────────┘  │
│  ┌───────────────────────────────┐  │
│  │  Firefox + Selenium           │  │
│  │  (Headless)                   │  │
│  └───────────────────────────────┘  │
│  ┌───────────────────────────────┐  │
│  │  SQLite Database              │  │
│  │  (Mounted: ./data)            │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
         │
         │ Port 8501
         ▼
    Your Browser
```

## Usage

1. **Access Dashboard**: Open http://localhost:8501
2. **Upload URLs**: Paste Facebook Marketplace profile URLs
3. **Process**: Click "Process & Enrich" 
4. **View Data**: See enriched profiles with images
5. **Export**: Download as Excel, CSV, or SQL

## Troubleshooting

### Container won't start

```bash
# Check logs
docker-compose logs

# Common issues:
# - Port 8501 already in use: Change port in docker-compose.yml
# - Permission issues: Run with sudo or fix Docker permissions
```

### Firefox enrichment not working

```bash
# Check Firefox installation
docker-compose exec fb-profile-processor which firefox

# Check geckodriver
docker-compose exec fb-profile-processor which geckodriver

# View detailed logs
docker-compose logs -f | grep -i firefox
```

### Database not persisting

```bash
# Check volume mount
docker-compose exec fb-profile-processor ls -la /app/data

# Ensure ./data directory exists and has correct permissions
mkdir -p ./data
chmod 755 ./data
```

## Advanced Usage

### Custom Database Location

```yaml
volumes:
  - /path/to/your/database:/app/data
```

### Running on Different Port

```yaml
ports:
  - "8080:8501"  # Access on port 8080
```

### Using with Facebook API

1. Set environment variables in `docker-compose.yml`:
```yaml
environment:
  - ENABLE_API=true
  - FACEBOOK_APP_ID=your_app_id
  - FACEBOOK_ACCESS_TOKEN=your_token
```

2. Restart container:
```bash
docker-compose restart
```

## Building for Production

### Multi-stage build (smaller image)

```dockerfile
FROM python:3.11-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:3.11-slim
# ... (copy from builder)
```

### Security hardening

```dockerfile
# Run as non-root user
RUN useradd -m -u 1000 appuser
USER appuser
```

## GitHub Actions Integration

Deploy automatically on push:

```yaml
# .github/workflows/docker.yml
name: Build and Push Docker Image

on:
  push:
    branches: [ main ]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Build and push
        uses: docker/build-push-action@v4
        with:
          push: true
          tags: ghcr.io/swipswaps/fb-profile-processor:latest
```

## Updates

```bash
# Pull latest changes
git pull

# Rebuild and restart
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

## Support

- **Issues**: https://github.com/swipswaps/fb-profile-processor/issues
- **Documentation**: https://github.com/swipswaps/fb-profile-processor
- **Demo**: https://swipswaps.github.io/fb-profile-processor/

## License

MIT License - See LICENSE file for details
