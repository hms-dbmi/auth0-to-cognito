#!/bin/bash -e

# Require Python 3 and pip
if ! command -v python3 &> /dev/null
then
    echo "python3 could not be found"
    exit
fi

if ! command -v pip &> /dev/null
then
    echo "pip could not be found"
    exit
fi

if ! command -v zip &> /dev/null
then
    echo "zip could not be found"
    exit
fi

# Create directory
mkdir -p user-migration-trigger

# Install requests
pip install requests -t user-migration-trigger

# Copy Python script
cp user_migration_trigger.py user-migration-trigger/index.py

# Zip it
(cd user-migration-trigger && zip -r ../user-migration-trigger.zip .)
