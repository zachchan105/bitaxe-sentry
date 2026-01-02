# Bitaxe Sentry

A monitoring system for Bitaxe miners that tracks performance metrics, sends alerts, and provides a web dashboard.

## Overview

Bitaxe Sentry is a lightweight monitoring solution for bitaxe cryptocurrency miners. It periodically polls miner endpoints, stores the data in an SQLite database, sends alerts via Discord when temperature or voltage thresholds are exceeded, and provides a lightweight dashboard to visualize miner performance.

### Features

- 📊 **Metrics Tracking**: Monitors hash rate, temperature, voltage, best difficulty, and error rate.
- 🚨 **Alert System**: Discord notifications for temperature/voltage thresholds, offline miners, and new best difficulty records
- 🌓 **Dark Mode**: Theme toggle with persistence
- ✏️ **Rename Miners**: Give friendly names instead of IPs
- 📱 **Web Dashboard**: Web interface for real-time monitoring and history charts
- 📊 **Mobile Friendly**: Responsive design works great on smartphones and tablets
- 🔄 **Automatic History Cleanup**: Configurable data retention period
- 🐳 **Docker Support**: Easy deployment with Docker Compose
- 🧩 **Umbrel App Store**: Available for 1‑click install on Umbrel

## Screenshots

![Dashboard View](./public/merged_image.png)

## Install on Umbrel

- Find "Bitaxe Sentry" in the Umbrel App Store and install with one click.
- All configuration is done in the app’s Settings page — no environment variables needed.

## Run with Docker

```bash
# Clone the repository
git clone https://github.com/zachchan105/bitaxe-sentry.git
cd bitaxe-sentry

# Start the services (use -d to run in the background)
docker compose up -d
```

The application uses Docker volumes for data persistence. All data is stored in a named volume `bitaxe_data` which persists between container restarts and updates.

## Updating

To update to the latest version:

```bash
# Stop the current containers
docker compose down

# Pull the latest code
git pull

# Rebuild and start the containers
docker compose up --build -d
```

## Web Dashboard

Once running, access the web dashboard at:
- http://your-server-ip:7070 (when running in Docker)

## Support Development

If you find this project useful, consider supporting its development:

**Bitcoin**: `bc1qrnywctt0lerrfgyqj5fvf7aulp5rvtr9as25uq`

![Bitcoin QR Code](https://api.qrserver.com/v1/create-qr-code/?size=150x150&data=bitcoin:bc1qrnywctt0lerrfgyqj5fvf7aulp5rvtr9as25uq) 
