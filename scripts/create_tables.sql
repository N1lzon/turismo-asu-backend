CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS places (
    id SERIAL PRIMARY KEY,
    google_place_id TEXT UNIQUE,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    address TEXT,
    phone TEXT,
    website TEXT,
    rating DECIMAL(2,1),
    total_ratings INTEGER,
    opening_hours JSONB,
    location GEOGRAPHY(POINT, 4326) NOT NULL,
    photos JSONB DEFAULT '[]',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS places_location_idx ON places USING GIST(location);
CREATE INDEX IF NOT EXISTS places_category_idx ON places(category);

CREATE TABLE IF NOT EXISTS routes (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    is_preset BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS route_places (
    id SERIAL PRIMARY KEY,
    route_id INTEGER REFERENCES routes(id) ON DELETE CASCADE,
    place_id INTEGER REFERENCES places(id) ON DELETE CASCADE,
    order_index INTEGER NOT NULL,
    UNIQUE(route_id, order_index)
);