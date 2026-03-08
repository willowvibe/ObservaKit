#!/bin/bash
set -e

VERSION_FILE="VERSION"

if [ ! -f "$VERSION_FILE" ]; then
    echo "0.1.0" > "$VERSION_FILE"
    echo "Created VERSION file with 0.1.0"
    exit 0
fi

# Read current version
current_version=$(cat "$VERSION_FILE")
echo "Current version: $current_version"

# Split version string into array
IFS='.' read -ra parts <<< "$current_version"

# Increment patch version
patch_version=$((parts[2] + 1))
new_version="${parts[0]}.${parts[1]}.$patch_version"

# Write back to file
echo "$new_version" > "$VERSION_FILE"
echo "Bumped version to: $new_version"

# Update version in backend/main.py
sed -i "s/version=\"[^\"]*\"/version=\"$new_version\"/g" backend/main.py
sed -i "s/\"version\": \"[^\"]*\"/\"version\": \"$new_version\"/g" backend/main.py

# Update version in pyproject.toml
sed -i "s/^version = \"[^\"]*\"/version = \"$new_version\"/" pyproject.toml

# Update version in landing-page/package.json
sed -i "s/\"version\": \"[^\"]*\"/\"version\": \"$new_version\"/" landing-page/package.json

# Update version in landing-page/src/App.jsx
sed -i "s/v[0-9]\+\.[0-9]\+\.[0-9]\+ • Open Source/v$new_version • Open Source/g" landing-page/src/App.jsx

echo "Synchronized version strings across codebase."
