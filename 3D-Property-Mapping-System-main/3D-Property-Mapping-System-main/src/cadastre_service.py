# src/cadastre_service.py
import hashlib
import json
from pathlib import Path
from typing import Dict, Any, List

SAMPLE_OWNERS = [
    "Shri Rajesh & Smt. Ananya Deshmukh",
    "Nariman Commercial Holdings Pvt. Ltd.",
    "Shri Vikramaditya Singhania",
    "Dr. Homi Bhabha Memorial Trust",
    "State Bank of India Corporate Treasury",
    "Smt. Pheroza Godrej & Family",
    "Shri Cyrus & Smt. Shireen Mistry",
    "Maharashtra State Financial Corporation",
    "Shri Anand G. Mahindra Trust",
    "Reserve Bank Officers Housing Society",
    "Smt. Radhika Merchant & Shri Anant Piramal",
    "Forbes & Campbell Heritage Properties",
    "Shri Jamshedji Tata Trust Estates",
    "Kothari & Mehta Chambers LLP",
    "Smt. Sunita Kapoor & Shri Devendra Kapoor",
    "Churchgate Heritage Preservation Trust",
    "Shri Ashwin Dani Family Trust",
    "Mumbai Municipal Officers Syndicate",
    "Smt. Meenakshi Sundaram Iyer",
    "Shri Gautam Adani Infrastructure Capital"
]

UNIT_TYPES_RESIDENTIAL = [
    "1BHK Heritage Studio",
    "2BHK Luxury Sea-Facing Flat",
    "3BHK Premium Executive Suite",
    "3.5BHK Master Penthouse Unit",
    "4BHK Duplex Sky Mansion"
]

UNIT_TYPES_COMMERCIAL = [
    "Corporate Headquarters Suite",
    "Private Equity Trading Office",
    "Chartered Accountancy Chambers",
    "Legal Arbitrage & Solicitor Office",
    "Consulate General Commercial Annex",
    "High-Net-Worth Advisory Lounge"
]

def get_cadastral_division(street: str, lat: float = 18.9280, lon: float = 72.8270) -> str:
    s_lower = street.lower()
    if "nariman" in s_lower:
        return "Nariman Point Division"
    elif "churchgate" in s_lower:
        return "Churchgate Corridor Division"
    elif "fort" in s_lower or "dalal" in s_lower:
        return "Fort Financial Division"
    elif "colaba" in s_lower or "cuffe" in s_lower:
        return "Colaba & Apollo Division"
    else:
        if lat < 18.9220:
            return "Colaba & Apollo Division"
        elif lon < 72.8250:
            return "Nariman Point Division"
        elif lat > 18.9320 and lon < 72.8300:
            return "Churchgate Corridor Division"
        else:
            return "Fort Financial Division"

def generate_land_ulpin(spatial_id: str, lat: float = 18.9280, lon: float = 72.8270) -> str:
    """
    Generates standard 14-digit Indian Bhu-Aadhaar ULPIN.
    Prefix: 27 (Maharashtra) + 01 (Mumbai City District) + 10 digits derived from coordinates/hash.
    """
    seed_str = f"{spatial_id}:{round(lat, 4)}:{round(lon, 4)}"
    h = int(hashlib.sha256(seed_str.encode()).hexdigest()[:10], 16)
    parcel_digits = str(h)[-10:].zfill(10)
    return f"2701{parcel_digits}"

def generate_cts_no(spatial_id: str, division: str) -> str:
    """
    Generates realistic Cadastral Survey / City Title Survey (CTS) number.
    """
    h = int(hashlib.md5(spatial_id.encode()).hexdigest()[:6], 16)
    cts_num = 100 + (h % 900)
    sub = chr(65 + (h % 8))  # A through H
    return f"CTS No. {cts_num}/{sub}, {division}"

def generate_building_cadastre(building_props: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generates the complete 3D Cadastre hierarchy:
    Building -> Wing -> Floor -> Flat -> ULPIN
    """
    spatial_id = building_props.get("spatial_id", "MUM-BLD-00000000")
    name = building_props.get("name", "South Mumbai Urban Structure")
    street = building_props.get("street", "South Mumbai Urban Zone")
    floors_count = int(building_props.get("floors", 5))
    height_m = float(building_props.get("height_m", floors_count * 3.4))
    floor_area = float(building_props.get("floor_area_sqm", 250.0))
    total_area = float(building_props.get("area_sqm", floor_area * floors_count))
    length_m = float(building_props.get("length_m", 30.0))
    breadth_m = float(building_props.get("breadth_m", 20.0))

    division = get_cadastral_division(street)
    land_ulpin = building_props.get("land_ulpin") or generate_land_ulpin(spatial_id)
    cts_no = building_props.get("cts_no") or generate_cts_no(spatial_id, division)

    # Determine Wings
    if total_area > 3500 or length_m > 70:
        wings = [
            {"wing_id": "Wing A", "wing_name": "East Wing (Tower A)", "flats_per_floor": 2},
            {"wing_id": "Wing B", "wing_name": "West Wing (Tower B)", "flats_per_floor": 2}
        ]
    elif total_area > 6000:
        wings = [
            {"wing_id": "Wing A", "wing_name": "North Tower", "flats_per_floor": 2},
            {"wing_id": "Wing B", "wing_name": "South Tower", "flats_per_floor": 2},
            {"wing_id": "Wing C", "wing_name": "Central Core Wing", "flats_per_floor": 1}
        ]
    else:
        wings = [
            {"wing_id": "Wing A", "wing_name": "Main Wing", "flats_per_floor": 4 if floor_area > 300 else 2}
        ]

    is_commercial = ("tower" in name.lower() or "chambers" in name.lower() or "bse" in name.lower() or
                     "bank" in name.lower() or "house" in name.lower() or "theatre" in name.lower() or
                     "financial" in division.lower() or "nariman" in street.lower())

    unit_types_pool = UNIT_TYPES_COMMERCIAL if is_commercial else UNIT_TYPES_RESIDENTIAL

    total_units = 0
    floors_list: List[Dict[str, Any]] = []
    floor_height_m = round(height_m / max(floors_count, 1), 2)

    for fl_idx in range(floors_count):
        fl_num = fl_idx + 1
        fl_label = "Ground Floor" if fl_idx == 0 else ("Terrace & Penthouse" if fl_idx == floors_count - 1 else f"Floor {fl_num}")
        elevation_base = round(fl_idx * floor_height_m, 2)
        elevation_top = round((fl_idx + 1) * floor_height_m, 2)

        floor_units: List[Dict[str, Any]] = []
        unit_counter = 1

        for w_idx, wing in enumerate(wings):
            flats_in_wing = wing["flats_per_floor"]
            for u_in_w in range(flats_in_wing):
                unit_number = f"G{str(unit_counter).zfill(2)}" if fl_idx == 0 else f"{fl_num}{str(unit_counter).zfill(2)}"
                wing_code = wing["wing_id"].replace("Wing ", "W")
                unit_ulpin = f"{land_ulpin}-{wing_code}-FL{str(fl_num).zfill(2)}-U{unit_number}"

                # Deterministic seed for unit owner and area
                u_seed = f"{spatial_id}:{fl_idx}:{wing['wing_id']}:{unit_number}"
                h_val = int(hashlib.md5(u_seed.encode()).hexdigest()[:8], 16)

                owner = SAMPLE_OWNERS[h_val % len(SAMPLE_OWNERS)]
                u_type = unit_types_pool[(h_val // 7) % len(unit_types_pool)]
                if fl_idx == floors_count - 1 and not is_commercial:
                    u_type = "Sky Villa Penthouse"

                # Subdivide floor area
                total_flats_floor = sum(w["flats_per_floor"] for w in wings)
                est_carpet_sqm = round((floor_area / max(total_flats_floor, 1)) * 0.78, 2)
                est_builtup_sqm = round(est_carpet_sqm * 1.25, 2)
                est_carpet_sqft = round(est_carpet_sqm * 10.7639, 1)

                uds_pct = round(100.0 / max(floors_count * total_flats_floor, 1), 2)
                prop_card_no = f"MH-MUM-VPC-2024-{str(h_val)[-6:]}"
                sac_no = f"SAC-01{wing['wing_id'][-1]}-{str(1000 + (h_val % 8999))}-{str(unit_counter).zfill(3)}"

                # Assign quadrant index (0: NE, 1: NW, 2: SW, 3: SE)
                quadrant = (unit_counter - 1) % 4

                unit_obj = {
                    "unit_id": f"UNIT-{fl_idx}-{unit_counter}",
                    "unit_number": unit_number,
                    "wing_id": wing["wing_id"],
                    "wing_name": wing["wing_name"],
                    "floor_index": fl_idx,
                    "floor_number": fl_num,
                    "unit_ulpin": unit_ulpin,
                    "unit_type": u_type,
                    "carpet_area_sqm": est_carpet_sqm,
                    "carpet_area_sqft": est_carpet_sqft,
                    "built_up_area_sqm": est_builtup_sqm,
                    "uds_percentage": f"{uds_pct}%",
                    "property_card_no": prop_card_no,
                    "cts_no": cts_no,
                    "tax_assessment_sac": sac_no,
                    "owner_name": owner,
                    "occupancy_status": "Owner Occupied / Clear Freehold",
                    "registration_status": "MahaBhumi 3D Cadastre Verified",
                    "stamp_duty_paid": True,
                    "quadrant": quadrant,
                    "elevation_base_m": elevation_base,
                    "elevation_top_m": elevation_top
                }
                floor_units.append(unit_obj)
                unit_counter += 1
                total_units += 1

        floors_list.append({
            "floor_index": fl_idx,
            "floor_number": fl_num,
            "floor_label": fl_label,
            "elevation_base_m": elevation_base,
            "elevation_top_m": elevation_top,
            "height_m": floor_height_m,
            "units_count": len(floor_units),
            "units": floor_units
        })

    return {
        "spatial_id": spatial_id,
        "name": name,
        "street": street,
        "cadastral_division": division,
        "land_ulpin": land_ulpin,
        "cts_no": cts_no,
        "floors_count": floors_count,
        "height_m": height_m,
        "floor_height_m": floor_height_m,
        "footprint_area_sqm": total_area,
        "floor_plate_sqm": floor_area,
        "length_m": length_m,
        "breadth_m": breadth_m,
        "total_units": total_units,
        "category": "Commercial High-Rise" if is_commercial else "Residential Twin Tower",
        "wings": wings,
        "floors": floors_list
    }

