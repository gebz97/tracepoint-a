#!/usr/bin/env bash


DIR="$(dirname "$0")"
cat "$DIR"/*.sql | psql