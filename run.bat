@echo off
title Domain Availability Scraper
echo Starting Domain Availability Scraper...
python main.py
if errorlevel 1 (
    echo.
    echo An error occurred while launching Domain Availability Scraper.
    pause
)
