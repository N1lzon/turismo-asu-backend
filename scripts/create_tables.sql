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
    start_time TIME,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS route_places (
    id SERIAL PRIMARY KEY,
    route_id INTEGER REFERENCES routes(id) ON DELETE CASCADE,
    place_id INTEGER REFERENCES places(id) ON DELETE CASCADE,
    order_index INTEGER NOT NULL,
    UNIQUE(route_id, order_index)
);

CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    photo TEXT,
    date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME,
    address TEXT,
    location GEOGRAPHY(POINT, 4326),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS events_date_idx ON events(date);
CREATE INDEX IF NOT EXISTS events_location_idx ON events USING GIST(location);