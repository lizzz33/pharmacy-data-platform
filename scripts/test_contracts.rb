#!/usr/bin/env ruby
require "open3"
require "yaml"

ROOT = File.expand_path("..", __dir__)
CONTRACT = YAML.load_file(File.join(ROOT, "hws_descriptions/hw1/hw01_contract.yaml"))
DATABASES = {
  "crm" => "crm_service_db",
  "catalog" => "catalog_service_db",
  "pos" => "pos_service_db",
  "wms" => "wms_service_db"
}.freeze
TYPE_CLASSES = {
  "text" => ["text", "character varying", "character"],
  "int" => ["smallint", "integer", "bigint"],
  "numeric" => ["numeric", "decimal"],
  "boolean" => ["boolean"],
  "date" => ["date"],
  "timestamptz" => ["timestamp with time zone"]
}.freeze

def psql(database, sql)
  command = ["docker", "compose", "run", "--rm", "-T", "--no-deps", "tools", "psql", "-XqAt",
             "-F", "\t", "-v", "ON_ERROR_STOP=1", "-d", database]
  stdout, stderr, status = Open3.capture3(*command, stdin_data: sql, chdir: ROOT)
  raise "psql #{database} failed: #{stderr.strip}" unless status.success?
  stdout
end

failures = []

CONTRACT.fetch("services").each do |service, service_spec|
  database = DATABASES.fetch(service)
  expected_views = service_spec.fetch("views")
  metadata_sql = <<~SQL
    SELECT table_name, column_name, data_type, ordinal_position
      FROM information_schema.columns
     WHERE table_schema = 'contract'
     ORDER BY table_name, ordinal_position;
  SQL
  actual = Hash.new { |hash, key| hash[key] = [] }
  psql(database, metadata_sql).lines.each do |line|
    view, column, type, = line.strip.split("\t")
    actual[view] << [column, type]
  end

  expected_views.each do |view, view_spec|
    expected_columns = view_spec.fetch("columns").map { |name, spec| [name, spec.fetch("type")] }
    actual_columns = actual[view]
    if actual_columns.map(&:first) != expected_columns.map(&:first)
      failures << "#{service}.#{view}: columns #{actual_columns.map(&:first).inspect}, expected #{expected_columns.map(&:first).inspect}"
      next
    end
    expected_columns.zip(actual_columns).each do |(column, expected_type), (_, actual_type)|
      unless TYPE_CLASSES.fetch(expected_type).include?(actual_type)
        failures << "#{service}.#{view}.#{column}: type #{actual_type}, expected #{expected_type}"
      end
    end
    puts "VIEW #{service}.#{view} PASS"
  end
  (actual.keys - expected_views.keys).each do |extra|
    failures << "#{service}: unexpected contract view #{extra}"
  end

  fixture = File.read(File.join(ROOT, "tests/contracts/#{service}.sql"))
  validation = ["BEGIN;", fixture]
  expected_views.each do |view, view_spec|
    nonnull = view_spec.fetch("columns").select { |_, spec| spec.fetch("nullable") == false }.keys
    predicate = nonnull.map { |column| "#{column} IS NULL" }.join(" OR ")
    validation << "SELECT 'NULL:#{view}', count(*) FROM contract.#{view} WHERE #{predicate};"
  end
  CONTRACT.fetch("sql_checks").select { |check| check.fetch("service") == service }.each do |check|
    sql = check.fetch("sql").strip.sub(/;\z/, "")
    validation << "SELECT 'CHECK:#{check.fetch('id')}', result FROM (#{sql}) AS contract_check(result);"
  end
  validation << <<~SQL
    SELECT 'CROSS_DB_DEPENDENCY', count(*)
      FROM pg_views
     WHERE schemaname = 'contract'
       AND (definition ILIKE '%dblink%' OR definition ILIKE '%postgres_fdw%');
    SELECT 'VOLATILE_VIEW_EXPRESSION', count(*)
      FROM pg_views
     WHERE schemaname = 'contract'
       AND (definition ILIKE '%now(%' OR definition ILIKE '%random(%'
            OR definition ILIKE '%clock_timestamp(%');
  SQL
  validation << "ROLLBACK;"

  psql(database, validation.join("\n")).lines.each do |line|
    marker, value = line.strip.split("\t", 2)
    next unless marker&.match?(/\A(SMOKE|NULL|CHECK|CROSS_DB_DEPENDENCY|VOLATILE_VIEW_EXPRESSION)/)
    expected = marker.start_with?("SMOKE:") ? "1" : "0"
    if value == expected
      puts "#{marker} PASS"
    else
      failures << "#{service} #{marker}: got #{value.inspect}, expected #{expected}"
    end
  end
end

unless failures.empty?
  warn failures.map { |failure| "FAIL #{failure}" }.join("\n")
  exit 1
end

puts "All contract views, fixtures, and C01-C23 checks passed."
