#!/usr/bin/env bash
# Validate Docker setup for Wasteland GM

echo "=== Docker Setup Validation ==="
echo ""

# Check Dockerfile syntax
echo "[1] Validating Dockerfile..."
if [ -f "Dockerfile" ]; then
    echo "  ✓ Dockerfile exists"
    # Check for common issues
    if grep -q "FROM python" Dockerfile; then
        echo "  ✓ Has Python base image"
    fi
    if grep -q "WORKDIR" Dockerfile; then
        echo "  ✓ Has WORKDIR set"
    fi
    if grep -q "COPY requirements.txt" Dockerfile; then
        echo "  ✓ Installs requirements"
    fi
    if grep -q "CMD" Dockerfile; then
        echo "  ✓ Has CMD defined"
    fi
else
    echo "  ✗ Dockerfile not found"
    exit 1
fi

echo ""
echo "[2] Validating docker-compose.yml..."
if [ -f "docker-compose.yml" ]; then
    echo "  ✓ docker-compose.yml exists"
    if grep -q "wasteland-gm:" docker-compose.yml; then
        echo "  ✓ Has service defined"
    fi
    if grep -q "stdin_open: true" docker-compose.yml; then
        echo "  ✓ Interactive mode enabled"
    fi
    if grep -q "volumes:" docker-compose.yml; then
        echo "  ✓ Volume mounts configured"
    fi
else
    echo "  ✗ docker-compose.yml not found"
    exit 1
fi

echo ""
echo "[3] Validating .dockerignore..."
if [ -f ".dockerignore" ]; then
    echo "  ✓ .dockerignore exists"
else
    echo "  ✗ .dockerignore not found"
    exit 1
fi

echo ""
echo "[4] Checking requirements.txt..."
if [ -f "requirements.txt" ]; then
    echo "  ✓ requirements.txt exists"
    echo "  Dependencies:"
    while IFS= read -r line; do
        if [ -n "$line" ] && [ "${line:0:1}" != "#" ]; then
            echo "    - $line"
        fi
    done < requirements.txt
else
    echo "  ✗ requirements.txt not found"
    exit 1
fi

echo ""
echo "=== All checks passed! ==="
echo ""
echo "To test Docker build:"
echo "  docker build -t wasteland-gm:latest ."
echo ""
echo "To run with Docker Compose:"
echo "  docker-compose up --build"
