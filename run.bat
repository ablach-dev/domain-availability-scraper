@echo off
title DomainPulse - Authoritative Domain Availability Scraper
echo Starting DomainPulse Desktop Application...
python main.py
if errorlevel 1 (
    echo.
    echo An error occurred while launching DomainPulse.
    pause
)
