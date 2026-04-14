import psycopg2
import json
import os
from dotenv import load_dotenv

load_dotenv()

places = [
    {
        "name": "Museo del Barro",
        "category": "museum",
        "address": "Calle Grabadores del Cabichuí, Asunción",
        "phone": "+595 21 607996",
        "website": "http://www.museodelbarro.org",
        "rating": 4.6,
        "total_ratings": 320,
        "opening_hours": {
            "lunes": "Cerrado",
            "martes": "09:00 - 17:00",
            "miércoles": "09:00 - 17:00",
            "jueves": "09:00 - 17:00",
            "viernes": "09:00 - 17:00",
            "sábado": "09:00 - 12:00",
            "domingo": "Cerrado"
        },
        "lat": -25.2880,
        "lng": -57.6320,
        "photos": [
            "https://images.unsplash.com/photo-1554907984-15263bfd63bd?w=1280&q=80",
            "https://images.unsplash.com/photo-1513519245088-0e12902e5a38?w=1280&q=80"
        ]
    },
    {
        "name": "Jardín Botánico y Zoológico de Asunción",
        "category": "park",
        "address": "Av. Artigas, Asunción",
        "phone": "+595 21 290960",
        "website": None,
        "rating": 4.2,
        "total_ratings": 5800,
        "opening_hours": {
            "lunes": "07:00 - 17:30",
            "martes": "07:00 - 17:30",
            "miércoles": "07:00 - 17:30",
            "jueves": "07:00 - 17:30",
            "viernes": "07:00 - 17:30",
            "sábado": "07:00 - 17:30",
            "domingo": "07:00 - 17:30"
        },
        "lat": -25.2760,
        "lng": -57.6050,
        "photos": [
            "https://images.unsplash.com/photo-1441974231531-c6227db76b6e?w=1280&q=80",
            "https://images.unsplash.com/photo-1519331379826-f10be5486c6f?w=1280&q=80"
        ]
    },
    {
        "name": "Panteón Nacional de los Héroes",
        "category": "attraction",
        "address": "Chile esq. Palmas, Asunción",
        "phone": None,
        "website": None,
        "rating": 4.7,
        "total_ratings": 9200,
        "opening_hours": {
            "lunes": "07:00 - 19:00",
            "martes": "07:00 - 19:00",
            "miércoles": "07:00 - 19:00",
            "jueves": "07:00 - 19:00",
            "viernes": "07:00 - 19:00",
            "sábado": "07:00 - 19:00",
            "domingo": "07:00 - 19:00"
        },
        "lat": -25.2867,
        "lng": -57.6452,
        "photos": [
            "https://images.unsplash.com/photo-1524492412937-b28074a5d7da?w=1280&q=80",
            "https://images.unsplash.com/photo-1477959858617-67f85cf4f1df?w=1280&q=80"
        ]
    },
    {
        "name": "La Preferida",
        "category": "restaurant",
        "address": "Av. Estados Unidos 341, Asunción",
        "phone": "+595 21 491144",
        "website": None,
        "rating": 4.4,
        "total_ratings": 2100,
        "opening_hours": {
            "lunes": "11:30 - 15:00",
            "martes": "11:30 - 15:00",
            "miércoles": "11:30 - 15:00",
            "jueves": "11:30 - 15:00",
            "viernes": "11:30 - 15:00",
            "sábado": "11:30 - 15:00",
            "domingo": "Cerrado"
        },
        "lat": -25.2950,
        "lng": -57.6380,
        "photos": [
            "https://images.unsplash.com/photo-1414235077428-338989a2e8c0?w=1280&q=80",
            "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=1280&q=80"
        ]
    },
    {
        "name": "Mercado 4",
        "category": "attraction",
        "address": "Av. Dr. Francia, Asunción",
        "phone": None,
        "website": None,
        "rating": 4.0,
        "total_ratings": 3400,
        "opening_hours": {
            "lunes": "06:00 - 18:00",
            "martes": "06:00 - 18:00",
            "miércoles": "06:00 - 18:00",
            "jueves": "06:00 - 18:00",
            "viernes": "06:00 - 18:00",
            "sábado": "06:00 - 18:00",
            "domingo": "06:00 - 14:00"
        },
        "lat": -25.2930,
        "lng": -57.6410,
        "photos": [
            "https://images.unsplash.com/photo-1555396273-367ea4eb4db5?w=1280&q=80",
            "https://images.unsplash.com/photo-1533900298318-6b8da08a523e?w=1280&q=80"
        ]
    },
    {
        "name": "Hotel Sheraton Asunción",
        "category": "hotel",
        "address": "Av. Mcal. López 1066, Asunción",
        "phone": "+595 21 617000",
        "website": "https://www.marriott.com/sheraton",
        "rating": 4.5,
        "total_ratings": 1800,
        "opening_hours": {
            "lunes": "24 horas",
            "martes": "24 horas",
            "miércoles": "24 horas",
            "jueves": "24 horas",
            "viernes": "24 horas",
            "sábado": "24 horas",
            "domingo": "24 horas"
        },
        "lat": -25.2980,
        "lng": -57.6350,
        "photos": [
            "https://images.unsplash.com/photo-1566073771259-6a8506099945?w=1280&q=80",
            "https://images.unsplash.com/photo-1564501049412-61c2a3083791?w=1280&q=80"
        ]
    },
    {
        "name": "Bar San Roque",
        "category": "bar",
        "address": "Eligio Ayala 792, Asunción",
        "phone": "+595 21 446955",
        "website": None,
        "rating": 4.3,
        "total_ratings": 870,
        "opening_hours": {
            "lunes": "Cerrado",
            "martes": "18:00 - 00:00",
            "miércoles": "18:00 - 00:00",
            "jueves": "18:00 - 00:00",
            "viernes": "18:00 - 02:00",
            "sábado": "18:00 - 02:00",
            "domingo": "Cerrado"
        },
        "lat": -25.2910,
        "lng": -57.6395,
        "photos": [
            "https://images.unsplash.com/photo-1572116469696-31de0f17cc34?w=1280&q=80",
            "https://images.unsplash.com/photo-1514362545857-3bc16c4c7d1b?w=1280&q=80"
        ]
    },
    {
        "name": "Museo Casa de la Independencia",
        "category": "museum",
        "address": "14 de Mayo 954, Asunción",
        "phone": "+595 21 493918",
        "website": None,
        "rating": 4.5,
        "total_ratings": 1500,
        "opening_hours": {
            "lunes": "07:00 - 19:00",
            "martes": "07:00 - 19:00",
            "miércoles": "07:00 - 19:00",
            "jueves": "07:00 - 19:00",
            "viernes": "07:00 - 19:00",
            "sábado": "08:00 - 12:00",
            "domingo": "Cerrado"
        },
        "lat": -25.2855,
        "lng": -57.6440,
        "photos": [
            "https://images.unsplash.com/photo-1554907984-15263bfd63bd?w=1280&q=80",
            "https://images.unsplash.com/photo-1513519245088-0e12902e5a38?w=1280&q=80"
        ]
    },
    {
        "name": "Parque Carlos Antonio López",
        "category": "park",
        "address": "Av. Carlos Antonio López, Asunción",
        "phone": None,
        "website": None,
        "rating": 4.1,
        "total_ratings": 640,
        "opening_hours": {
            "lunes": "06:00 - 20:00",
            "martes": "06:00 - 20:00",
            "miércoles": "06:00 - 20:00",
            "jueves": "06:00 - 20:00",
            "viernes": "06:00 - 20:00",
            "sábado": "06:00 - 20:00",
            "domingo": "06:00 - 20:00"
        },
        "lat": -25.2820,
        "lng": -57.6480,
        "photos": [
            "https://images.unsplash.com/photo-1441974231531-c6227db76b6e?w=1280&q=80",
            "https://images.unsplash.com/photo-1519331379826-f10be5486c6f?w=1280&q=80"
        ]
    },
    {
        "name": "Restaurante Tierra Colorada",
        "category": "restaurant",
        "address": "Av. Brasilia 1000, Asunción",
        "phone": "+595 21 610555",
        "website": None,
        "rating": 4.6,
        "total_ratings": 1100,
        "opening_hours": {
            "lunes": "12:00 - 15:00",
            "martes": "12:00 - 15:00",
            "miércoles": "12:00 - 15:00",
            "jueves": "12:00 - 15:00",
            "viernes": "12:00 - 15:00",
            "sábado": "12:00 - 22:00",
            "domingo": "12:00 - 16:00"
        },
        "lat": -25.3010,
        "lng": -57.6290,
        "photos": [
            "https://images.unsplash.com/photo-1414235077428-338989a2e8c0?w=1280&q=80",
            "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=1280&q=80"
        ]
    }
]

def seed():
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur = conn.cursor()

    # Limpiar tablas en orden correcto por las foreign keys
    cur.execute("DELETE FROM route_places")
    cur.execute("DELETE FROM routes")
    cur.execute("DELETE FROM places")
    print("Tablas limpiadas")

    # Insertar lugares
    for place in places:
        cur.execute("""
            INSERT INTO places (
                name, category, address, phone, website,
                rating, total_ratings, opening_hours,
                location, photos
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s,
                ST_MakePoint(%s, %s)::geography,
                %s
            )
        """, (
            place["name"],
            place["category"],
            place["address"],
            place["phone"],
            place["website"],
            place["rating"],
            place["total_ratings"],
            json.dumps(place["opening_hours"]),
            place["lng"],
            place["lat"],
            json.dumps(place["photos"])
        ))

    print(f"✓ {len(places)} lugares insertados")

    # Insertar rutas predeterminadas
    for route in routes:
        cur.execute("""
            INSERT INTO routes (name, description, is_preset, start_time)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (route["name"], route["description"], route["is_preset"], route["start_time"]))

        route_id = cur.fetchone()[0]

        for index, place_name in enumerate(route["places"]):
            cur.execute("""
                INSERT INTO route_places (route_id, place_id, order_index)
                SELECT %s, id, %s FROM places WHERE name = %s
            """, (route_id, index, place_name))

    print(f"✓ {len(routes)} rutas predeterminadas insertadas")

    conn.commit()
    cur.close()
    conn.close()

routes = [
    {
        "name": "Centro Histórico",
        "description": "Recorrido por los principales monumentos y museos del centro de Asunción",
        "is_preset": True,
        # Panteón abre 07:00
        "start_time": "07:00",
        "places": [
            "Panteón Nacional de los Héroes",
            "Museo Casa de la Independencia",
            "Museo del Barro",
            "Mercado 4"
        ]
    },
    {
        "name": "Naturaleza y Relax",
        "description": "Parques y espacios verdes para desconectarse de la ciudad",
        "is_preset": True,
        # Jardín Botánico abre 07:00
        "start_time": "07:00",
        "places": [
            "Jardín Botánico y Zoológico de Asunción",
            "Parque Carlos Antonio López",
            "Restaurante Tierra Colorada"
        ]
    },
    {
        "name": "Gastronomía Asuncena",
        "description": "Los mejores restaurantes y bares típicos de la ciudad",
        "is_preset": True,
        # La Preferida abre 11:30
        "start_time": "11:30",
        "places": [
            "La Preferida",
            "Restaurante Tierra Colorada",
            "Bar San Roque"
        ]
    }
]

if __name__ == "__main__":
    seed()