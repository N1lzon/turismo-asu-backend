-- Agrega la columna start_time a la tabla routes (para bases de datos existentes)
ALTER TABLE routes ADD COLUMN IF NOT EXISTS start_time TIME;
