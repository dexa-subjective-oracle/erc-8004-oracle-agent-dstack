#!/bin/bash
set -e

echo "📦 Installing Python packages..."
apt-get update
apt-get install -y python3 python3-pip
pip3 install -e .

echo "🚀 Starting ERC-8004 TEE Agent..."
exec python3 deployment/local_agent_server.py
