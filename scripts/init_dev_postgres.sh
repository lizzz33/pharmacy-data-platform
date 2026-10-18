#!/bin/sh
set -eu

for database in crm_service_db catalog_service_db wms_service_db pos_service_db; do
  psql --set ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    --command "CREATE DATABASE $database"
done

for service in crm catalog wms pos; do
  database="${service}_service_db"
  for migration in "/migrations/$service"/*.sql; do
    psql --set ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$database" \
      --file "$migration"
  done
done
