#!/bin/bash
# AppShak HQ — GitHub Setup Script
# Run this once after cloning or to init fresh

echo "🚀 AppShak HQ — GitHub Push Setup"
echo "==================================="

# 1. Init git if not already
if [ ! -d ".git" ]; then
  git init
  echo "✅ Git repo initialised"
fi

# 2. Set main branch
git branch -M main

# 3. Stage everything
git add .
git status

echo ""
echo "==================================="
echo "Now run:"
echo ""
echo "  git commit -m 'feat: initial AppShak HQ 3D CCTV dashboard'"
echo "  git remote add origin https://github.com/YOUR_USERNAME/appshak-hq.git"
echo "  git push -u origin main"
echo ""
echo "Or with SSH:"
echo "  git remote add origin git@github.com:YOUR_USERNAME/appshak-hq.git"
echo "  git push -u origin main"
echo "==================================="
