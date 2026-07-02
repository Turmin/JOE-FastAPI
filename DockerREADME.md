# Docker and NGINX Setup for JOE Playlist API

This document describes how to install Docker, build and run the JOE Playlist API container, and expose it through NGINX without breaking existing NGINX websites.

The application itself is documented in [README.md](README.md).

## Overview

The JOE Playlist API is a FastAPI service that connects to the upstream WebSocket:

```text
wss://socket.qmusic.be/api/502/ltfn4msd/websocket
```

The service subscribes to the JOE station:

```text
joe_nl
```

It stores the latest received tracks in memory and exposes them through these endpoints:

```text
GET /
GET /status
GET /playlist
GET /now-playing
GET /docs
```

There is currently no `/health` endpoint.

Use `/` or `/status` for basic checks.

## Recommended VPS path

Use `/opt/joe-fastapi` for the project:

```bash
sudo mkdir -p /opt/joe-fastapi
sudo chown -R $USER:$USER /opt/joe-fastapi
cd /opt/joe-fastapi
```

Check that you are in the correct location:

```bash
pwd
```

Expected output:

```text
/opt/joe-fastapi
```

## Expected project structure

```text
/opt/joe-fastapi
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── README.md
├── DockerREADME.md
└── app
    ├── __init__.py
    └── joe_api.py
```

Create the app directory if needed:

```bash
mkdir -p app
touch app/__init__.py
```

## Install Docker on Debian

First check your OS:

```bash
cat /etc/os-release
dpkg --print-architecture
```

If the VPS is Debian, use the Debian Docker repository.

Remove a wrong Docker repository if needed:

```bash
sudo rm -f /etc/apt/sources.list.d/docker.list
sudo rm -f /etc/apt/keyrings/docker.asc
sudo apt update
```

Install required packages:

```bash
sudo apt update
sudo apt install -y ca-certificates curl
```

Add Docker's GPG key:

```bash
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
```

Add the Docker repository:

```bash
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
```

Install Docker Engine and Compose plugin:

```bash
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Check Docker:

```bash
sudo docker --version
sudo docker compose version
```

Test Docker:

```bash
sudo docker run hello-world
```

## Optional: run Docker without sudo

Add your user to the Docker group:

```bash
sudo usermod -aG docker $USER
```

Then log out and log in again:

```bash
exit
```

After reconnecting:

```bash
docker --version
docker compose version
```

Until that works, use `sudo docker`.

## requirements.txt

Create or edit:

```bash
cd /opt/joe-fastapi
nano requirements.txt
```

Content:

```txt
fastapi
uvicorn[standard]
websockets
websocket-client
```

Important:

`websocket-client` is required because the script imports:

```python
import websocket
```

## Dockerfile

Create or edit:

```bash
cd /opt/joe-fastapi
nano Dockerfile
```

Content:

```dockerfile
FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

CMD ["uvicorn", "app.joe_api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

The important part is:

```text
app.joe_api:app
```

This means:

```text
folder: app
file: joe_api.py
FastAPI object: app
```

So the Python file must contain:

```python
app = FastAPI(...)
```

## docker-compose.yml

Create or edit:

```bash
cd /opt/joe-fastapi
nano docker-compose.yml
```

Content:

```yaml
services:
  joe-fastapi:
    build: .
    container_name: joe-fastapi
    restart: unless-stopped
    ports:
      - "127.0.0.1:8000:8000"
```

This exposes the container only on localhost. Public access should go through NGINX.

## Build and start the container

From the project directory:

```bash
cd /opt/joe-fastapi
sudo docker compose up -d --build
```

## Check Docker status

Show the service status:

```bash
cd /opt/joe-fastapi
sudo docker compose ps
```

Show logs:

```bash
cd /opt/joe-fastapi
sudo docker compose logs -f
```

Show the last 100 log lines:

```bash
cd /opt/joe-fastapi
sudo docker compose logs --tail=100
```

Show logs for the container directly:

```bash
sudo docker logs joe-fastapi --tail=100
```

## Test the API locally on the VPS

```bash
curl http://127.0.0.1:8000/
curl http://127.0.0.1:8000/status
curl http://127.0.0.1:8000/playlist
curl http://127.0.0.1:8000/now-playing
```

Do not test `/health`, because this project currently does not have that endpoint.

## Stop the container

```bash
cd /opt/joe-fastapi
sudo docker compose stop
```

## Start the container again

```bash
cd /opt/joe-fastapi
sudo docker compose start
```

## Restart the container

```bash
cd /opt/joe-fastapi
sudo docker compose restart
```

## Stop and remove the container

This stops and removes the container, but keeps your project files.

```bash
cd /opt/joe-fastapi
sudo docker compose down
```

Start it again:

```bash
cd /opt/joe-fastapi
sudo docker compose up -d
```

## Rebuild after code changes

If you changed `joe_api.py`, `requirements.txt`, `Dockerfile`, or other files copied into the image:

```bash
cd /opt/joe-fastapi
sudo docker compose up -d --build
```

## Restart Docker service

Restart the Docker daemon itself:

```bash
sudo systemctl restart docker
```

Check Docker daemon status:

```bash
sudo systemctl status docker
```

Enable Docker on boot:

```bash
sudo systemctl enable docker
```

Start Docker manually:

```bash
sudo systemctl start docker
```

Stop Docker manually:

```bash
sudo systemctl stop docker
```

Warning: stopping Docker stops all running containers on the VPS.

## Check whether port 8000 is listening

```bash
sudo ss -tulpn | grep 8000
```

Expected output should include:

```text
127.0.0.1:8000
```

## NGINX reverse proxy

The safest approach is to create a new NGINX site file instead of editing existing website configs.

Example domain:

```text
joe-api.example.com
```

Create a new NGINX config:

```bash
sudo nano /etc/nginx/sites-available/joe-fastapi
```

Content:

```nginx
server {
    listen 80;
    server_name joe-api.example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;

        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        proxy_read_timeout 3600;
        proxy_send_timeout 3600;
    }
}
```

Enable the new site:

```bash
sudo ln -s /etc/nginx/sites-available/joe-fastapi /etc/nginx/sites-enabled/joe-fastapi
```

Test NGINX before reloading:

```bash
sudo nginx -t
```

Only reload if the test succeeds:

```bash
sudo systemctl reload nginx
```

## NGINX status and lifecycle commands

Check NGINX status:

```bash
sudo systemctl status nginx
```

Reload NGINX safely:

```bash
sudo systemctl reload nginx
```

Restart NGINX:

```bash
sudo systemctl restart nginx
```

Stop NGINX:

```bash
sudo systemctl stop nginx
```

Start NGINX:

```bash
sudo systemctl start nginx
```

Enable NGINX on boot:

```bash
sudo systemctl enable nginx
```

Test NGINX config:

```bash
sudo nginx -t
```

List enabled NGINX sites:

```bash
ls -la /etc/nginx/sites-enabled/
```

List available NGINX sites:

```bash
ls -la /etc/nginx/sites-available/
```

## Add SSL with Certbot

After the DNS record points to the VPS, run:

```bash
sudo certbot --nginx -d joe-api.example.com
```

Then test:

```bash
curl https://joe-api.example.com/
curl https://joe-api.example.com/status
curl https://joe-api.example.com/playlist
curl https://joe-api.example.com/now-playing
```

## Backup NGINX before changes

Before changing NGINX, make a backup:

```bash
sudo cp -a /etc/nginx /etc/nginx.backup-before-joe-fastapi
```

## Troubleshooting

### `docker: command not found`

Docker is not installed or the current shell cannot find it.

Check:

```bash
docker --version
```

Install Docker using the steps above.

### Container keeps restarting

Check logs:

```bash
cd /opt/joe-fastapi
sudo docker compose logs --tail=100
```

Common causes:

```text
ModuleNotFoundError
ImportError
SyntaxError
Error loading ASGI app
Attribute "app" not found
```

### `ModuleNotFoundError: No module named 'websocket'`

Add this to `requirements.txt`:

```txt
websocket-client
```

Then rebuild:

```bash
sudo docker compose up -d --build
```

### `curl: Failed to connect to 127.0.0.1 port 8000`

The container is not running or the port is not mapped.

Check:

```bash
sudo docker compose ps
sudo docker compose logs --tail=100
sudo ss -tulpn | grep 8000
```

### `/health` returns 404

That is expected. This project does not define `/health`.

Use:

```bash
curl http://127.0.0.1:8000/
curl http://127.0.0.1:8000/status
```

### NGINX reload fails

Run:

```bash
sudo nginx -t
```

Fix the error shown in the output before running:

```bash
sudo systemctl reload nginx
```

### API works locally but not through domain

Check:

```bash
curl http://127.0.0.1:8000/status
sudo nginx -t
sudo systemctl status nginx
```

Also check:

```bash
dig joe-api.example.com
```

The domain must point to the VPS IP address.

## Useful complete update flow

After editing code:

```bash
cd /opt/joe-fastapi
sudo docker compose up -d --build
sudo docker compose ps
sudo docker compose logs --tail=100
curl http://127.0.0.1:8000/status
sudo nginx -t
sudo systemctl reload nginx
```

Then test the public endpoint:

```bash
curl https://joe-api.example.com/status
```
