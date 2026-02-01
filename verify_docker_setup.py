#!/usr/bin/env python3
"""Quick validation script to verify Docker setup."""

import os
import json
from pathlib import Path

def check_file_exists(filename, description):
    """Check if file exists and report status."""
    if Path(filename).exists():
        size = os.path.getsize(filename)
        print(f"  ✓ {filename} ({size} bytes) - {description}")
        return True
    else:
        print(f"  ✗ {filename} - NOT FOUND")
        return False

def check_docker_compose_syntax():
    """Verify docker-compose.yml can be parsed."""
    try:
        import yaml
        with open('docker-compose.yml', 'r') as f:
            data = yaml.safe_load(f)
        if 'services' in data and 'wasteland-gm' in data['services']:
            print("  ✓ docker-compose.yml syntax valid")
            return True
    except Exception as e:
        print(f"  ✗ docker-compose.yml error: {e}")
        return False

def check_requirements():
    """Verify requirements.txt has necessary packages."""
    required = {'anthropic', 'pyyaml', 'python-dotenv'}
    try:
        with open('requirements.txt', 'r') as f:
            packages = set(line.strip().split('>=')[0].lower() for line in f if line.strip() and not line.startswith('#'))
        
        missing = required - packages
        if not missing:
            print(f"  ✓ requirements.txt has all required packages: {', '.join(sorted(required))}")
            return True
        else:
            print(f"  ✗ requirements.txt missing: {', '.join(missing)}")
            return False
    except Exception as e:
        print(f"  ✗ Error reading requirements.txt: {e}")
        return False

def check_env_example():
    """Verify .env.example exists."""
    if Path('.env.example').exists():
        with open('.env.example', 'r') as f:
            content = f.read()
            if 'ANTHROPIC_API_KEY' in content:
                print("  ✓ .env.example configured with ANTHROPIC_API_KEY")
                return True
    print("  ✗ .env.example not properly configured")
    return False

def main():
    print("=" * 60)
    print("WASTELAND GM - DOCKER SETUP VERIFICATION")
    print("=" * 60)
    print()
    
    checks = [
        ("Docker Configuration Files", [
            ("Dockerfile", "Production build configuration"),
            ("docker-compose.yml", "Development/deployment orchestration"),
            (".dockerignore", "Build optimization"),
        ]),
        ("Documentation", [
            ("README.md", "Main project documentation"),
            ("DOCKER.md", "Docker-specific documentation"),
            ("DOCKER-SETUP.md", "Docker setup summary"),
        ]),
        ("Configuration", [
            (".env.example", "Environment variables template"),
            ("requirements.txt", "Python dependencies"),
        ]),
    ]
    
    total = 0
    passed = 0
    
    for section, files in checks:
        print(f"[{section}]")
        for filename, description in files:
            total += 1
            if check_file_exists(filename, description):
                passed += 1
        print()
    
    print("[Syntax Checks]")
    if check_docker_compose_syntax():
        passed += 1
    total += 1
    print()
    
    if check_requirements():
        passed += 1
    total += 1
    print()
    
    if check_env_example():
        passed += 1
    total += 1
    print()
    
    print("=" * 60)
    print(f"RESULTS: {passed}/{total} checks passed")
    print("=" * 60)
    print()
    
    if passed == total:
        print("✅ Docker setup is complete and ready!")
        print()
        print("Next steps:")
        print("  1. Copy .env.example to .env")
        print("  2. Add your ANTHROPIC_API_KEY to .env")
        print("  3. Run: docker-compose up")
        print()
        return 0
    else:
        print(f"⚠️  {total - passed} issues found. Please review above.")
        print()
        return 1

if __name__ == '__main__':
    exit(main())
