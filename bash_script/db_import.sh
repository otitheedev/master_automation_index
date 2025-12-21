#!/usr/bin/env bash
set -euo pipefail

# db_import.sh
# Imports all .sql files found in the repo's sql/ directory into MySQL.
# - Creates a database per file, named after the filename (without extension).
# - Works with Docker (preferred) or a locally available mysql client.
# - Defaults align with docker-compose.yml in this repo.
#
# Usage:
#   ./db_import.sh [--no-docker] [--yes] [--container NAME] [--host HOST] [--port PORT] \\
#                  [--root-user USER] [--root-password PASS] [--charset utf8mb4] [--collation utf8mb4_unicode_ci]
#
# Examples:
#   ./db_import.sh
#   ./db_import.sh --no-docker --host 127.0.0.1 --port 3306 --root-password root_password
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SQL_DIR="${SCRIPT_DIR}/sql"

# Defaults based on docker-compose.yml
USE_DOCKER=1
ASSUME_YES=0
MYSQL_CONTAINER_DEFAULT="otithee_mysql"
MYSQL_CONTAINER="${MYSQL_CONTAINER_DEFAULT}"
MYSQL_HOST_DEFAULT="mysql"
MYSQL_HOST="${MYSQL_HOST_DEFAULT}"
MYSQL_PORT_DEFAULT="3306"
MYSQL_PORT="${MYSQL_PORT_DEFAULT}"
MYSQL_ROOT_USER_DEFAULT="root"
MYSQL_ROOT_USER="${MYSQL_ROOT_USER_DEFAULT}"
MYSQL_ROOT_PASSWORD_DEFAULT="root_password"
MYSQL_ROOT_PASSWORD="${MYSQL_ROOT_PASSWORD_DEFAULT}"
DB_CHARSET_DEFAULT="utf8mb4"
DB_CHARSET="${DB_CHARSET_DEFAULT}"
DB_COLLATION_DEFAULT="utf8mb4_unicode_ci"
DB_COLLATION="${DB_COLLATION_DEFAULT}"

print_usage() {
	echo "Usage: $0 [options]"
	echo
	echo "Options:"
	echo "  --no-docker                 Use local mysql client instead of Docker."
	echo "  --yes                       Do not prompt for confirmation."
	echo "  --container NAME            Docker container name (default: ${MYSQL_CONTAINER_DEFAULT})."
	echo "  --host HOST                 MySQL host (default: ${MYSQL_HOST_DEFAULT})."
	echo "  --port PORT                 MySQL port (default: ${MYSQL_PORT_DEFAULT})."
	echo "  --root-user USER            MySQL root user (default: ${MYSQL_ROOT_USER_DEFAULT})."
	echo "  --root-password PASS        MySQL root password (default: ${MYSQL_ROOT_PASSWORD_DEFAULT})."
	echo "  --charset CHARSET           DB charset (default: ${DB_CHARSET_DEFAULT})."
	echo "  --collation COLLATION       DB collation (default: ${DB_COLLATION_DEFAULT})."
	echo "  -h, --help                  Show this help."
}

while [[ $# -gt 0 ]]; do
	case "$1" in
		--no-docker)
			USE_DOCKER=0
			shift
			;;
		--yes)
			ASSUME_YES=1
			shift
			;;
		--container)
			MYSQL_CONTAINER="${2:-}"
			shift 2
			;;
		--host)
			MYSQL_HOST="${2:-}"
			shift 2
			;;
		--port)
			MYSQL_PORT="${2:-}"
			shift 2
			;;
		--root-user)
			MYSQL_ROOT_USER="${2:-}"
			shift 2
			;;
		--root-password)
			MYSQL_ROOT_PASSWORD="${2:-}"
			shift 2
			;;
		--charset)
			DB_CHARSET="${2:-}"
			shift 2
			;;
		--collation)
			DB_COLLATION="${2:-}"
			shift 2
			;;
		-h|--help)
			print_usage
			exit 0
			;;
		*)
			echo "Unknown option: $1"
			print_usage
			exit 1
			;;
	esac
done

require_cmd() {
	if ! command -v "$1" >/dev/null 2>&1; then
		echo "Error: required command not found: $1"
		exit 1
	fi
}

docker_container_running() {
	local name="$1"
	if ! command -v docker >/dev/null 2>&1; then
		return 1
	fi
	docker ps --format '{{.Names}}' | grep -wq "${name}"
}

confirm() {
	if [[ "${ASSUME_YES}" -eq 1 ]]; then
		return 0
	fi
	read -r -p "Import all .sql files from ${SQL_DIR} into MySQL? [y/N] " resp
	case "$resp" in
		[yY][eE][sS]|[yY]) return 0 ;;
		*) echo "Aborted."; exit 1 ;;
	esac
}

if [[ ! -d "${SQL_DIR}" ]]; then
	echo "Error: SQL directory not found: ${SQL_DIR}"
	exit 1
fi

mapfile -t SQL_FILES < <(find "${SQL_DIR}" -maxdepth 1 -type f -name "*.sql" | sort)
if [[ ${#SQL_FILES[@]} -eq 0 ]]; then
	echo "No .sql files found in ${SQL_DIR}"
	exit 0
fi

echo "Detected SQL files:"
for f in "${SQL_FILES[@]}"; do
	echo "  - $(basename "$f")"
done

if [[ "${USE_DOCKER}" -eq 1 ]]; then
	if ! docker_container_running "${MYSQL_CONTAINER}"; then
		echo "Warning: Docker container '${MYSQL_CONTAINER}' not running."
		echo "  - To use Docker, ensure it's up: docker compose up -d mysql"
		echo "  - Falling back to local mysql client."
		USE_DOCKER=0
	fi
fi

if [[ "${USE_DOCKER}" -eq 0 ]]; then
	require_cmd mysql
	echo "Using local mysql client to connect to ${MYSQL_HOST}:${MYSQL_PORT} as ${MYSQL_ROOT_USER}"
else
	require_cmd docker
	echo "Using Docker container '${MYSQL_CONTAINER}' for mysql client (root user)"
fi

confirm

mysql_exec() {
	local sql="$1"
	if [[ "${USE_DOCKER}" -eq 1 ]]; then
		docker exec -i "${MYSQL_CONTAINER}" \
			env MYSQL_PWD="${MYSQL_ROOT_PASSWORD}" \
			mysql -h "${MYSQL_HOST}" -P "${MYSQL_PORT}" -u "${MYSQL_ROOT_USER}" -e "${sql}"
	else
		MYSQL_PWD="${MYSQL_ROOT_PASSWORD}" \
			mysql -h "${MYSQL_HOST}" -P "${MYSQL_PORT}" -u "${MYSQL_ROOT_USER}" -e "${sql}"
	fi
}

mysql_import_file() {
	local db_name="$1"
	local file_path="$2"
	if [[ "${USE_DOCKER}" -eq 1 ]]; then
		docker exec -i "${MYSQL_CONTAINER}" \
			env MYSQL_PWD="${MYSQL_ROOT_PASSWORD}" \
			mysql -h "${MYSQL_HOST}" -P "${MYSQL_PORT}" -u "${MYSQL_ROOT_USER}" --max-allowed-packet=1G "${db_name}" < "${file_path}"
	else
		MYSQL_PWD="${MYSQL_ROOT_PASSWORD}" \
			mysql -h "${MYSQL_HOST}" -P "${MYSQL_PORT}" -u "${MYSQL_ROOT_USER}" --max-allowed-packet=1G "${db_name}" < "${file_path}"
	fi
}

sanitize_db_name() {
	# Lowercase, remove extension, replace invalid chars with underscore
	local base
	base="$(basename "$1" .sql)"
	# Convert to lowercase and replace anything not [a-z0-9_] with _
	echo "${base,,}" | sed -E 's/[^a-z0-9_]/_/g'
}

for sql_file in "${SQL_FILES[@]}"; do
	db_name="$(sanitize_db_name "${sql_file}")"
	if [[ -z "${db_name}" ]]; then
		echo "Skipping ${sql_file}: could not derive database name."
		continue
	fi

	echo
	echo "==> Dropping database if exists: ${db_name}"
	mysql_exec "DROP DATABASE IF EXISTS \`${db_name}\`;"
	
	echo "==> Creating database: ${db_name} (charset=${DB_CHARSET}, collation=${DB_COLLATION})"
	mysql_exec "CREATE DATABASE \`${db_name}\` CHARACTER SET ${DB_CHARSET} COLLATE ${DB_COLLATION};"

	echo "==> Importing $(basename "${sql_file}") into ${db_name} ..."
	start_time=$(date +%s)
	mysql_import_file "${db_name}" "${sql_file}"
	end_time=$(date +%s)
	echo "==> Done (${db_name}) in $((end_time - start_time))s"
done

echo
echo "All imports completed."


