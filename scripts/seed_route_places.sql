-- Populates route_places for the 3 preset routes.
-- Run this on the production database:
--   psql $DATABASE_URL -f scripts/seed_route_places.sql

-- Route IDs: 14=Centro Histórico, 15=Naturaleza y Relax, 16=Gastronomía Asuncena
-- Place IDs confirmed via /places/search against the production DB

DELETE FROM route_places WHERE route_id IN (14, 15, 16);

-- Centro Histórico: Panteón → Casa Independencia → Museo del Barro → Museo del Cabildo
INSERT INTO route_places (route_id, place_id, order_index) VALUES
    (14, 1624, 0),
    (14, 1176, 1),
    (14, 1375, 2),
    (14, 1177, 3);

-- Naturaleza y Relax: Jardín Botánico → Parque Carlos Antonio López → Tierra Colorada
INSERT INTO route_places (route_id, place_id, order_index) VALUES
    (15, 1275, 0),
    (15, 1422, 1),
    (15, 553,  2);

-- Gastronomía Asuncena: La Preferida → Tierra Colorada → Bar San Roque
INSERT INTO route_places (route_id, place_id, order_index) VALUES
    (16, 369, 0),
    (16, 553, 1),
    (16, 801, 2);
