import json
import os
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, Response
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
import uvicorn

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=False)
GOOGLE_3D_TILES_API_KEY = os.getenv("GOOGLE_3D_TILES_API_KEY", "").strip()

from src.cadastre_service import generate_building_cadastre

app = FastAPI(title="South Mumbai 3D Urban Architecture Twin - Vertical ULPIN Cadastre")
app.add_middleware(GZipMiddleware, minimum_size=1000)

@app.middleware("http")
async def add_no_cache_headers(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

BUILDINGS_PATH = BASE_DIR / "data" / "processed" / "buildings.geojson"
ARCH_BUILDINGS_PATH = BASE_DIR / "data" / "processed" / "buildings_3d_architectural.geojson"
UTILITIES_PATH = BASE_DIR / "data" / "processed" / "utilities.geojson"

if not BUILDINGS_PATH.exists() or not ARCH_BUILDINGS_PATH.exists() or not UTILITIES_PATH.exists():
    from src.ingest_south_mumbai import build_south_mumbai_dataset
    build_south_mumbai_dataset()

CACHED_BUILDINGS_INDEX = {}

def load_buildings_index():
    global CACHED_BUILDINGS_INDEX
    if BUILDINGS_PATH.exists():
        with open(BUILDINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            for feat in data.get("features", []):
                sp_id = feat.get("properties", {}).get("spatial_id")
                if sp_id:
                    CACHED_BUILDINGS_INDEX[sp_id] = feat

load_buildings_index()

@app.get("/api/buildings")
def get_buildings():
    return FileResponse(BUILDINGS_PATH, media_type="application/geo+json")

@app.get("/api/buildings/architectural")
def get_architectural_buildings():
    if not ARCH_BUILDINGS_PATH.exists():
        from src.ingest_south_mumbai import build_architectural_3d_buildings
        build_architectural_3d_buildings()
    return FileResponse(ARCH_BUILDINGS_PATH, media_type="application/geo+json")

@app.get("/api/utilities")
def get_utilities():
    return FileResponse(UTILITIES_PATH, media_type="application/geo+json")

@app.get("/api/building/{spatial_id}/cadastre")
def get_building_cadastre_endpoint(spatial_id: str):
    feat = CACHED_BUILDINGS_INDEX.get(spatial_id)
    if not feat:
        with open(BUILDINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            for item in data.get("features", []):
                if item.get("properties", {}).get("spatial_id") == spatial_id:
                    feat = item
                    break
    if not feat:
        raise HTTPException(status_code=404, detail="Building not found in South Mumbai cadastral registry.")
    
    props = feat.get("properties", {})
    cadastre = generate_building_cadastre(props)
    cadastre["geometry"] = feat.get("geometry", {})
    return JSONResponse(content=cadastre)

def _find_cadastre_unit(cadastre, unit_id: Optional[str]):
    if not unit_id:
        return None
    return next(
        (unit for floor in cadastre["floors"] for unit in floor["units"] if unit["unit_id"] == unit_id),
        None,
    )

def _build_property_document(spatial_id: str, unit_id: Optional[str] = None) -> tuple[bytes, str]:
    feat = CACHED_BUILDINGS_INDEX.get(spatial_id)
    if not feat:
        raise HTTPException(status_code=404, detail="Building not found in South Mumbai cadastral registry.")
    cadastre = generate_building_cadastre(feat.get("properties", {}))
    unit = _find_cadastre_unit(cadastre, unit_id)
    if unit_id and unit is None:
        raise HTTPException(status_code=404, detail="Vertical unit not found in cadastral registry.")
    record = unit or {
        "unit_number": "Land Parcel", "wing_name": "", "floor_label": "Land record",
        "unit_ulpin": cadastre["land_ulpin"], "unit_type": cadastre["category"],
        "carpet_area_sqm": cadastre["footprint_area_sqm"],
        "owner_name": "Registered ownership details held in the land parcel record",
        "property_card_no": "See CTS / property card register",
        "tax_assessment_sac": "N/A",
    }
    issued_on = datetime.now(timezone.utc).strftime("%d-%m-%Y")
    filename = f"{record['unit_ulpin'].replace('/', '-')}-property-ownership-details.pdf"
    buffer = BytesIO()
    font_candidates = [
        (BASE_DIR / "assets" / "NotoSansDevanagari-Regular.ttf", BASE_DIR / "assets" / "NotoSansDevanagari-Bold.ttf"),
        (Path("C:/Windows/Fonts/mangal.ttf"), Path("C:/Windows/Fonts/mangalb.ttf")),
        (Path("C:/Windows/Fonts/kokila.ttf"), Path("C:/Windows/Fonts/kokilab.ttf")),
    ]
    devanagari_font = next(
        ((regular, bold) for regular, bold in font_candidates if regular.exists() and bold.exists()),
        None,
    )
    if devanagari_font is None:
        raise HTTPException(
            status_code=500,
            detail="A Devanagari font (Mangal or Kokila) is required to render the Hindi government header.",
        )
    regular_font, bold_font = devanagari_font
    pdfmetrics.registerFont(TTFont("GovernmentDevanagari", str(regular_font)))
    pdfmetrics.registerFont(TTFont("GovernmentDevanagari-Bold", str(bold_font)))
    styles = getSampleStyleSheet()
    navy = colors.HexColor("#17365d")
    styles.add(ParagraphStyle(name="DocLabel", parent=styles["Normal"], fontName="Times-Bold", fontSize=10.5, leading=12, textColor=navy))
    styles.add(ParagraphStyle(name="DocValue", parent=styles["Normal"], fontName="Times-Roman", fontSize=10.5, leading=12, textColor=navy))
    styles.add(ParagraphStyle(name="DocHeader", parent=styles["Normal"], fontName="Times-Bold", fontSize=14, leading=15, alignment=1, textColor=navy))
    styles.add(ParagraphStyle(name="HindiHeader", parent=styles["Normal"], fontName="GovernmentDevanagari-Bold", fontSize=16, leading=17, alignment=1, textColor=navy))
    styles.add(ParagraphStyle(name="DocSubheader", parent=styles["Normal"], fontName="Times-Roman", fontSize=8.5, leading=9.2, alignment=1, textColor=navy))
    styles.add(ParagraphStyle(name="SectionTitle", parent=styles["Normal"], fontName="Times-Bold", fontSize=11, leading=13, textColor=navy))
    emblem = Image(str(BASE_DIR / "assets" / "emblem-of-india-user.png"), width=21 * mm, height=29 * mm)
    ministry_mark = Image(str(BASE_DIR / "assets" / "ministry-rural-development-user.jpg"), width=48 * mm, height=22 * mm)

    def section(title, rows):
        return [
            Table([[Paragraph(title, styles["SectionTitle"])]], colWidths=[182 * mm], style=TableStyle([
                ("LINEBELOW", (0, 0), (-1, -1), 1, navy),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ])),
            Table([[Paragraph(label, styles["DocLabel"]), Paragraph(str(value), styles["DocValue"])] for label, value in rows],
                  colWidths=[51 * mm, 131 * mm], style=TableStyle([
                      ("LINEBELOW", (0, 0), (-1, -1), 0.35, colors.HexColor("#b8c5d1")),
                      ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 6),
                      ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                      ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
                  ])),
            Spacer(1, 3 * mm),
        ]

    story = [
        Table([[emblem, [
            Paragraph("भारत सरकार", styles["HindiHeader"]),
            Paragraph("ग्रामीण विकास मंत्रालय", styles["HindiHeader"]),
            Paragraph("Government of India", styles["DocHeader"]),
            Paragraph("Ministry of Rural Development", styles["DocHeader"]),
            Paragraph("Department of Land Resources", styles["DocSubheader"]),
            Paragraph("(Digital India Land Records Modernization Programme)", styles["DocSubheader"]),
        ], ministry_mark]], colWidths=[26 * mm, 114 * mm, 42 * mm], style=TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (2, 0), (2, 0), "RIGHT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ])),
        Spacer(1, 1.5 * mm),
        Table([[""]], colWidths=[182 * mm], rowHeights=[0.6 * mm], style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), navy),
        ])),
        Spacer(1, 3.5 * mm),
        Paragraph("PROPERTY OWNERSHIP DETAILS", styles["DocHeader"]),
        Paragraph("(ULPIN BASED LAND & BUILDING INFORMATION)", styles["DocSubheader"]),
        Paragraph("Issued under the authority of the Ministry of Rural Development, Government of India", styles["DocSubheader"]),
        Spacer(1, 2 * mm),
        Table([["", Paragraph(f"Document No.: MRD/ULPIN/{datetime.now(timezone.utc).year}/{spatial_id[-6:]}<br/>Date of Issue: {issued_on}", styles["DocValue"])]
               ], colWidths=[105 * mm, 67 * mm], style=TableStyle([("ALIGN", (1, 0), (1, 0), "RIGHT")])),
    ]
    story.extend(section("1. PROPERTY / BUILDING DETAILS", [
        ("Building Name", cadastre["name"]), ("Location / Address", cadastre["street"]),
        ("Land ULPIN", cadastre["land_ulpin"]), ("CTS No.", cadastre["cts_no"]),
        ("District", "Mumbai"), ("State", "Maharashtra"),
        ("Cadastral Division", cadastre["cadastral_division"]),
    ]))
    story.extend(section("2. UNIT DETAILS", [
        ("Unit No.", f"Flat {record['unit_number']}, {record['wing_name']}, {record.get('floor_label', 'Selected floor')}"),
        ("Vertical ULPIN", record["unit_ulpin"]), ("Unit Type", record["unit_type"]),
        ("Floor", record.get("floor_label", "Selected floor")),
        ("Carpet Area", f"{record['carpet_area_sqm']} sq.m"),
        ("Built-up Area", f"{record.get('built_up_area_sqm', 'N/A')} sq.m"),
        ("Undivided Share", str(record.get("uds_percentage", "N/A"))),
    ]))
    story.extend(section("3. OWNER DETAILS", [
        ("Owner Name", record["owner_name"]), ("Ownership Type", "Registered titleholder / cadastral owner"),
        ("Address", f"{cadastre['street']}, Mumbai - 400 001"), ("Property Card No.", record["property_card_no"]),
        ("Registration No.", record["tax_assessment_sac"]),
        ("Tax Assessment / SAC", record["tax_assessment_sac"]),
    ]))
    story.extend(section("4. ULPIN SUMMARY", [
        ("Base Parcel ULPIN", cadastre["land_ulpin"]), ("Vertical Unit ULPIN", record["unit_ulpin"]),
        ("Cadastral Division", cadastre["cadastral_division"]),
        ("Title Status", "Freehold / Clear title - MahaBhumi 3D Cadastre Verified"),
    ]))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph("This digitally generated preview is based on the cadastral data available in this application. It is not a legal title deed and must be verified against the department's official records.", styles["DocSubheader"]))
    document = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=10 * mm, leftMargin=10 * mm, topMargin=5 * mm, bottomMargin=5 * mm, title="Property Ownership Details")
    document.build(story)
    return buffer.getvalue(), filename

@app.get("/api/building/{spatial_id}/document")
def preview_property_document(spatial_id: str, unit_id: Optional[str] = None):
    content, filename = _build_property_document(spatial_id, unit_id)
    return Response(content=content, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{filename}"'})

@app.get("/api/building/{spatial_id}/document/download")
def download_property_document(spatial_id: str, unit_id: Optional[str] = None):
    content, filename = _build_property_document(spatial_id, unit_id)
    return Response(content=content, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})

@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    google_key_literal = json.dumps(GOOGLE_3D_TILES_API_KEY)
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>South Mumbai 3D Urban Architecture Twin - Vertical ULPIN Cadastre</title>
    <meta name="viewport" content="initial-scale=1,maximum-scale=1,user-scalable=no">
    <!-- Fonts & Icons -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;600;700&display=swap" rel="stylesheet">
    <!-- CesiumJS -->
    <script src="https://cdn.jsdelivr.net/npm/cesium@1.124.0/Build/Cesium/Cesium.js"></script>
    <link href="https://cdn.jsdelivr.net/npm/cesium@1.124.0/Build/Cesium/Widgets/widgets.css" rel="stylesheet" />
    <!-- MapLibre GL JS -->
    <script src="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.js"></script>
    <link href="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.css" rel="stylesheet" />
    <!-- Three.js & OrbitControls -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
    <!-- React 18 & Babel -->
    <script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
    <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
    <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>

    <style>
        :root {
            --bg-dark: #090d16;
            --bg-card: #0f172a;
            --bg-card-hover: #1e293b;
            --bg-card-subtle: #131b2e;
            --accent-cyan: #38bdf8;
            --accent-blue: #2563eb;
            --accent-emerald: #10b981;
            --accent-amber: #f59e0b;
            --border-subtle: rgba(255, 255, 255, 0.08);
            --border-medium: rgba(255, 255, 255, 0.15);
            --border-glow: rgba(37, 99, 235, 0.3);
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --text-dim: #64748b;
            --shadow-panel: 0 16px 36px -4px rgba(0, 0, 0, 0.65), 0 2px 8px rgba(0, 0, 0, 0.4);
        }

        * { box-sizing: border-box; }
        body, html {
            margin: 0; padding: 0; width: 100%; height: 100%;
            font-family: 'Plus Jakarta Sans', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg-dark); color: var(--text-primary);
            overflow: hidden; user-select: none;
        }

        #map, #fallback-map { position: absolute; top: 0; bottom: 0; width: 100%; height: 100%; }
        #map { display: block; background: #090d16; }
        #fallback-map { display: none; }
        .cesium-viewer { background: #090d16; }

        ::-webkit-scrollbar { width: 5px; height: 5px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #334155; border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: #475569; }

        .glass-panel {
            background: #0f172a;
            border: 1px solid var(--border-subtle);
            border-radius: 10px;
            box-shadow: var(--shadow-panel);
        }

        .code-font {
            font-family: 'JetBrains Mono', 'Fira Code', monospace;
        }

        #viewport-tooltip {
            position: absolute; display: none; pointer-events: none; z-index: 50;
            background: #ffffff; border: 1px solid #D5DCE3;
            border-radius: 4px; padding: 7px 11px; font-size: 11px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12);
            color: #263238;
            transform: translate(-50%, -120%); transition: opacity 0.15s;
        }

        #twin-workspace {
            position: absolute; top: 0; left: 0; width: 100vw; height: 100vh;
            background: #CBD7E3;
            z-index: 40; display: none; flex-direction: column;
        }

        #twin-canvas-container {
            flex: 1; width: 100%; height: 100%; position: relative; overflow: hidden;
        }

        /* Clean Engineering Slider */
        input[type=range] {
            -webkit-appearance: none;
            appearance: none;
            width: 100%;
            height: 4px;
            border-radius: 2px;
            background: #334155;
            outline: none;
            cursor: pointer;
        }
        input[type=range]::-webkit-slider-thumb {
            -webkit-appearance: none;
            appearance: none;
            width: 14px;
            height: 14px;
            border-radius: 50%;
            background: #2563eb;
            border: 2px solid #ffffff;
            cursor: pointer;
            box-shadow: 0 1px 4px rgba(0,0,0,0.5);
            transition: transform 0.12s ease, background 0.12s ease;
        }
        input[type=range]::-webkit-slider-thumb:hover {
            transform: scale(1.2);
            background: #3b82f6;
        }

        .pulsing-dot {
            width: 7px; height: 7px; border-radius: 50%; background: #10b981;
            display: inline-block;
        }

        #react-root {
            position: absolute; top: 0; left: 0; width: 100%; height: 100%;
            pointer-events: none; z-index: 45;
        }
        #react-root > * {
            pointer-events: auto;
        }

        /* 3D Subterranean Interactive Inspection Popup */
        .maplibregl-popup {
            z-index: 80 !important;
            pointer-events: auto !important;
        }
        .maplibregl-popup-content {
            background: #0f172a !important;
            border: 1px solid var(--border-medium) !important;
            border-radius: 10px !important;
            padding: 14px 16px !important;
            color: #f8fafc !important;
            box-shadow: var(--shadow-panel) !important;
            width: 320px !important;
            max-width: 320px !important;
            box-sizing: border-box !important;
            overflow: hidden !important;
        }
        .maplibregl-popup-tip {
            border-top-color: #0f172a !important;
            border-bottom-color: #0f172a !important;
        }
        .maplibregl-popup-close-button {
            color: #94a3b8 !important;
            font-size: 18px !important;
            line-height: 1 !important;
            padding: 4px 8px !important;
            right: 8px !important;
            top: 8px !important;
            border-radius: 6px !important;
            cursor: pointer !important;
            z-index: 10 !important;
        }
        .maplibregl-popup-close-button:hover {
            color: #fff !important;
            background: rgba(255, 255, 255, 0.1) !important;
        }
    </style>
</head>
<body>
    <div id="map"></div>
    <div id="fallback-map"></div>


    <div id="twin-workspace">
        <div id="twin-canvas-container">
            <div id="viewport-tooltip">
                <div id="tt-title" style="font-weight: 700; color: #20364A; font-size: 11.5px; margin-bottom: 2px;"></div>
                <div id="tt-sub" style="color: #66717A; font-size: 10.5px;"></div>
                <div id="tt-ulpin" class="code-font" style="color: #2563A6; font-weight: 600; font-size: 10px; margin-top: 4px;"></div>
            </div>
            <!-- 3D Real-time Projected Unit Callout Pin -->
            <div id="unit-3d-pin" style="position: absolute; pointer-events: none; transform: translate(-50%, -100%); z-index: 55; display: none;">
                <div id="unit-3d-pin-label" style="background: #20364A; color: #ffffff; border: 1px solid #D5DCE3; border-radius: 4px; padding: 3px 8px; font-size: 11px; font-weight: 600; box-shadow: 0 2px 6px rgba(0,0,0,0.25); white-space: nowrap; display: inline-block;">
                    Flat 504
                </div>
                <div style="width: 1.5px; height: 16px; background: #20364A; margin: 0 auto;"></div>
                <div style="width: 5px; height: 5px; background: #2563A6; border: 1.5px solid #ffffff; border-radius: 50%; margin: -3px auto 0; box-shadow: 0 1px 3px rgba(0,0,0,0.3);"></div>
            </div>
        </div>
    </div>

    <div id="react-root"></div>

    <script type="text/babel">
        const { useState, useEffect, useRef } = React;

        const GOOGLE_3D_TILES_API_KEY = __GOOGLE_3D_TILES_API_KEY__;
        const SOUTH_MUMBAI = { lon: 72.8270, lat: 18.9280 };

        window.appBridge = {
            openDigitalTwin: null,
            closeDigitalTwin: null,
            selectFlat: null,
            selectFloor: null,
            currentBuilding: null,
            currentCadastre: null
        };

        class ArchitecturalDigitalTwinRenderer {
            constructor(containerId) {
                this.container = document.getElementById(containerId);
                this.scene = null;
                this.camera = null;
                this.renderer = null;
                this.controls = null;
                this.animId = null;

                this.buildingData = null;
                this.cadastreData = null;

                this.floorGroups = [];
                this.flatMeshes = [];
                this.allInteractiveMeshes = [];

                this.selectedFlatId = null;
                this.selectedFloorIndex = null;

                this.explodeRatio = 0.0;
                this.targetExplodeRatio = 0.0;

                this.raycaster = new THREE.Raycaster();
                this.mouse = new THREE.Vector2();

                this.materials = this.initMaterials();

                this.camTween = {
                    active: false,
                    startPos: new THREE.Vector3(),
                    targetPos: new THREE.Vector3(),
                    startLook: new THREE.Vector3(),
                    targetLook: new THREE.Vector3(),
                    progress: 0,
                    duration: 45
                };

                this.init();
            }

            initMaterials() {
                return {
                    slabConcrete: new THREE.MeshStandardMaterial({
                        color: 0xd8e2ec, roughness: 0.55, metalness: 0.08
                    }),
                    slabEdge: new THREE.MeshStandardMaterial({
                        color: 0x8295a8, roughness: 0.45, metalness: 0.15
                    }),
                    roofSlate: new THREE.MeshStandardMaterial({
                        color: 0x475569, roughness: 0.65, metalness: 0.25
                    }),
                    exteriorStone: new THREE.MeshStandardMaterial({
                        color: 0xbac7d5, roughness: 0.6, metalness: 0.1
                    }),
                    exteriorAccent: new THREE.MeshStandardMaterial({
                        color: 0x1e293b, roughness: 0.4, metalness: 0.35
                    }),
                    windowGlass: new THREE.MeshStandardMaterial({
                        color: 0x2b6cb0, roughness: 0.12, metalness: 0.35,
                        transparent: true, opacity: 0.72
                    }),
                    windowGlassWarm: new THREE.MeshStandardMaterial({
                        color: 0x3182ce, roughness: 0.15, metalness: 0.3,
                        transparent: true, opacity: 0.72
                    }),
                    aluminumFrame: new THREE.MeshStandardMaterial({
                        color: 0x1e293b, roughness: 0.35, metalness: 0.85
                    }),
                    balconyDeck: new THREE.MeshStandardMaterial({
                        color: 0x94a3b8, roughness: 0.7, metalness: 0.1
                    }),
                    balconyGlassRailing: new THREE.MeshStandardMaterial({
                        color: 0x60a5fa, roughness: 0.2, metalness: 0.2,
                        transparent: true, opacity: 0.65
                    }),
                    metalRailing: new THREE.MeshStandardMaterial({
                        color: 0x334155, roughness: 0.35, metalness: 0.8
                    }),
                    entranceDoor: new THREE.MeshStandardMaterial({
                        color: 0x1e40af, roughness: 0.15, metalness: 0.3,
                        transparent: true, opacity: 0.8
                    }),
                    roofHVAC: new THREE.MeshStandardMaterial({
                        color: 0x64748b, roughness: 0.55, metalness: 0.6
                    }),
                    flatFloorSelected: new THREE.MeshStandardMaterial({
                        color: 0x1d4ed8, emissive: 0x1e40af, emissiveIntensity: 0.5,
                        roughness: 0.2, metalness: 0.2, transparent: true, opacity: 0.94
                    }),
                    ghostedMaterial: new THREE.MeshStandardMaterial({
                        color: 0x94a3b8, roughness: 0.3, transparent: true, opacity: 0.18
                    })
                };
            }

            init() {
                const w = this.container.clientWidth || window.innerWidth;
                const h = this.container.clientHeight || window.innerHeight;

                this.scene = new THREE.Scene();
                // Professional Architectural Studio Viewport Canvas (Soft Slate Gradient)
                const bgCanvas = document.createElement('canvas');
                bgCanvas.width = 2;
                bgCanvas.height = 512;
                const ctx = bgCanvas.getContext('2d');
                const grad = ctx.createLinearGradient(0, 0, 0, 512);
                grad.addColorStop(0.0, '#AEC0D2');    // Soft atmospheric slate-blue sky
                grad.addColorStop(0.55, '#C6D4E2');   // Subtle horizon depth
                grad.addColorStop(1.0, '#DDE5EE');   // Clean ground blend
                ctx.fillStyle = grad;
                ctx.fillRect(0, 0, 2, 512);
                this.scene.background = new THREE.CanvasTexture(bgCanvas);

                this.camera = new THREE.PerspectiveCamera(42, w / h, 0.5, 3000);

                this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
                this.renderer.setSize(w, h);
                this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
                this.renderer.shadowMap.enabled = true;
                this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
                this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
                this.renderer.toneMappingExposure = 1.0;
                this.container.appendChild(this.renderer.domElement);

                if (typeof THREE.OrbitControls !== 'undefined') {
                    this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
                    this.controls.enableDamping = true;
                    this.controls.dampingFactor = 0.06;
                    this.controls.maxPolarAngle = Math.PI / 2 - 0.03;
                    this.controls.minDistance = 6;
                    this.controls.maxDistance = 600;
                } else {
                    this.controls = { target: new THREE.Vector3(0, 20, 0), update: () => {} };
                    this.setupFallbackControls();
                }

                this.setupLighting();
                this.setupGround();

                window.addEventListener('resize', () => this.onResize());
                this.renderer.domElement.addEventListener('mousemove', (e) => this.onMouseMove(e));
                this.renderer.domElement.addEventListener('click', (e) => this.onClick(e));

                this.animate = this.animate.bind(this);
                this.animate();
            }

            setupLighting() {
                // Soft ambient sky illumination (calibrated to prevent bleaching)
                const ambient = new THREE.AmbientLight(0xdbeafe, 0.35);
                this.scene.add(ambient);

                // Balanced hemisphere light (sky reflection vs ground bounce)
                const hemiLight = new THREE.HemisphereLight(0xf1f5f9, 0x475569, 0.35);
                hemiLight.position.set(0, 200, 0);
                this.scene.add(hemiLight);

                // Key architectural directional sunlight casting crisp shadows
                const sun = new THREE.DirectionalLight(0xfffaf0, 1.15);
                sun.position.set(120, 220, 140);
                sun.castShadow = true;
                sun.shadow.mapSize.width = 2048;
                sun.shadow.mapSize.height = 2048;
                sun.shadow.camera.near = 10;
                sun.shadow.camera.far = 600;
                const d = 100;
                sun.shadow.camera.left = -d;
                sun.shadow.camera.right = d;
                sun.shadow.camera.top = d;
                sun.shadow.camera.bottom = -d;
                sun.shadow.bias = -0.0004;
                this.scene.add(sun);

                // Cool fill / rim light on opposite side for silhouette depth
                const rimLight = new THREE.DirectionalLight(0x93c5fd, 0.45);
                rimLight.position.set(-140, 90, -140);
                this.scene.add(rimLight);
            }

            setupGround() {
                const gridHelper = new THREE.GridHelper(260, 52, 0x475569, 0x94a3b8);
                gridHelper.position.y = -0.05;
                gridHelper.material.opacity = 0.7;
                gridHelper.material.transparent = true;
                this.scene.add(gridHelper);

                const groundGeo = new THREE.PlaneGeometry(360, 360);
                const groundMat = new THREE.MeshStandardMaterial({
                    color: 0xb4c2d0, roughness: 0.9, metalness: 0.08
                });
                const ground = new THREE.Mesh(groundGeo, groundMat);
                ground.rotation.x = -Math.PI / 2;
                ground.position.y = -0.1;
                ground.receiveShadow = true;
                this.scene.add(ground);
            }

            setupFallbackControls() {
                let isDragging = false, isPanning = false;
                let prevMouse = { x: 0, y: 0 };
                let spherical = { radius: 80, theta: 0.85, phi: 1.15 };

                const updateCam = () => {
                    spherical.phi = Math.max(0.08, Math.min(Math.PI - 0.08, spherical.phi));
                    this.camera.position.x = this.controls.target.x + spherical.radius * Math.sin(spherical.phi) * Math.sin(spherical.theta);
                    this.camera.position.y = this.controls.target.y + spherical.radius * Math.cos(spherical.phi);
                    this.camera.position.z = this.controls.target.z + spherical.radius * Math.sin(spherical.phi) * Math.cos(spherical.theta);
                    this.camera.lookAt(this.controls.target);
                };

                this.renderer.domElement.addEventListener('contextmenu', e => e.preventDefault());
                this.renderer.domElement.addEventListener('mousedown', (e) => {
                    if (e.button === 0) isDragging = true;
                    if (e.button === 2) isPanning = true;
                    prevMouse = { x: e.clientX, y: e.clientY };
                });
                window.addEventListener('mouseup', () => { isDragging = false; isPanning = false; });
                this.renderer.domElement.addEventListener('mousemove', (e) => {
                    const dx = e.clientX - prevMouse.x;
                    const dy = e.clientY - prevMouse.y;
                    if (isDragging) {
                        spherical.theta -= dx * 0.008;
                        spherical.phi -= dy * 0.008;
                        updateCam();
                    } else if (isPanning) {
                        this.controls.target.x -= dx * 0.12;
                        this.controls.target.y += dy * 0.12;
                        updateCam();
                    }
                    prevMouse = { x: e.clientX, y: e.clientY };
                });
                this.renderer.domElement.addEventListener('wheel', (e) => {
                    spherical.radius = Math.max(8, Math.min(800, spherical.radius + e.deltaY * 0.25));
                    updateCam();
                });
                updateCam();
            }

            onResize() {
                if (!this.container || !this.renderer || !this.camera) return;
                const w = this.container.clientWidth;
                const h = this.container.clientHeight;
                this.camera.aspect = w / h;
                this.camera.updateProjectionMatrix();
                this.renderer.setSize(w, h);
            }

            clearBuilding() {
                if (this.buildingGroup) {
                    this.scene.remove(this.buildingGroup);
                    this.buildingGroup = null;
                }
                if (this.contextGroup) {
                    this.scene.remove(this.contextGroup);
                    this.contextGroup = null;
                }
                this.floorGroups = [];
                this.flatMeshes = [];
                this.allInteractiveMeshes = [];
                this.selectedFlatId = null;
                this.selectedFloorIndex = null;
                this.explodeRatio = 0.0;
                this.targetExplodeRatio = 0.0;
                const pinEl = document.getElementById('unit-3d-pin');
                if (pinEl) pinEl.style.display = 'none';
            }

            loadBuilding(buildingFeature, cadastre) {
                this.clearBuilding();
                this.buildingData = buildingFeature;
                this.cadastreData = cadastre;

                const p = (buildingFeature && buildingFeature.properties) ? buildingFeature.properties : {};
                const geom = (buildingFeature && buildingFeature.geometry && buildingFeature.geometry.coordinates) 
                    ? buildingFeature.geometry 
                    : (cadastre && cadastre.geometry ? cadastre.geometry : null);

                if (!geom) {
                    console.error("loadBuilding: No valid geometry found for building", buildingFeature, cadastre);
                    return;
                }

                let ring = [];
                if (geom.type === 'Polygon' && geom.coordinates && geom.coordinates[0]) {
                    ring = geom.coordinates[0];
                } else if (geom.type === 'MultiPolygon' && geom.coordinates && geom.coordinates[0] && geom.coordinates[0][0]) {
                    ring = geom.coordinates[0][0];
                }
                if (!ring || ring.length < 3) {
                    console.error("loadBuilding: Polygon ring has less than 3 points", ring);
                    return;
                }

                let avgLon = 0, avgLat = 0;
                ring.forEach(pt => { avgLon += pt[0]; avgLat += pt[1]; });
                avgLon /= ring.length;
                avgLat /= ring.length;

                const SCALE_M = 111320;
                const cosLat = Math.cos(avgLat * Math.PI / 180);

                const shapePoints = ring.map(pt => new THREE.Vector2(
                    (pt[0] - avgLon) * SCALE_M * cosLat,
                    -(pt[1] - avgLat) * SCALE_M
                ));

                const shape = new THREE.Shape(shapePoints);
                const box2 = new THREE.Box2().setFromPoints(shapePoints);
                const size = new THREE.Vector2();
                box2.getSize(size);
                const center = new THREE.Vector2();
                box2.getCenter(center);

                const centeredPoints = shapePoints.map(pt => new THREE.Vector2(pt.x - center.x, pt.y - center.y));
                const centeredShape = new THREE.Shape(centeredPoints);

                this.buildingGroup = new THREE.Group();
                this.scene.add(this.buildingGroup);

                const floors = cadastre.floors_count || p.floors || 5;
                const floorHeight = cadastre.floor_height_m || (p.height_m / floors);
                const maxDim = Math.max(size.x, size.y, p.height_m || 50);

                // 1. Build Central High-Detail BIM Building
                this.buildArchitecturalFloors(centeredShape, centeredPoints, cadastre, floorHeight, size);
                this.buildGroundEntrance(size, floorHeight);
                this.buildRooftopCrown(centeredShape, floors * floorHeight, size);

                // 2. Reset Camera to Isolated Building
                this.resetCameraToFraming(maxDim, p.height_m || 50);
            }

            buildContextualSurroundings() {
                // Strictly isolated single building mode - no surrounding massing
                if (this.contextGroup) {
                    this.scene.remove(this.contextGroup);
                    this.contextGroup = null;
                }
            }

            buildArchitecturalFloors(centeredShape, points, cadastre, floorHeight, bboxSize) {
                const floors = cadastre.floors;

                floors.forEach((floorObj, flIdx) => {
                    const floorGroup = new THREE.Group();
                    floorGroup.position.y = flIdx * floorHeight;
                    floorGroup.userData = {
                        floorIndex: flIdx,
                        baseY: flIdx * floorHeight,
                        floorData: floorObj
                    };

                    const slabThickness = 0.36;
                    const slabGeom = new THREE.ExtrudeGeometry(centeredShape, {
                        depth: slabThickness,
                        bevelEnabled: true,
                        bevelSegments: 2,
                        steps: 1,
                        bevelSize: 0.16,
                        bevelThickness: 0.12
                    });
                    slabGeom.rotateX(-Math.PI / 2);

                    const slabMesh = new THREE.Mesh(slabGeom, this.materials.slabConcrete);
                    slabMesh.castShadow = true;
                    slabMesh.receiveShadow = true;
                    floorGroup.add(slabMesh);

                    const slabEdgeGeom = new THREE.EdgesGeometry(slabGeom, 35);
                    const slabEdge = new THREE.LineSegments(slabEdgeGeom, new THREE.LineBasicMaterial({
                        color: 0x334155, transparent: true, opacity: 0.75
                    }));
                    floorGroup.add(slabEdge);

                    const units = floorObj.units || [];
                    const hWall = floorHeight - slabThickness;

                    units.forEach((unit, uIdx) => {
                        const flatGroup = new THREE.Group();
                        flatGroup.position.y = slabThickness;
                        flatGroup.userData = {
                            isFlat: true,
                            unitId: unit.unit_id,
                            unitData: unit,
                            floorIndex: flIdx,
                            wingId: unit.wing_id
                        };

                        const flatShape = this.createQuadrantShape(centeredShape, points, unit.quadrant, bboxSize);

                        const flatPlateGeom = new THREE.ExtrudeGeometry(flatShape, { depth: 0.08, bevelEnabled: false });
                        flatPlateGeom.rotateX(-Math.PI / 2);
                        const flatPlateMesh = new THREE.Mesh(flatPlateGeom, this.materials.exteriorAccent.clone());
                        flatPlateMesh.position.y = 0.02;
                        flatPlateMesh.userData = { isFlatClickable: true, unitId: unit.unit_id, unitData: unit };
                        flatGroup.add(flatPlateMesh);

                        // Architectural Glazed Curtain Wall Facade (Primary visible envelope)
                        const wallGeom = new THREE.ExtrudeGeometry(flatShape, { depth: hWall, bevelEnabled: false });
                        wallGeom.rotateX(-Math.PI / 2);
                        const initialGlassMat = (uIdx % 2 === 0 ? this.materials.windowGlass : this.materials.windowGlassWarm).clone();
                        const wallMesh = new THREE.Mesh(wallGeom, initialGlassMat);
                        wallMesh.castShadow = true;
                        wallMesh.receiveShadow = true;
                        wallMesh.userData = { isFlatClickable: true, unitId: unit.unit_id, unitData: unit };
                        flatGroup.add(wallMesh);

                        // Window Mullions & Architectural Frame Lines
                        const flatEdgeGeom = new THREE.EdgesGeometry(wallGeom, 25);
                        const flatOutline = new THREE.LineSegments(flatEdgeGeom, new THREE.LineBasicMaterial({
                            color: 0x1e293b, transparent: true, opacity: 0.55, linewidth: 1.5
                        }));
                        flatGroup.add(flatOutline);

                        // Internal Structural Column at Quadrant Core
                        const colSize = Math.max(0.6, Math.min(bboxSize.x, bboxSize.y) * 0.045);
                        const colGeo = new THREE.BoxGeometry(colSize, hWall, colSize);
                        const colMesh = new THREE.Mesh(colGeo, this.materials.exteriorStone);
                        const colOffset = 0.85;
                        const signX = (unit.quadrant === 0 || unit.quadrant === 3 ? 1 : -1);
                        const signZ = (unit.quadrant === 0 || unit.quadrant === 1 ? 1 : -1);
                        colMesh.position.set(signX * colOffset, hWall / 2, signZ * colOffset);
                        flatGroup.add(colMesh);

                        const balconyMesh = this.createBalcony(unit.quadrant, bboxSize, hWall);
                        if (balconyMesh) {
                            balconyMesh.userData = { isFlatClickable: true, unitId: unit.unit_id, unitData: unit };
                            flatGroup.add(balconyMesh);
                        }

                        flatGroup.userData.wallMesh = wallMesh;
                        flatGroup.userData.plateMesh = flatPlateMesh;
                        flatGroup.userData.outline = flatOutline;
                        flatGroup.userData.unitData = unit;

                        this.allInteractiveMeshes.push(wallMesh, flatPlateMesh);
                        this.flatMeshes.push(flatGroup);
                        floorGroup.add(flatGroup);
                    });

                    floorGroup.userData.slabMesh = slabMesh;
                    this.floorGroups.push(floorGroup);
                    this.buildingGroup.add(floorGroup);
                });
            }

            createQuadrantShape(fullShape, points, quadIdx, size) {
                const quadShape = new THREE.Shape();
                const halfW = size.x * 0.48;
                const halfH = size.y * 0.48;

                const inQuad = (points || []).filter(pt => {
                    if (quadIdx === 0) return pt.x >= -0.2 && pt.y >= -0.2;
                    if (quadIdx === 1) return pt.x <= 0.2 && pt.y >= -0.2;
                    if (quadIdx === 2) return pt.x <= 0.2 && pt.y <= 0.2;
                    return pt.x >= -0.2 && pt.y <= 0.2;
                });

                if (inQuad.length >= 3) {
                    const coreOffset = 0.32;
                    const cx = (quadIdx === 0 || quadIdx === 3 ? 1 : -1) * coreOffset;
                    const cy = (quadIdx === 0 || quadIdx === 1 ? 1 : -1) * coreOffset;
                    quadShape.moveTo(cx, cy);

                    const sorted = [...inQuad].sort((a, b) => Math.atan2(a.y - cy, a.x - cx) - Math.atan2(b.y - cy, b.x - cx));
                    sorted.forEach(pt => quadShape.lineTo(pt.x * 0.96, pt.y * 0.96));
                    quadShape.closePath();
                    return quadShape;
                }

                let minX = -halfW, maxX = 0, minY = -halfH, maxY = 0;
                if (quadIdx === 0) { minX = 0.3; maxX = halfW; minY = 0.3; maxY = halfH; }
                else if (quadIdx === 1) { minX = -halfW; maxX = -0.3; minY = 0.3; maxY = halfH; }
                else if (quadIdx === 2) { minX = -halfW; maxX = -0.3; minY = -halfH; maxY = -0.3; }
                else if (quadIdx === 3) { minX = 0.3; maxX = halfW; minY = -halfH; maxY = -0.3; }

                quadShape.moveTo(minX, minY);
                quadShape.lineTo(maxX, minY);
                quadShape.lineTo(maxX, maxY);
                quadShape.lineTo(minX, maxY);
                quadShape.closePath();
                return quadShape;
            }

            createInsetShape(shape, inset) {
                const s = new THREE.Shape();
                const pts = shape.getPoints();
                if (pts.length < 3) return null;
                pts.forEach((pt, i) => {
                    const sx = pt.x * (1 - inset * 0.15);
                    const sy = pt.y * (1 - inset * 0.15);
                    if (i === 0) s.moveTo(sx, sy);
                    else s.lineTo(sx, sy);
                });
                s.closePath();
                return s;
            }

            createBalcony(quadIdx, bboxSize, hWall) {
                const bGroup = new THREE.Group();
                const bWidth = Math.min(bboxSize.x * 0.35, 8.0);
                const bDepth = 1.6;
                const bThick = 0.22;

                const slabGeo = new THREE.BoxGeometry(bWidth, bThick, bDepth);
                const slab = new THREE.Mesh(slabGeo, this.materials.balconyDeck);
                slab.castShadow = true;
                bGroup.add(slab);

                const railH = 1.05;
                const railGeo = new THREE.BoxGeometry(bWidth, railH, 0.05);
                const rail = new THREE.Mesh(railGeo, this.materials.balconyGlassRailing);
                rail.position.set(0, railH / 2, bDepth / 2);
                bGroup.add(rail);

                const handrailGeo = new THREE.BoxGeometry(bWidth + 0.1, 0.06, 0.08);
                const handrail = new THREE.Mesh(handrailGeo, this.materials.aluminumFrame);
                handrail.position.set(0, railH, bDepth / 2);
                bGroup.add(handrail);

                const signX = (quadIdx === 0 || quadIdx === 3) ? 1 : -1;
                const signZ = (quadIdx === 0 || quadIdx === 1) ? 1 : -1;
                bGroup.position.set(signX * (bboxSize.x * 0.38), 0.15, signZ * (bboxSize.y * 0.38));
                return bGroup;
            }

            buildGroundEntrance(bboxSize, floorHeight) {
                const entranceGroup = new THREE.Group();
                entranceGroup.position.y = 0;

                const canopyW = Math.min(bboxSize.x * 0.45, 14);
                const canopyD = 4.2;
                const canopyThick = 0.3;
                const canopyGeo = new THREE.BoxGeometry(canopyW, canopyThick, canopyD);
                const canopy = new THREE.Mesh(canopyGeo, this.materials.slabEdge);
                canopy.position.set(0, floorHeight * 0.95, bboxSize.y * 0.48 + canopyD / 2);
                entranceGroup.add(canopy);

                const edgeGeo = new THREE.EdgesGeometry(canopyGeo);
                const line = new THREE.LineSegments(edgeGeo, new THREE.LineBasicMaterial({ color: 0x38bdf8, opacity: 0.5, transparent: true }));
                line.position.copy(canopy.position);
                entranceGroup.add(line);

                [-canopyW * 0.42, canopyW * 0.42].forEach(posX => {
                    const colGeo = new THREE.CylinderGeometry(0.25, 0.25, floorHeight * 0.95, 16);
                    const col = new THREE.Mesh(colGeo, this.materials.aluminumFrame);
                    col.position.set(posX, (floorHeight * 0.95) / 2, bboxSize.y * 0.48 + canopyD * 0.85);
                    col.castShadow = true;
                    entranceGroup.add(col);
                });

                const doorGeo = new THREE.BoxGeometry(canopyW * 0.55, floorHeight * 0.75, 0.1);
                const doors = new THREE.Mesh(doorGeo, this.materials.entranceDoor);
                doors.position.set(0, (floorHeight * 0.75) / 2, bboxSize.y * 0.48);
                entranceGroup.add(doors);

                this.buildingGroup.add(entranceGroup);
            }

            buildRooftopCrown(centeredShape, totalHeight, bboxSize) {
                const crownGroup = new THREE.Group();
                crownGroup.position.y = totalHeight;

                const parapetH = 1.15;
                const parapetGeom = new THREE.ExtrudeGeometry(centeredShape, { depth: parapetH, bevelEnabled: false });
                parapetGeom.rotateX(-Math.PI / 2);
                const parapetMesh = new THREE.Mesh(parapetGeom, this.materials.roofSlate);
                crownGroup.add(parapetMesh);

                const coreW = Math.min(bboxSize.x * 0.32, 10);
                const coreD = Math.min(bboxSize.y * 0.32, 10);
                const coreH = 3.8;
                const coreGeo = new THREE.BoxGeometry(coreW, coreH, coreD);
                const core = new THREE.Mesh(coreGeo, this.materials.roofSlate);
                core.position.set(0, coreH / 2, 0);
                core.castShadow = true;
                crownGroup.add(core);

                [-coreW * 0.7, coreW * 0.7].forEach((posX, idx) => {
                    const hvacGeo = new THREE.BoxGeometry(2.4, 1.6, 2.8);
                    const hvac = new THREE.Mesh(hvacGeo, this.materials.roofHVAC);
                    hvac.position.set(posX, 0.8, -coreD * 0.5);
                    crownGroup.add(hvac);

                    const tankGeo = new THREE.CylinderGeometry(1.1, 1.1, 2.2, 16);
                    const tank = new THREE.Mesh(tankGeo, this.materials.aluminumFrame);
                    tank.position.set(posX, 1.1, coreD * 0.5);
                    crownGroup.add(tank);
                });

                const spireH = Math.min(totalHeight * 0.22, 18);
                const spireGeo = new THREE.CylinderGeometry(0.08, 0.35, spireH, 8);
                const spire = new THREE.Mesh(spireGeo, this.materials.aluminumFrame);
                spire.position.set(0, coreH + spireH / 2, 0);
                crownGroup.add(spire);

                const beaconGeo = new THREE.SphereGeometry(0.3, 12, 12);
                const beaconMat = new THREE.MeshBasicMaterial({ color: 0xff3b30 });
                const beacon = new THREE.Mesh(beaconGeo, beaconMat);
                beacon.position.set(0, coreH + spireH, 0);
                crownGroup.add(beacon);

                crownGroup.userData = { isCrown: true, baseY: totalHeight };
                this.crownGroup = crownGroup;
                this.buildingGroup.add(crownGroup);
            }

            setExplode(ratio) {
                this.targetExplodeRatio = THREE.MathUtils.clamp(ratio, 0.0, 1.0);
            }

            updateExplodeAnimation() {
                const diff = this.targetExplodeRatio - this.explodeRatio;
                if (Math.abs(diff) > 0.002) {
                    this.explodeRatio += diff * 0.12;
                    const maxGap = 8.5;

                    this.floorGroups.forEach((fg, idx) => {
                        const targetY = fg.userData.baseY + (idx * maxGap * this.explodeRatio);
                        fg.position.y = targetY;
                    });

                    if (this.crownGroup) {
                        const crownTargetY = this.crownGroup.userData.baseY + (this.floorGroups.length * maxGap * this.explodeRatio);
                        this.crownGroup.position.y = crownTargetY;
                    }
                }
            }

            selectFlat(unitId) {
                this.selectedFlatId = unitId;

                this.flatMeshes.forEach(fg => {
                    const isTarget = (fg.userData.unitId === unitId);
                    const isSameFloor = (this.selectedFloorIndex !== null && fg.userData.floorIndex === this.selectedFloorIndex);

                    if (unitId === null) {
                        fg.userData.wallMesh.material = this.materials.windowGlass;
                        fg.userData.plateMesh.material = this.materials.exteriorAccent;
                        fg.userData.outline.material.color.set(0x1e293b);
                        fg.userData.outline.material.opacity = 0.55;
                    } else if (isTarget) {
                        fg.userData.wallMesh.material = new THREE.MeshStandardMaterial({
                            color: 0x1d4ed8,
                            emissive: 0x1e40af,
                            emissiveIntensity: 0.5,
                            roughness: 0.2,
                            metalness: 0.2,
                            transparent: true,
                            opacity: 0.94
                        });
                        fg.userData.plateMesh.material = new THREE.MeshStandardMaterial({
                            color: 0x1d4ed8,
                            emissive: 0x2563a6,
                            emissiveIntensity: 0.4
                        });
                        fg.userData.outline.material.color.set(0x60a5fa);
                        fg.userData.outline.material.opacity = 1.0;
                    } else {
                        fg.userData.wallMesh.material = this.materials.windowGlass;
                        fg.userData.plateMesh.material = this.materials.exteriorAccent;
                        fg.userData.outline.material.color.set(0x1e293b);
                        fg.userData.outline.material.opacity = isSameFloor ? 0.7 : 0.4;
                    }
                });

                if (unitId) {
                    const targetFlat = this.flatMeshes.find(f => f.userData.unitId === unitId);
                    if (targetFlat) {
                        const worldPos = new THREE.Vector3();
                        targetFlat.getWorldPosition(worldPos);
                        this.tweenCameraTo(
                            new THREE.Vector3(worldPos.x + 22, worldPos.y + 16, worldPos.z + 28),
                            worldPos
                        );
                    }
                }
            }

            selectFloor(floorIndex) {
                this.selectedFloorIndex = floorIndex;
                this.selectedFlatId = null;

                this.floorGroups.forEach((fg, idx) => {
                    const isSelected = (idx === floorIndex);
                    fg.traverse(child => {
                        if (child.isMesh && child.userData.isFlatClickable) {
                            if (floorIndex === null || isSelected) {
                                child.material = this.materials.windowGlass;
                            } else {
                                child.material = this.materials.ghostedMaterial;
                            }
                        }
                    });
                });

                if (floorIndex !== null && this.floorGroups[floorIndex]) {
                    const targetFloor = this.floorGroups[floorIndex];
                    const worldPos = new THREE.Vector3();
                    targetFloor.getWorldPosition(worldPos);
                    this.tweenCameraTo(
                        new THREE.Vector3(worldPos.x + 36, worldPos.y + 24, worldPos.z + 42),
                        worldPos
                    );
                }
            }

            tweenCameraTo(targetPos, targetLook) {
                this.camTween.active = true;
                this.camTween.startPos.copy(this.camera.position);
                this.camTween.targetPos.copy(targetPos);
                this.camTween.startLook.copy(this.controls.target);
                this.camTween.targetLook.copy(targetLook);
                this.camTween.progress = 0;
            }

            updateCameraTween() {
                if (!this.camTween.active) return;
                this.camTween.progress += 1.0 / this.camTween.duration;
                const t = THREE.MathUtils.clamp(this.camTween.progress, 0.0, 1.0);
                const ease = t * t * (3.0 - 2.0 * t);

                this.camera.position.lerpVectors(this.camTween.startPos, this.camTween.targetPos, ease);
                this.controls.target.lerpVectors(this.camTween.startLook, this.camTween.targetLook, ease);

                if (t >= 1.0) {
                    this.camTween.active = false;
                }
            }

            setCameraPreset(preset) {
                if (!this.buildingGroup) return;
                const box = new THREE.Box3().setFromObject(this.buildingGroup);
                const center = box.getCenter(new THREE.Vector3());
                const size = box.getSize(new THREE.Vector3());
                const maxDim = Math.max(size.x, size.y, size.z);

                if (preset === '3d' || preset === 'iso') {
                    this.tweenCameraTo(
                        new THREE.Vector3(center.x + maxDim * 1.4, center.y + maxDim * 1.1, center.z + maxDim * 1.4),
                        center
                    );
                } else if (preset === 'elevation') {
                    this.tweenCameraTo(
                        new THREE.Vector3(center.x, center.y, center.z + maxDim * 2.2),
                        center
                    );
                } else if (preset === 'plan') {
                    this.tweenCameraTo(
                        new THREE.Vector3(center.x, center.y + maxDim * 2.5, center.z + 0.1),
                        center
                    );
                } else if (preset === 'exploded') {
                    this.setExplode(0.8);
                    this.tweenCameraTo(
                        new THREE.Vector3(center.x + maxDim * 1.5, center.y + maxDim * 1.3, center.z + maxDim * 1.5),
                        center
                    );
                }
            }

            alignNorth() {
                if (!this.camera || !this.controls) return;
                const target = this.controls.target;
                const dist = this.camera.position.distanceTo(target);
                this.tweenCameraTo(
                    new THREE.Vector3(target.x, target.y + dist * 0.52, target.z + dist * 0.85),
                    target
                );
            }

            zoom(factor) {
                if (!this.camera || !this.controls) return;
                const dir = new THREE.Vector3().subVectors(this.camera.position, this.controls.target);
                const newDist = Math.max(8, Math.min(500, dir.length() * factor));
                dir.setLength(newDist);
                this.camera.position.copy(this.controls.target).add(dir);
            }

            resetCameraToFraming(maxDim, height) {
                const targetLook = new THREE.Vector3(0, height / 2, 0);
                const targetPos = new THREE.Vector3(maxDim * 1.6, height * 0.9 + maxDim * 0.8, maxDim * 1.6);
                this.camera.position.copy(targetPos);
                this.controls.target.copy(targetLook);
                this.camera.lookAt(targetLook);
            }

            onMouseMove(event) {
                const rect = this.renderer.domElement.getBoundingClientRect();
                this.mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
                this.mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

                this.raycaster.setFromCamera(this.mouse, this.camera);
                const intersects = this.raycaster.intersectObjects(this.allInteractiveMeshes, false);

                const tooltip = document.getElementById('viewport-tooltip');
                if (intersects.length > 0) {
                    const top = intersects[0];
                    const uData = top.object.userData.unitData;
                    if (uData) {
                        tooltip.style.display = 'block';
                        tooltip.style.left = `${event.clientX}px`;
                        tooltip.style.top = `${event.clientY}px`;
                        document.getElementById('tt-title').innerText = `Flat ${uData.unit_number} (${uData.wing_id})`;
                        document.getElementById('tt-sub').innerText = `${uData.unit_type} • ${uData.carpet_area_sqm} m² (${uData.carpet_area_sqft} sq.ft)`;
                        document.getElementById('tt-ulpin').innerText = `ULPIN: ${uData.unit_ulpin}`;
                        this.renderer.domElement.style.cursor = 'pointer';
                        return;
                    }
                }
                tooltip.style.display = 'none';
                this.renderer.domElement.style.cursor = 'default';
            }

            onClick(event) {
                this.raycaster.setFromCamera(this.mouse, this.camera);
                const intersects = this.raycaster.intersectObjects(this.allInteractiveMeshes, false);
                if (intersects.length > 0) {
                    const uData = intersects[0].object.userData.unitData;
                    if (uData && window.appBridge.selectFlat) {
                        window.appBridge.selectFlat(uData);
                    }
                }
            }

            updatePinPosition() {
                const pinEl = document.getElementById('unit-3d-pin');
                if (!pinEl) return;
                if (!this.selectedFlatId) {
                    pinEl.style.display = 'none';
                    return;
                }
                const targetFlat = this.flatMeshes.find(f => f.userData.unitId === this.selectedFlatId);
                if (!targetFlat) {
                    pinEl.style.display = 'none';
                    return;
                }
                const worldPos = new THREE.Vector3();
                targetFlat.getWorldPosition(worldPos);
                worldPos.y += 2.0;
                const projected = worldPos.clone().project(this.camera);
                if (projected.z < 1.0) {
                    const w = this.container.clientWidth;
                    const h = this.container.clientHeight;
                    const screenX = (projected.x * 0.5 + 0.5) * w;
                    const screenY = (-(projected.y * 0.5) + 0.5) * h;
                    pinEl.style.display = 'block';
                    pinEl.style.left = `${screenX}px`;
                    pinEl.style.top = `${screenY}px`;
                    const labelEl = document.getElementById('unit-3d-pin-label');
                    if (labelEl && targetFlat.userData.unitData) {
                        labelEl.textContent = `Flat ${targetFlat.userData.unitData.unit_number}`;
                    }
                } else {
                    pinEl.style.display = 'none';
                }
            }

            animate() {
                this.animId = requestAnimationFrame(this.animate);
                if (this.controls && this.controls.update) this.controls.update();
                this.updateExplodeAnimation();
                this.updateCameraTween();
                this.updatePinPosition();
                this.renderer.render(this.scene, this.camera);
            }
        }

        // Professional Engineering Inline SVG Icons
        const IconEmblem = () => (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2L3 7v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V7l-9-5z"/>
                <path d="M12 7v8"/>
                <path d="M8 11h8"/>
            </svg>
        );

        const IconIsometric = () => (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="m21 16-9 5-9-5V8l9-5 9 5v8Z"/>
                <path d="m3 8 9 5 9-5"/>
                <path d="M12 13v8"/>
            </svg>
        );

        const IconElevation = () => (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="4" y="4" width="16" height="16" rx="2"/>
                <path d="M4 10h16"/>
                <path d="M4 16h16"/>
                <path d="M10 4v16"/>
            </svg>
        );

        const IconTopPlan = () => (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="3" width="18" height="18" rx="2"/>
                <path d="M3 9h18"/>
                <path d="M9 21V9"/>
            </svg>
        );

        const IconBuilding = () => (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="4" y="2" width="16" height="20" rx="2"/>
                <path d="M9 22v-4h6v4"/>
                <path d="M8 6h.01M16 6h.01M8 10h.01M16 10h.01M8 14h.01M16 14h.01"/>
            </svg>
        );

        const IconOrbit = () => (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="9"/>
                <path d="m16 8-4-4-4 4"/>
                <path d="M12 4v7"/>
                <path d="m8 16 4 4 4-4"/>
                <path d="M12 20v-7"/>
            </svg>
        );

        const IconUnderground = () => (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 8h18"/>
                <path d="M4 14h16"/>
                <path d="M6 20h12"/>
                <circle cx="8" cy="14" r="2" fill="currentColor"/>
                <circle cx="16" cy="14" r="2" fill="currentColor"/>
            </svg>
        );

        const IconExplode = () => (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="m12 2 10 5-10 5-10-5 10-5Z"/>
                <path d="m2 12 10 5 10-5"/>
                <path d="m2 17 10 5 10-5"/>
            </svg>
        );

        const IconCopy = () => (
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
            </svg>
        );

        const IconCheck = () => (
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#10b981" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="20 6 9 17 4 12"/>
            </svg>
        );

        const IconSearch = () => (
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="11" cy="11" r="8"/>
                <path d="m21 21-4.35-4.35"/>
            </svg>
        );

        const IconLogoStack = () => (
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#ffffff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="12 2 2 7 12 12 22 7 12 2" fill="rgba(255, 255, 255, 0.2)" />
                <polyline points="2 17 12 22 22 17" />
                <polyline points="2 12 12 17 22 12" />
            </svg>
        );

        const IconMap = ({ size = 14 }) => (
            <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6"/>
                <line x1="8" y1="2" x2="8" y2="18"/>
                <line x1="16" y1="6" x2="16" y2="22"/>
            </svg>
        );

        const IconProperty = ({ size = 14 }) => (
            <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="4" y="2" width="16" height="20" rx="2"/>
                <path d="M9 22v-4h6v4"/>
                <path d="M8 6h.01M16 6h.01M8 10h.01M16 10h.01M8 14h.01M16 14h.01"/>
            </svg>
        );

        const IconLayers = ({ size = 14 }) => (
            <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="12 2 2 7 12 12 22 7 12 2"/>
                <polyline points="2 17 12 22 22 17"/>
                <polyline points="2 12 12 17 22 12"/>
            </svg>
        );

        const IconTools = ({ size = 14 }) => (
            <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
            </svg>
        );

        const IconReports = ({ size = 14 }) => (
            <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
                <line x1="16" y1="13" x2="8" y2="13"/>
                <line x1="16" y1="17" x2="8" y2="17"/>
            </svg>
        );

        const IconBack = ({ size = 13 }) => (
            <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="19" y1="12" x2="5" y2="12"/>
                <polyline points="12 19 5 12 12 5"/>
            </svg>
        );

        const IconFolder = ({ size = 13, color = "currentColor" }) => (
            <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
            </svg>
        );

        const IconFolderOpen = ({ size = 13, color = "#2563eb" }) => (
            <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M6 14l1.45-6.53A2 2 0 0 1 9.4 6H20a2 2 0 0 1 2 2v2"/>
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
            </svg>
        );

        const IconChevronRight = ({ size = 10 }) => (
            <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="9 18 15 12 9 6"/>
            </svg>
        );

        const IconChevronDown = ({ size = 10 }) => (
            <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="6 9 12 15 18 9"/>
            </svg>
        );

        const IconUnit = ({ size = 12, color = "currentColor" }) => (
            <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="3" width="18" height="18" rx="2" />
                <path d="M9 3v18" />
            </svg>
        );

        const IconSelect = ({ size = 14 }) => (
            <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="m3 3 7.07 16.97 2.51-7.39 7.39-2.51L3 3z"/>
                <path d="m13 13 6 6"/>
            </svg>
        );

        const IconMeasure = ({ size = 14 }) => (
            <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21.3 8.7 8.7 21.3c-1 1-2.6 1-3.6 0l-2.4-2.4c-1-1-1-2.6 0-3.6L15.3 2.7c1-1 2.6-1 3.6 0l2.4 2.4c1 1 1 2.6 0 3.6z"/>
                <path d="m7.5 10.5 2 2"/>
                <path d="m10.5 7.5 2 2"/>
                <path d="m13.5 4.5 2 2"/>
            </svg>
        );

        const IconSection = ({ size = 14 }) => (
            <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="3" width="18" height="18" rx="2"/>
                <line x1="3" y1="12" x2="21" y2="12" strokeDasharray="3 3"/>
            </svg>
        );

        const IconReset = ({ size = 14 }) => (
            <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/>
            </svg>
        );

        const IconCompassRose = ({ size = 16 }) => (
            <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <polygon points="12 2 15 12 12 10" fill="#ef4444" stroke="#ef4444"/>
                <polygon points="12 2 9 12 12 10" fill="#dc2626" stroke="#dc2626"/>
                <polygon points="12 22 15 12 12 14" fill="#94a3b8" stroke="#94a3b8"/>
                <polygon points="12 22 9 12 12 14" fill="#cbd5e1" stroke="#cbd5e1"/>
            </svg>
        );

        const IconPerspective = ({ size = 14 }) => (
            <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="m2 9 10-5 10 5-10 5L2 9Z"/>
                <path d="m2 9v6l10 5 10-5V9"/>
            </svg>
        );

        const IconWater = ({ size = 12, color = "#0ea5e9" }) => (
            <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z"/>
            </svg>
        );

        const IconSewer = ({ size = 12, color = "#10b981" }) => (
            <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M4 14h6v6h4v-6h6V10h-6V4h-4v6H4z"/>
            </svg>
        );

        const IconPower = ({ size = 12, color = "#f59e0b" }) => (
            <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" fill={color} fillOpacity="0.3"/>
            </svg>
        );

        const IconRain = ({ size = 12, color = "#6366f1" }) => (
            <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M20 16.2A4.5 4.5 0 0 0 17.5 8h-1.8A7 7 0 1 0 4 14.9"/>
                <path d="M8 19v2M12 19v2M16 19v2"/>
            </svg>
        );

        const IconDownload = ({ size = 13, color = "currentColor" }) => (
            <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                <polyline points="7 10 12 15 17 10"/>
                <line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
        );

        const IconDoc = ({ size = 13, color = "currentColor" }) => (
            <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
                <line x1="16" y1="13" x2="8" y2="13"/>
                <line x1="16" y1="17" x2="8" y2="17"/>
            </svg>
        );

        const IconMore = ({ size = 14 }) => (
            <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="1.5"/>
                <circle cx="19" cy="12" r="1.5"/>
                <circle cx="5" cy="12" r="1.5"/>
            </svg>
        );

        const IconThumbnail = () => (
            <svg width="48" height="48" viewBox="0 0 60 60" fill="none">
                <rect width="60" height="60" fill="#0f172a" />
                <rect x="8" y="14" width="20" height="42" fill="#1e293b" stroke="#334155" strokeWidth="1" />
                <rect x="24" y="8" width="28" height="48" fill="#1e293b" stroke="#475569" strokeWidth="1" />
                <rect x="28" y="12" width="20" height="12" fill="#38bdf8" fillOpacity="0.4" stroke="#38bdf8" strokeWidth="1" />
                <line x1="24" y1="26" x2="52" y2="26" stroke="#ffffff" strokeWidth="1.5" />
                <line x1="24" y1="34" x2="52" y2="34" stroke="#ffffff" strokeWidth="1.5" />
                <line x1="24" y1="42" x2="52" y2="42" stroke="#ffffff" strokeWidth="1.5" />
                <line x1="8" y1="24" x2="28" y2="24" stroke="#ffffff" strokeWidth="1.2" />
                <line x1="8" y1="34" x2="28" y2="34" stroke="#ffffff" strokeWidth="1.2" />
                <line x1="8" y1="44" x2="28" y2="44" stroke="#ffffff" strokeWidth="1.2" />
            </svg>
        );

        function App() {
            const [viewMode, setViewMode] = useState('map');
            const [buildingsData, setBuildingsData] = useState(null);
            const [selectedBuilding, setSelectedBuilding] = useState(null);
            const [cadastre, setCadastre] = useState(null);
            const [selectedWing, setSelectedWing] = useState('all');
            const [selectedFloor, setSelectedFloor] = useState(null);
            const [selectedFlat, setSelectedFlat] = useState(null);
            const [explodeRatio, setExplodeRatio] = useState(0);
            const [copiedCode, setCopiedCode] = useState(false);
            const [searchQuery, setSearchQuery] = useState('');
            const [searchResults, setSearchResults] = useState([]);
            const [twinPreset, setTwinPreset] = useState('iso');
            const [showStoreys, setShowStoreys] = useState(true);
            const [isOrbiting, setIsOrbiting] = useState(false);
            const [undergroundMode, setUndergroundMode] = useState(false);
            const [utilitiesData, setUtilitiesData] = useState(null);
            const [selectedUtility, setSelectedUtility] = useState(null);
            const [activeUtilityCat, setActiveUtilityCat] = useState('all');
            const [showLaterals, setShowLaterals] = useState(true);
            const [showManholes, setShowManholes] = useState(true);
            const [undergroundOrbitMode, setUndergroundOrbitMode] = useState(true);
            const [currentBearing, setCurrentBearing] = useState(-24);
            const [currentPitch, setCurrentPitch] = useState(58);

            // Digital Twin Workstation state matching reference mockup
            const [activeTab, setActiveTab] = useState('overview');
            const [expandedFloors, setExpandedFloors] = useState({ 4: true });
            const [activeTool, setActiveTool] = useState('select');
            const [twinViewMode, setTwinViewMode] = useState('3d');

            // Page 1: Map Explorer & GIS Layers State
            const [gisLayers, setGisLayers] = useState({
                parcels: true,
                buildings: true,
                roads: true,
                metro: true,
                utilities: false,
                drainage: true,
                coastalRoad: true,
                satellite: true,
                terrainDem: true
            });
            const [activeMapTool, setActiveMapTool] = useState('select');
            const [mapViewAngle, setMapViewAngle] = useState('iso');
            const [baseMapType, setBaseMapType] = useState('satellite');
            const [propertyTab, setPropertyTab] = useState('overview');

            const twinRef = useRef(null);
            const undergroundModeRef = useRef(false);
            const undergroundOrbitModeRef = useRef(true);

            useEffect(() => {
                undergroundModeRef.current = undergroundMode;
            }, [undergroundMode]);

            useEffect(() => {
                undergroundOrbitModeRef.current = undergroundOrbitMode;
            }, [undergroundOrbitMode]);

            useEffect(() => {
                const ts = Date.now();
                Promise.all([
                    fetch(`/api/buildings?t=${ts}`).then(r => r.json()),
                    fetch(`/api/buildings/architectural?t=${ts}`).then(r => r.json()),
                    fetch(`/api/utilities?t=${ts}`).then(r => r.json())
                ]).then(([bldData, archData, utilData]) => {
                    window.buildingsData = bldData;
                    setBuildingsData(bldData);
                    setUtilitiesData(utilData);
                    initMapLibre(bldData, archData, utilData);
                }).catch(err => console.error("Buildings & 3D data fetch error:", err));
            }, []);

            useEffect(() => {
                if (!twinRef.current) {
                    twinRef.current = new ArchitecturalDigitalTwinRenderer('twin-canvas-container');
                }
            }, []);

            useEffect(() => {
                window.appBridge.openDigitalTwin = (bldFeat) => {
                    handleOpenTwin(bldFeat);
                };
                window.appBridge.selectFlat = (unitData) => {
                    setSelectedFlat(unitData);
                    setSelectedFloor(unitData.floor_index);
                    setExpandedFloors(prev => ({ ...prev, [unitData.floor_index]: true }));
                    if (twinRef.current) twinRef.current.selectFlat(unitData.unit_id);
                };
            }, []);

            const handleOpenTwin = async (bldFeat) => {
                setSelectedBuilding(bldFeat);
                if (!bldFeat || !bldFeat.properties) {
                    console.error("handleOpenTwin called with invalid building feature:", bldFeat);
                    return;
                }
                const spId = bldFeat.properties.spatial_id;

                let master = null;
                if (buildingsData && buildingsData.features) {
                    master = buildingsData.features.find(b => b.properties && b.properties.spatial_id === spId);
                }
                if (!master) {
                    master = bldFeat;
                }

                setSelectedBuilding(master);
                setSelectedFloor(null);
                setSelectedFlat(null);
                setExplodeRatio(0);
                setActiveTab('overview');
                setTwinViewMode('3d');
                setViewMode('twin');

                const workspaceEl = document.getElementById('twin-workspace');
                if (workspaceEl) workspaceEl.style.display = 'flex';

                try {
                    const res = await fetch(`/api/building/${spId}/cadastre`);
                    if (!res.ok) throw new Error(`Cadastre API returned status ${res.status}`);
                    const cad = await res.json();
                    setCadastre(cad);

                    // Pick default expanded floor & flat matching reference layout (e.g. Floor 5, Flat 504)
                    let defFlIdx = 0;
                    let defFlat = null;
                    if (cad.floors && cad.floors.length > 0) {
                        defFlIdx = Math.min(4, cad.floors.length - 1);
                        const fl = cad.floors[defFlIdx];
                        if (fl && fl.units && fl.units.length > 0) {
                            defFlat = fl.units.find(u => u.unit_number === 504 || u.unit_number === '504') || fl.units[fl.units.length - 1];
                        }
                    }
                    setExpandedFloors({ [defFlIdx]: true });
                    if (defFlat) {
                        setSelectedFloor(defFlIdx);
                        setSelectedFlat(defFlat);
                    }

                    if (!twinRef.current) {
                        twinRef.current = new ArchitecturalDigitalTwinRenderer('twin-canvas-container');
                    }
                    setTimeout(() => {
                        if (twinRef.current) {
                            twinRef.current.onResize();
                            twinRef.current.loadBuilding(master, cad);
                            if (defFlat) {
                                twinRef.current.selectFlat(defFlat.unit_id);
                            }
                        }
                    }, 60);
                } catch (err) {
                    console.error("Cadastre fetch failed for", spId, err);
                }
            };

            const handleCloseTwin = () => {
                setViewMode('map');
                const workspaceEl = document.getElementById('twin-workspace');
                if (workspaceEl) workspaceEl.style.display = 'none';
                const pinEl = document.getElementById('unit-3d-pin');
                if (pinEl) pinEl.style.display = 'none';
                if (twinRef.current) {
                    twinRef.current.clearBuilding();
                }
            };

            const toggleFloorExpanded = (flIdx, e) => {
                if (e) e.stopPropagation();
                setExpandedFloors(prev => ({ ...prev, [flIdx]: !prev[flIdx] }));
            };

            const handleTreeFloorClick = (flIdx) => {
                setSelectedFloor(flIdx);
                setSelectedFlat(null);
                setExpandedFloors(prev => ({ ...prev, [flIdx]: true }));
                if (twinRef.current) twinRef.current.selectFloor(flIdx);
            };

            const handleTreeFlatClick = (unit) => {
                setSelectedFlat(unit);
                setSelectedFloor(unit.floor_index);
                setExpandedFloors(prev => ({ ...prev, [unit.floor_index]: true }));
                if (twinRef.current) twinRef.current.selectFlat(unit.unit_id);
            };


            const handleExplodeChange = (val) => {
                const num = parseFloat(val);
                setExplodeRatio(num);
                if (twinRef.current) twinRef.current.setExplode(num);
            };

            const handleFloorClick = (flIdx) => {
                if (selectedFloor === flIdx) {
                    setSelectedFloor(null);
                    if (twinRef.current) twinRef.current.selectFloor(null);
                } else {
                    setSelectedFloor(flIdx);
                    setSelectedFlat(null);
                    if (twinRef.current) twinRef.current.selectFloor(flIdx);
                }
            };

            const handleFlatClick = (unit) => {
                setSelectedFlat(unit);
                setSelectedFloor(unit.floor_index);
                if (twinRef.current) twinRef.current.selectFlat(unit.unit_id);
            };

            const handleCameraPreset = (preset) => {
                setTwinPreset(preset);
                if (twinRef.current) twinRef.current.setCameraPreset(preset);
            };

            const toggleStoreys = () => {
                const next = !showStoreys;
                setShowStoreys(next);
                if (window.mapInstance) {
                    const vis = next ? 'visible' : 'none';
                    ['buildings-3d-slabs', 'buildings-3d-glass', 'buildings-3d-roofs'].forEach(id => {
                        if (window.mapInstance.getLayer(id)) window.mapInstance.setLayoutProperty(id, 'visibility', vis);
                    });
                }
            };

            const toggleOrbit = () => {
                if (isOrbiting) {
                    setIsOrbiting(false);
                    if (window.orbitRaf) cancelAnimationFrame(window.orbitRaf);
                } else {
                    setIsOrbiting(true);
                    const rotate = () => {
                        if (!window.mapInstance) return;
                        const b = window.mapInstance.getBearing();
                        window.mapInstance.setBearing((b + 0.12) % 360);
                        window.orbitRaf = requestAnimationFrame(rotate);
                    };
                    window.orbitRaf = requestAnimationFrame(rotate);
                }
            };

            const handleToggleUnderground = () => {
                const nextMode = !undergroundMode;
                setUndergroundMode(nextMode);
                setSelectedUtility(null);
                const m = window.mapInstance;
                if (!m) return;

                const satOpacity = nextMode ? 0.0 : 0.92; // 0.0 exposes dark GIS street bed
                const bldOpacity = nextMode ? 0.88 : 1.0; // Crisp solid white/grey architectural massing matching reference BIM image
                const utilVis = nextMode ? 'visible' : 'none';

                // 1. Expose dark slate GIS ground & street bed
                if (m.getLayer('satellite-base')) {
                    m.setPaintProperty('satellite-base', 'raster-opacity', satOpacity);
                }
                const mapDiv = document.getElementById('map');
                if (mapDiv) {
                    mapDiv.style.backgroundColor = nextMode ? '#0b1120' : '#020816';
                }

                // 2. Translucent ghost architectural buildings in underground mode, solid in normal mode
                if (m.getLayer('buildings-3d-base-rim')) {
                    m.setPaintProperty('buildings-3d-base-rim', 'fill-extrusion-opacity', nextMode ? 0.08 : 1.0);
                }
                if (m.getLayer('buildings-3d-glass')) {
                    m.setPaintProperty('buildings-3d-glass', 'fill-extrusion-opacity', nextMode ? 0.05 : 1.0);
                }
                if (m.getLayer('buildings-3d-slabs')) {
                    m.setPaintProperty('buildings-3d-slabs', 'fill-extrusion-opacity', nextMode ? 0.12 : 1.0);
                }
                if (m.getLayer('buildings-3d-roofs')) {
                    m.setPaintProperty('buildings-3d-roofs', 'fill-extrusion-opacity', nextMode ? 0.10 : 1.0);
                }

                // 3. Subsurface infrastructure layers (Crisp vector conduits, specular lines, junction nodes)
                const allSubsurfaceLayers = [
                    'utilities-click-hitbox',
                    'utilities-trench-shadow',
                    'utilities-pipe-casing',
                    'utilities-trunks-core',
                    'utilities-specular-ridge',
                    'utilities-flow-pulse',
                    'utilities-station-boxes',
                    'utilities-station-boxes-outline',
                    'utilities-coastal-inner',
                    'utilities-coastal-lighting',
                    'utilities-metro-rails',
                    'utilities-pedestrian-stripes',
                    'utilities-laterals',
                    'utilities-manholes-base',
                    'utilities-manholes'
                ];
                allSubsurfaceLayers.forEach(id => {
                    if (m.getLayer(id)) {
                        m.setLayoutProperty(id, 'visibility', utilVis);
                    }
                });
                if (!nextMode && window.utilityPopup) {
                    window.utilityPopup.remove();
                }

                // 4. Ground street parcel boundary lines (faint in underground mode)
                if (m.getLayer('buildings-ground-line')) {
                    m.setPaintProperty('buildings-ground-line', 'line-opacity', nextMode ? 0.12 : 0.70);
                    m.setPaintProperty('buildings-ground-line', 'line-color', nextMode ? '#334155' : [
                        'case',
                        ['==', ['get', 'spatial_id'], 'MUM-BLD-E35A525A'], '#f59e0b',
                        ['==', ['get', 'spatial_id'], 'MUM-BLD-211FC714'], '#f59e0b',
                        ['!=', ['get', 'name'], ''], '#38bdf8',
                        '#64748b'
                    ]);
                }

                // 5. Oblique architectural 3D perspective matching reference BIM digital twin
                // 5. Oblique architectural 3D perspective with full 360-degree rotation freedom
                if (nextMode) {
                    applyUtilityFilters(activeUtilityCat, showLaterals, showManholes);
                    m.easeTo({
                        pitch: 58,
                        bearing: -24,
                        zoom: 16.45,
                        duration: 1200
                    });
                } else {
                    if (m.getLayer('utilities-highlight')) {
                        m.setFilter('utilities-highlight', ['==', 'utility_id', '']);
                    }
                    m.easeTo({
                        pitch: 62,
                        bearing: -22,
                        zoom: 16.55,
                        duration: 1000
                    });
                }
            };

            const handleToggleGisLayer = (layerKey) => {
                setGisLayers(prev => {
                    const nextVal = !prev[layerKey];
                    const next = { ...prev, [layerKey]: nextVal };
                    const m = window.mapInstance;
                    if (m) {
                        if (layerKey === 'parcels' && m.getLayer('buildings-ground-line')) {
                            m.setLayoutProperty('buildings-ground-line', 'visibility', nextVal ? 'visible' : 'none');
                        } else if (layerKey === 'buildings') {
                            const vis = nextVal ? 'visible' : 'none';
                            ['buildings-3d-slabs', 'buildings-3d-glass', 'buildings-3d-roofs', 'buildings-3d-base-rim'].forEach(id => {
                                if (m.getLayer(id)) m.setLayoutProperty(id, 'visibility', vis);
                            });
                        } else if (layerKey === 'utilities') {
                            handleToggleUnderground();
                        } else if (layerKey === 'satellite' && m.getLayer('satellite-base')) {
                            m.setLayoutProperty('satellite-base', 'visibility', nextVal ? 'visible' : 'none');
                        } else if (layerKey === 'metro') {
                            const vis = nextVal ? 'visible' : 'none';
                            ['utilities-station-boxes', 'utilities-station-boxes-outline', 'utilities-metro-rails'].forEach(id => {
                                if (m.getLayer(id)) m.setLayoutProperty(id, 'visibility', vis);
                            });
                        } else if (layerKey === 'coastalRoad') {
                            const vis = nextVal ? 'visible' : 'none';
                            ['utilities-coastal-inner', 'utilities-coastal-lighting'].forEach(id => {
                                if (m.getLayer(id)) m.setLayoutProperty(id, 'visibility', vis);
                            });
                        }
                    }
                    return next;
                });
            };

            const handleSetMapAngle = (angle) => {
                setMapViewAngle(angle);
                const m = window.mapInstance;
                if (!m) return;
                if (angle === 'iso') {
                    m.easeTo({ pitch: 58, bearing: -24, duration: 800 });
                } else if (angle === 'top') {
                    m.easeTo({ pitch: 0, bearing: 0, duration: 800 });
                } else if (angle === 'front') {
                    m.easeTo({ pitch: 75, bearing: 0, duration: 800 });
                } else if (angle === 'side') {
                    m.easeTo({ pitch: 75, bearing: 90, duration: 800 });
                } else if (angle === 'section') {
                    m.easeTo({ pitch: 65, bearing: -45, duration: 800 });
                }
            };

            const handleResetMapView = () => {
                const m = window.mapInstance;
                if (!m) return;
                m.flyTo({ center: [72.8270, 18.9276], zoom: 16.55, pitch: 62, bearing: -22, duration: 1000 });
                setMapViewAngle('iso');
            };

            const handleToggleBaseMap = () => {
                const next = baseMapType === 'satellite' ? 'streets' : 'satellite';
                setBaseMapType(next);
                const m = window.mapInstance;
                if (m && m.getLayer('satellite-base')) {
                    m.setLayoutProperty('satellite-base', 'visibility', next === 'satellite' ? 'visible' : 'none');
                }
            };

            const handleToggle2D3D = () => {
                const m = window.mapInstance;
                if (!m) return;
                const currentP = m.getPitch();
                m.easeTo({ pitch: currentP > 10 ? 0 : 62, duration: 600 });
            };

            const getCardinal = (deg) => {
                const d = Math.round(((deg % 360) + 360) % 360);
                const dirs = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
                const idx = Math.round(d / 45) % 8;
                return dirs[idx];
            };

            const handleRotateStep = (deltaDeg) => {
                const m = window.mapInstance;
                if (!m) return;
                const current = m.getBearing();
                m.easeTo({
                    bearing: (current + deltaDeg) % 360,
                    duration: 350
                });
            };

            const handleSetCardinalBearing = (targetBearing) => {
                const m = window.mapInstance;
                if (!m) return;
                m.easeTo({
                    bearing: targetBearing,
                    duration: 550
                });
            };

            const handleSetPitchAngle = (targetPitch) => {
                const m = window.mapInstance;
                if (!m) return;
                m.easeTo({
                    pitch: targetPitch,
                    duration: 550
                });
            };

            const handleUtilityCategoryChange = (cat) => {
                setActiveUtilityCat(cat);
                applyUtilityFilters(cat, showLaterals, showManholes);
            };

            const handleToggleLaterals = () => {
                const next = !showLaterals;
                setShowLaterals(next);
                applyUtilityFilters(activeUtilityCat, next, showManholes);
            };

            const handleToggleManholes = () => {
                const next = !showManholes;
                setShowManholes(next);
                applyUtilityFilters(activeUtilityCat, showLaterals, next);
            };

            const applyUtilityFilters = (cat, latEnabled, mhEnabled) => {
                const m = window.mapInstance;
                if (!m) return;

                const catCondition = (cat === 'all') ? ['!=', 'category', ''] : ['==', 'category', cat];
                const trunkFilter = ['all', ['==', 'is_lateral', false], ['==', 'is_manhole', false], ['!=', 'is_station_box', true], catCondition];

                [
                    'utilities-trench-shadow',
                    'utilities-pipe-casing',
                    'utilities-trunks-core',
                    'utilities-specular-ridge',
                    'utilities-flow-pulse'
                ].forEach(id => {
                    if (m.getLayer(id)) m.setFilter(id, trunkFilter);
                });

                // Hitbox covers all subterranean conduits & stations for instant click registration
                if (m.getLayer('utilities-click-hitbox')) {
                    m.setFilter('utilities-click-hitbox', catCondition);
                }

                if (m.getLayer('utilities-station-boxes')) {
                    const showStation = (cat === 'all' || cat === 'metro_underground');
                    m.setLayoutProperty('utilities-station-boxes', 'visibility', showStation ? 'visible' : 'none');
                }
                if (m.getLayer('utilities-station-boxes-outline')) {
                    const showStation = (cat === 'all' || cat === 'metro_underground');
                    m.setLayoutProperty('utilities-station-boxes-outline', 'visibility', showStation ? 'visible' : 'none');
                }
                if (m.getLayer('utilities-coastal-inner')) {
                    const showCoastal = (cat === 'all' || cat === 'coastal_road_tunnel');
                    m.setLayoutProperty('utilities-coastal-inner', 'visibility', showCoastal ? 'visible' : 'none');
                }
                if (m.getLayer('utilities-coastal-lighting')) {
                    const showCoastal = (cat === 'all' || cat === 'coastal_road_tunnel');
                    m.setLayoutProperty('utilities-coastal-lighting', 'visibility', showCoastal ? 'visible' : 'none');
                }
                if (m.getLayer('utilities-metro-rails')) {
                    const showMetro = (cat === 'all' || cat === 'metro_underground');
                    m.setLayoutProperty('utilities-metro-rails', 'visibility', showMetro ? 'visible' : 'none');
                }
                if (m.getLayer('utilities-pedestrian-stripes')) {
                    const showPed = (cat === 'all' || cat === 'pedestrian_subway');
                    m.setLayoutProperty('utilities-pedestrian-stripes', 'visibility', showPed ? 'visible' : 'none');
                }

                if (m.getLayer('utilities-laterals')) {
                    m.setLayoutProperty('utilities-laterals', 'visibility', latEnabled ? 'visible' : 'none');
                    if (latEnabled) {
                        m.setFilter('utilities-laterals', ['all', ['==', 'is_lateral', true], catCondition]);
                    }
                }

                if (m.getLayer('utilities-manholes-base')) {
                    m.setLayoutProperty('utilities-manholes-base', 'visibility', mhEnabled ? 'visible' : 'none');
                    if (mhEnabled) {
                        m.setFilter('utilities-manholes-base', ['all', ['==', 'is_manhole', true], catCondition]);
                    }
                }
                if (m.getLayer('utilities-manholes')) {
                    m.setLayoutProperty('utilities-manholes', 'visibility', mhEnabled ? 'visible' : 'none');
                    if (mhEnabled) {
                        m.setFilter('utilities-manholes', ['all', ['==', 'is_manhole', true], catCondition]);
                    }
                }
            };

            const handleSearch = (q) => {
                setSearchQuery(q);
                if (!q.trim() || !buildingsData) {
                    setSearchResults([]);
                    return;
                }
                const lower = q.toLowerCase();
                const matched = buildingsData.features.filter(f => {
                    const p = f.properties;
                    return (p.name && p.name.toLowerCase().includes(lower)) ||
                           (p.land_ulpin && p.land_ulpin.includes(lower)) ||
                           (p.street && p.street.toLowerCase().includes(lower));
                }).slice(0, 6);
                setSearchResults(matched);
            };

            const handleFlyToUtility = (u) => {
                if (!window.mapInstance || !utilitiesData) return;
                const feat = utilitiesData.features.find(f => f.properties && f.properties.utility_id === u.utility_id);
                if (!feat || !feat.geometry) return;
                const geom = feat.geometry;
                if (geom.type === 'Point') {
                    window.mapInstance.flyTo({ center: geom.coordinates, zoom: 17.5, pitch: 68, duration: 1200 });
                } else if (geom.type === 'LineString') {
                    const coords = geom.coordinates;
                    const mid = coords[Math.floor(coords.length / 2)];
                    window.mapInstance.flyTo({ center: mid, zoom: 17.2, pitch: 68, duration: 1200 });
                } else if (geom.type === 'Polygon') {
                    const coords = geom.coordinates[0];
                    const mid = coords[0];
                    window.mapInstance.flyTo({ center: mid, zoom: 17.2, pitch: 68, duration: 1200 });
                }
            };

            const createUtilityPopupHTML = (p) => {
                const isStation = p.is_station_box === true || p.is_station_box === 'true';
                const isManhole = p.is_manhole === true || p.is_manhole === 'true';
                const isLateral = p.is_lateral === true || p.is_lateral === 'true';

                let categoryTitle = "SUBTERRANEAN CONDUIT";
                if (isStation) categoryTitle = "METRO 3 STATION BOX";
                else if (p.category === 'coastal_road_tunnel') categoryTitle = isManhole ? "MCRP PORTAL / VENT SHAFT" : "UNDERSEA ROAD HIGHWAY TUNNEL";
                else if (p.category === 'metro_underground') categoryTitle = isManhole ? "METRO VENTILATION SHAFT" : "RAPID TRANSIT METRO TUNNEL";
                else if (p.category === 'vehicular_subway') categoryTitle = "VEHICULAR ROAD UNDERPASS";
                else if (p.category === 'pedestrian_subway') categoryTitle = isManhole ? "SUBWAY ENTRANCE PORTAL" : "PEDESTRIAN COMMUTER SUBWAY";
                else if (isManhole) categoryTitle = "INSPECTION CHAMBER / VAULT";
                else if (isLateral) categoryTitle = "BUILDING SERVICE LATERAL";
                else categoryTitle = "PRIMARY TRUNK TRANSMISSION AQUEDUCT";

                const diameterStr = p.nominal_diameter_mm >= 1000 
                    ? `${(p.nominal_diameter_mm / 1000).toFixed(1)} m (${p.nominal_diameter_mm} mm)`
                    : `${p.nominal_diameter_mm} mm`;

                const accentColor = p.color || '#00e5ff';

                return `
                    <div style="font-family: 'Plus Jakarta Sans', system-ui, sans-serif; width: 100%; box-sizing: border-box; overflow: hidden; user-select: text;">
                        <!-- Header with dedicated right clearance for MapLibre close X -->
                        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; padding-right: 26px;">
                            <span style="font-size: 9px; font-weight: 700; letter-spacing: 0.04em; padding: 2px 7px; border-radius: 4px; background: rgba(255, 255, 255, 0.06); color: #f8fafc; border: 1px solid rgba(255, 255, 255, 0.12); text-transform: uppercase; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 170px; display: inline-flex; align-items: center; gap: 5px;">
                                <span style="width: 6px; height: 6px; border-radius: 50%; background: ${accentColor}; flex-shrink: 0;"></span>
                                ${categoryTitle}
                            </span>
                            <span style="font-size: 10.5px; font-weight: 700; color: #38bdf8; background: rgba(56,189,248,0.1); padding: 2px 7px; border-radius: 4px; border: 1px solid rgba(56,189,248,0.25); white-space: nowrap; flex-shrink: 0;">
                                -${p.depth_msl_m}m MSL
                            </span>
                        </div>
                        <div style="font-weight: 700; font-size: 13.5px; color: #fff; margin-bottom: 3px; line-height: 1.35; word-break: break-word;">
                            ${p.label || 'Subterranean Asset'}
                        </div>
                        <div style="font-size: 10.5px; color: #94a3b8; margin-bottom: 10px; line-height: 1.3; word-break: break-word;">
                            ${p.corridor_name || ''}
                        </div>
                        <div style="display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 6px; background: #131b2e; padding: 8px 10px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.06); margin-bottom: 8px; font-size: 10.5px; box-sizing: border-box;">
                            <div style="min-width: 0; overflow: hidden;">
                                <div style="color: #64748b; font-size: 8.5px; font-weight: 700; text-transform: uppercase;">DIAMETER / BORE</div>
                                <div style="font-weight: 700; color: ${accentColor}; margin-top: 1px; word-break: break-word;">${diameterStr}</div>
                            </div>
                            <div style="min-width: 0; overflow: hidden;">
                                <div style="color: #64748b; font-size: 8.5px; font-weight: 700; text-transform: uppercase;">CLEARANCE</div>
                                <div style="font-weight: 700; color: #10b981; margin-top: 1px; word-break: break-word; line-height: 1.25; font-size: 10px;">${p.clearance_status || 'Compliant'}</div>
                            </div>
                            <div style="grid-column: span 2; padding-top: 4px; border-top: 1px solid rgba(255,255,255,0.06); min-width: 0; overflow: hidden;">
                                <div style="color: #64748b; font-size: 8.5px; font-weight: 700; text-transform: uppercase;">SPECIFICATION & AUTHORITY</div>
                                <div style="color: #cbd5e1; font-size: 10px; margin-top: 1px; word-break: break-word; line-height: 1.3;">
                                    ${p.material || ''} • <b style="color: #38bdf8;">${p.authority || ''}</b>
                                </div>
                            </div>
                            ${p.connected_building ? `
                            <div style="grid-column: span 2; padding-top: 4px; border-top: 1px solid rgba(255,255,255,0.06); min-width: 0; overflow: hidden;">
                                <div style="color: #64748b; font-size: 8.5px; font-weight: 700; text-transform: uppercase;">CONNECTED LANDMARK</div>
                                <div style="color: #f59e0b; font-size: 10px; font-weight: 700; margin-top: 1px; word-break: break-word;">
                                    ${p.connected_building}
                                </div>
                            </div>
                            ` : ''}
                        </div>
                        <div style="font-size: 9.5px; color: #94a3b8; display: flex; justify-content: space-between; align-items: center; padding: 0 2px;">
                            <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 190px;">ULPIN: <b style="font-family: monospace; color: #f59e0b;">${p.utility_ulpin || p.utility_id}</b></span>
                            <span style="color: #10b981; font-weight: 700; flex-shrink: 0;">● Active</span>
                        </div>
                    </div>
                `;
            };

            const initMapLibre = (bldGeo, archGeo, utilGeo) => {
                const MANTRALAYA_COORD = [72.8270, 18.9276];

                const map = new maplibregl.Map({
                    container: 'map',
                    style: {
                        version: 8,
                        sources: {
                            'esri-satellite': {
                                type: 'raster',
                                tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
                                tileSize: 256,
                                attribution: '&copy; ESRI World Imagery'
                            }
                        },
                        layers: [{
                            id: 'satellite-base',
                            type: 'raster',
                            source: 'esri-satellite',
                            paint: { 'raster-brightness-max': 0.92, 'raster-contrast': 0.15 }
                        }]
                    },
                    center: MANTRALAYA_COORD,
                    zoom: 16.55,
                    pitch: 62,
                    bearing: -22,
                    maxPitch: 85,
                    antialias: true
                });

                map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }));

                map.on('load', () => {
                    // Realistic Geographic Sun & Ambient Architectural Lighting (Illuminates all 360° sides)
                    map.setLight({
                        anchor: 'map',
                        color: '#ffffff',
                        intensity: 0.90,
                        position: [1.3, 210, 30]
                    });

                    // 1. Cadastral Land Parcel Outlines on Ground
                    map.addSource('buildings-src', { type: 'geojson', data: bldGeo });
                    map.addLayer({
                        id: 'buildings-ground-line',
                        type: 'line',
                        source: 'buildings-src',
                        paint: {
                            'line-color': [
                                'case',
                                ['==', ['get', 'spatial_id'], 'MUM-BLD-E35A525A'], '#f59e0b',
                                ['==', ['get', 'spatial_id'], 'MUM-BLD-211FC714'], '#f59e0b',
                                ['!=', ['get', 'name'], ''], '#38bdf8',
                                '#64748b'
                            ],
                            'line-width': [
                                'case',
                                ['==', ['get', 'spatial_id'], 'MUM-BLD-E35A525A'], 2.5,
                                ['==', ['get', 'spatial_id'], 'MUM-BLD-211FC714'], 2.5,
                                1.0
                            ],
                            'line-opacity': 0.7
                        }
                    });

                    // 2. Subterranean Infrastructure Networks (Rendered beneath buildings into bedrock strata)
                    if (utilGeo) {
                        map.addSource('utilities-src', { type: 'geojson', data: utilGeo });

                        // A. Invisible 40px Wide Hitbox Buffer (Ensures 100% effortless clicking precision on all subterranean conduits)
                        map.addLayer({
                            id: 'utilities-click-hitbox',
                            type: 'line',
                            source: 'utilities-src',
                            layout: { 'line-cap': 'round', 'line-join': 'round', 'visibility': 'none' },
                            paint: {
                                'line-width': 40.0,
                                'line-color': '#000000',
                                'line-opacity': 0.02
                            }
                        });

                        // B. Subtle Ground Trench Drop Shadow (Crisp depth separation beneath the surface)
                        map.addLayer({
                            id: 'utilities-trench-shadow',
                            type: 'line',
                            source: 'utilities-src',
                            filter: ['all', ['==', 'is_lateral', false], ['==', 'is_manhole', false], ['!=', 'is_station_box', true]],
                            layout: { 'line-cap': 'round', 'line-join': 'round', 'visibility': 'none' },
                            paint: {
                                'line-color': '#020617',
                                'line-width': [
                                    'case',
                                    ['==', ['get', 'category'], 'coastal_road_tunnel'], 18.0,
                                    ['==', ['get', 'category'], 'metro_underground'], 15.0,
                                    ['==', ['get', 'category'], 'vehicular_subway'], 13.0,
                                    ['==', ['get', 'category'], 'pedestrian_subway'], 11.5,
                                    ['==', ['get', 'category'], 'drainage_trunk'], 11.0,
                                    ['==', ['get', 'category'], 'water_supply'], 11.0,
                                    ['==', ['get', 'category'], 'power_best'], 9.5,
                                    ['==', ['get', 'category'], 'gas_mgl'], 9.0,
                                    8.5
                                ],
                                'line-blur': 2.5,
                                'line-opacity': 0.50
                            }
                        });

                        // C. Outer Pipe Wall / Structural Metallic & Concrete Casing (Clean, crisp structural boundary)
                        map.addLayer({
                            id: 'utilities-pipe-casing',
                            type: 'line',
                            source: 'utilities-src',
                            filter: ['all', ['==', 'is_lateral', false], ['==', 'is_manhole', false], ['!=', 'is_station_box', true]],
                            layout: { 'line-cap': 'round', 'line-join': 'round', 'visibility': 'none' },
                            paint: {
                                'line-color': [
                                    'case',
                                    ['==', ['get', 'category'], 'coastal_road_tunnel'], '#070d1e',
                                    ['==', ['get', 'category'], 'metro_underground'], '#0f0926',
                                    ['==', ['get', 'category'], 'vehicular_subway'], '#1c1917',
                                    ['==', ['get', 'category'], 'pedestrian_subway'], '#1c1917',
                                    ['==', ['get', 'category'], 'drainage_trunk'], '#064e3b',
                                    ['==', ['get', 'category'], 'water_supply'], '#082f49',
                                    ['==', ['get', 'category'], 'power_best'], '#450a0a',
                                    ['==', ['get', 'category'], 'gas_mgl'], '#451a03',
                                    '#1e293b'
                                ],
                                'line-width': [
                                    'case',
                                    ['==', ['get', 'category'], 'coastal_road_tunnel'], 13.5,
                                    ['==', ['get', 'category'], 'metro_underground'], 11.0,
                                    ['==', ['get', 'category'], 'vehicular_subway'], 9.0,
                                    ['==', ['get', 'category'], 'pedestrian_subway'], 8.0,
                                    ['==', ['get', 'category'], 'drainage_trunk'], 7.8,
                                    ['==', ['get', 'category'], 'water_supply'], 7.8,
                                    ['==', ['get', 'category'], 'power_best'], 6.8,
                                    ['==', ['get', 'category'], 'gas_mgl'], 6.2,
                                    6.0
                                ],
                                'line-opacity': 1.0
                            }
                        });

                        // D. Physical Pipe Core Body (Vibrant, high-contrast BIM vector conduits matching reference image)
                        map.addLayer({
                            id: 'utilities-trunks-core',
                            type: 'line',
                            source: 'utilities-src',
                            filter: ['all', ['==', 'is_lateral', false], ['==', 'is_manhole', false], ['!=', 'is_station_box', true]],
                            layout: { 'line-cap': 'round', 'line-join': 'round', 'visibility': 'none' },
                            paint: {
                                'line-color': [
                                    'case',
                                    ['==', ['get', 'category'], 'coastal_road_tunnel'], '#0284c7',
                                    ['==', ['get', 'category'], 'metro_underground'], '#8b5cf6',
                                    ['==', ['get', 'category'], 'vehicular_subway'], '#f97316',
                                    ['==', ['get', 'category'], 'pedestrian_subway'], '#eab308',
                                    ['==', ['get', 'category'], 'drainage_trunk'], '#10b981',
                                    ['==', ['get', 'category'], 'water_supply'], '#00e5ff',
                                    ['==', ['get', 'category'], 'power_best'], '#ef4444',
                                    ['==', ['get', 'category'], 'gas_mgl'], '#f59e0b',
                                    ['get', 'color']
                                ],
                                'line-width': [
                                    'case',
                                    ['==', ['get', 'category'], 'coastal_road_tunnel'], 9.5,
                                    ['==', ['get', 'category'], 'metro_underground'], 7.5,
                                    ['==', ['get', 'category'], 'vehicular_subway'], 6.2,
                                    ['==', ['get', 'category'], 'pedestrian_subway'], 5.5,
                                    ['==', ['get', 'category'], 'drainage_trunk'], 5.2,
                                    ['==', ['get', 'category'], 'water_supply'], 5.2,
                                    ['==', ['get', 'category'], 'power_best'], 4.5,
                                    ['==', ['get', 'category'], 'gas_mgl'], 4.2,
                                    4.0
                                ],
                                'line-opacity': 1.0
                            }
                        });

                        // E. 3D Cylindrical Specular Crown Ridge (Highlighting top ridge of conduit)
                        map.addLayer({
                            id: 'utilities-specular-ridge',
                            type: 'line',
                            source: 'utilities-src',
                            filter: ['all', ['==', 'is_manhole', false], ['!=', 'is_station_box', true]],
                            layout: { 'line-cap': 'round', 'line-join': 'round', 'visibility': 'none' },
                            paint: {
                                'line-color': '#ffffff',
                                'line-width': [
                                    'case',
                                    ['==', ['get', 'category'], 'coastal_road_tunnel'], 2.2,
                                    ['==', ['get', 'category'], 'metro_underground'], 1.8,
                                    ['==', ['get', 'category'], 'vehicular_subway'], 1.5,
                                    ['==', ['get', 'category'], 'pedestrian_subway'], 1.4,
                                    ['==', ['get', 'category'], 'drainage_trunk'], 1.3,
                                    ['==', ['get', 'category'], 'water_supply'], 1.3,
                                    ['==', ['get', 'category'], 'power_best'], 1.2,
                                    ['==', ['get', 'category'], 'gas_mgl'], 1.1,
                                    1.0
                                ],
                                'line-opacity': 0.75,
                                'line-blur': 0.2
                            }
                        });

                        // F. Coastal Road Tunnel Dual-Lane Striping & Interior Lighting
                        map.addLayer({
                            id: 'utilities-coastal-inner',
                            type: 'line',
                            source: 'utilities-src',
                            filter: ['==', 'category', 'coastal_road_tunnel'],
                            layout: { 'line-cap': 'round', 'line-join': 'round', 'visibility': 'none' },
                            paint: {
                                'line-color': '#ffffff',
                                'line-width': 2.2,
                                'line-dasharray': [4, 3],
                                'line-opacity': 0.95
                            }
                        });
                        map.addLayer({
                            id: 'utilities-coastal-lighting',
                            type: 'line',
                            source: 'utilities-src',
                            filter: ['==', 'category', 'coastal_road_tunnel'],
                            layout: { 'line-cap': 'round', 'line-join': 'round', 'visibility': 'none' },
                            paint: {
                                'line-color': '#38bdf8',
                                'line-width': 1.2,
                                'line-opacity': 0.85
                            }
                        });

                        // G. Metro Line 3 Twin Steel Railway Tracks
                        map.addLayer({
                            id: 'utilities-metro-rails',
                            type: 'line',
                            source: 'utilities-src',
                            filter: ['==', 'category', 'metro_underground'],
                            layout: { 'line-cap': 'round', 'line-join': 'round', 'visibility': 'none' },
                            paint: {
                                'line-color': '#e2e8f0',
                                'line-width': 1.8,
                                'line-dasharray': [2, 1.5],
                                'line-opacity': 0.95
                            }
                        });

                        // H. Pedestrian Subway Tactile Footway Striping
                        map.addLayer({
                            id: 'utilities-pedestrian-stripes',
                            type: 'line',
                            source: 'utilities-src',
                            filter: ['==', 'category', 'pedestrian_subway'],
                            layout: { 'line-cap': 'round', 'line-join': 'round', 'visibility': 'none' },
                            paint: {
                                'line-color': '#fef08a',
                                'line-width': 1.8,
                                'line-dasharray': [1.5, 1.5],
                                'line-opacity': 0.95
                            }
                        });

                        // I. Building Lateral Hookups (Direct conduit branches into building basements)
                        map.addLayer({
                            id: 'utilities-laterals',
                            type: 'line',
                            source: 'utilities-src',
                            filter: ['==', 'is_lateral', true],
                            layout: { 'line-cap': 'round', 'line-join': 'round', 'visibility': 'none' },
                            paint: {
                                'line-color': ['get', 'color'],
                                'line-width': 3.5,
                                'line-dasharray': [2, 1.5],
                                'line-opacity': 0.95
                            }
                        });

                        // J. Subterranean Fluid & Energy Flow Pulse Layer
                        map.addLayer({
                            id: 'utilities-flow-pulse',
                            type: 'line',
                            source: 'utilities-src',
                            filter: ['all', ['==', 'is_manhole', false], ['!=', 'is_station_box', true]],
                            layout: { 'line-cap': 'round', 'line-join': 'round', 'visibility': 'none' },
                            paint: {
                                'line-color': [
                                    'case',
                                    ['==', ['get', 'category'], 'coastal_road_tunnel'], '#38bdf8',
                                    ['==', ['get', 'category'], 'metro_underground'], '#c084fc',
                                    ['==', ['get', 'category'], 'power_best'], '#fef08a',
                                    ['==', ['get', 'category'], 'gas_mgl'], '#fde047',
                                    ['==', ['get', 'category'], 'water_supply'], '#e0f2fe',
                                    '#ffffff'
                                ],
                                'line-width': 2.5,
                                'line-dasharray': [1, 4],
                                'line-opacity': 0.85
                            }
                        });

                        // K. Metro Line 3 3D Subterranean Station Boxes (Volumetric cut-and-cover underground structures)
                        map.addLayer({
                            id: 'utilities-station-boxes',
                            type: 'fill-extrusion',
                            source: 'utilities-src',
                            filter: ['==', 'is_station_box', true],
                            layout: { 'visibility': 'none' },
                            paint: {
                                'fill-extrusion-base': 0,
                                'fill-extrusion-height': 5.5,
                                'fill-extrusion-color': '#8b5cf6',
                                'fill-extrusion-opacity': 0.70
                            }
                        });
                        map.addLayer({
                            id: 'utilities-station-boxes-outline',
                            type: 'line',
                            source: 'utilities-src',
                            filter: ['==', 'is_station_box', true],
                            layout: { 'visibility': 'none' },
                            paint: {
                                'line-color': '#c084fc',
                                'line-width': 2.5,
                                'line-opacity': 1.0
                            }
                        });

                        // L. Realistic Precision Engineering CAD Inspection Nodes (Sleek junction pins matching reference image)
                        map.addLayer({
                            id: 'utilities-manholes-base',
                            type: 'circle',
                            source: 'utilities-src',
                            filter: ['==', 'is_manhole', true],
                            layout: { 'visibility': 'none' },
                            paint: {
                                'circle-radius': 6.5,
                                'circle-color': '#020617',
                                'circle-blur': 0.4,
                                'circle-opacity': 0.55
                            }
                        });
                        map.addLayer({
                            id: 'utilities-manholes',
                            type: 'circle',
                            source: 'utilities-src',
                            filter: ['==', 'is_manhole', true],
                            layout: { 'visibility': 'none' },
                            paint: {
                                'circle-radius': 4.8,
                                'circle-color': ['get', 'color'],
                                'circle-stroke-width': 1.5,
                                'circle-stroke-color': '#ffffff',
                                'circle-opacity': 1.0
                            }
                        });

                        // M. Subterranean Selection Highlight Beam
                        map.addLayer({
                            id: 'utilities-highlight',
                            type: 'line',
                            source: 'utilities-src',
                            filter: ['==', 'utility_id', ''],
                            layout: { 'line-cap': 'round', 'line-join': 'round', 'visibility': 'none' },
                            paint: {
                                'line-color': '#ffffff',
                                'line-width': 10.0,
                                'line-opacity': 0.95,
                                'line-blur': 1.2
                            }
                        });
                    }

                    // 3. 3D Architectural Multi-Storey Strata Sources & Layers (Drawn ABOVE subterranean networks)
                    map.addSource('buildings-arch-src', { type: 'geojson', data: archGeo });

                    // Foundation Base Plinth (Protruding ground base)
                    map.addLayer({
                        id: 'buildings-3d-base-rim',
                        type: 'fill-extrusion',
                        source: 'buildings-arch-src',
                        filter: ['==', 'strata_type', 'base_rim'],
                        paint: {
                            'fill-extrusion-base': ['get', 'base_m'],
                            'fill-extrusion-height': ['get', 'height_m'],
                            'fill-extrusion-color': [
                                'case',
                                ['==', ['get', 'is_mantralaya'], true], '#f59e0b',
                                ['==', ['get', 'spatial_id'], 'MUM-BLD-E35A525A'], '#f59e0b',
                                ['==', ['get', 'spatial_id'], 'MUM-BLD-211FC714'], '#f59e0b',
                                '#1e293b'
                            ],
                            'fill-extrusion-opacity': 1.0
                        }
                    });

                    // Storey Facade Wall Panels (Deep dark charcoal / navy slate #161f2e)
                    map.addLayer({
                        id: 'buildings-3d-glass',
                        type: 'fill-extrusion',
                        source: 'buildings-arch-src',
                        filter: ['==', 'strata_type', 'glass'],
                        paint: {
                            'fill-extrusion-base': ['get', 'base_m'],
                            'fill-extrusion-height': ['get', 'height_m'],
                            'fill-extrusion-color': '#161f2e',
                            'fill-extrusion-opacity': 1.0
                        }
                    });

                    // Concrete Floor Slab Dividers (Protruding crisp bright white ledges #ffffff)
                    map.addLayer({
                        id: 'buildings-3d-slabs',
                        type: 'fill-extrusion',
                        source: 'buildings-arch-src',
                        filter: ['==', 'strata_type', 'slab'],
                        paint: {
                            'fill-extrusion-base': ['get', 'base_m'],
                            'fill-extrusion-height': ['get', 'height_m'],
                            'fill-extrusion-color': '#ffffff',
                            'fill-extrusion-opacity': 1.0
                        }
                    });

                    // Concrete Roof Caps / Parapet Crowns (Uniform slate steel-blue #7b92b1 matching reference image)
                    map.addLayer({
                        id: 'buildings-3d-roofs',
                        type: 'fill-extrusion',
                        source: 'buildings-arch-src',
                        filter: ['==', 'strata_type', 'roof'],
                        paint: {
                            'fill-extrusion-base': ['get', 'base_m'],
                            'fill-extrusion-height': ['get', 'height_m'],
                            'fill-extrusion-color': '#7b92b1',
                            'fill-extrusion-opacity': 1.0
                        }
                    });

                    // Active Building Selection Highlight
                    map.addLayer({
                        id: 'buildings-3d-highlight',
                        type: 'fill-extrusion',
                        source: 'buildings-arch-src',
                        filter: ['==', 'spatial_id', ''],
                        paint: {
                            'fill-extrusion-base': ['get', 'base_m'],
                            'fill-extrusion-height': ['+', ['get', 'height_m'], 1.2],
                            'fill-extrusion-color': '#2563A6',
                            'fill-extrusion-opacity': 0.75
                        }
                    });

                    // Live Bearing & Pitch Updates for 360° Compass HUD
                    map.on('rotate', () => {
                        setCurrentBearing(map.getBearing());
                    });
                    map.on('pitch', () => {
                        setCurrentPitch(map.getPitch());
                    });

                    // 360° Left-Click Drag Orbit System for Subterranean Exploration
                    const canvas = map.getCanvas();
                    let isLeftDragging = false;
                    let dragStartX = 0;
                    let dragStartY = 0;
                    let startBearing = 0;
                    let startPitch = 0;
                    let hasDragged = false;
                    let suppressNextClick = false;

                    const onMouseDown = (e) => {
                        if (e.button === 0 && undergroundModeRef.current && undergroundOrbitModeRef.current) {
                            isLeftDragging = true;
                            hasDragged = false;
                            dragStartX = e.clientX;
                            dragStartY = e.clientY;
                            startBearing = map.getBearing();
                            startPitch = map.getPitch();
                            map.dragPan.disable();
                        }
                    };

                    const onMouseMove = (e) => {
                        if (!isLeftDragging) return;
                        const dx = e.clientX - dragStartX;
                        const dy = e.clientY - dragStartY;
                        if (Math.abs(dx) > 3 || Math.abs(dy) > 3) {
                            hasDragged = true;
                        }
                        if (hasDragged) {
                            const newBearing = (startBearing + dx * 0.35) % 360;
                            const newPitch = Math.max(0, Math.min(85, startPitch - dy * 0.25));
                            map.setBearing(newBearing);
                            map.setPitch(newPitch);
                        }
                    };

                    const onMouseUp = (e) => {
                        if (!isLeftDragging) return;
                        isLeftDragging = false;
                        map.dragPan.enable();
                        if (hasDragged) {
                            suppressNextClick = true;
                            setTimeout(() => { suppressNextClick = false; }, 60);
                        }
                    };

                    canvas.addEventListener('mousedown', onMouseDown);
                    window.addEventListener('mousemove', onMouseMove);
                    window.addEventListener('mouseup', onMouseUp);

                    // 4. Unified Interactive Subterranean & Architectural Click Dispatcher
                    map.on('click', (e) => {
                        if (suppressNextClick) {
                            suppressNextClick = false;
                            return;
                        }
                        const hitTolerance = 24; // 24px wide bounding box for effortless, 100% reliable clicks
                        const bbox = [
                            [e.point.x - hitTolerance, e.point.y - hitTolerance],
                            [e.point.x + hitTolerance, e.point.y + hitTolerance]
                        ];

                        // Check Subterranean Utilities FIRST (Top Priority)
                        const allUtilLayers = [
                            'utilities-click-hitbox',
                            'utilities-trunks-core',
                            'utilities-pipe-casing',
                            'utilities-station-boxes',
                            'utilities-station-boxes-outline',
                            'utilities-coastal-inner',
                            'utilities-metro-rails',
                            'utilities-pedestrian-stripes',
                            'utilities-laterals',
                            'utilities-manholes'
                        ].filter(id => map.getLayer(id) && map.getLayoutProperty(id, 'visibility') !== 'none');

                        const utilHits = allUtilLayers.length > 0 ? map.queryRenderedFeatures(bbox, { layers: allUtilLayers }) : [];

                        if (utilHits && utilHits.length > 0) {
                            const feat = utilHits.find(f => f.properties && (f.properties.is_manhole === true || f.properties.is_station_box === true)) || utilHits[0];
                            const p = Object.assign({}, feat.properties);
                            if (typeof p.is_station_box === 'string') p.is_station_box = p.is_station_box === 'true';
                            if (typeof p.is_lateral === 'string') p.is_lateral = p.is_lateral === 'true';
                            if (typeof p.is_manhole === 'string') p.is_manhole = p.is_manhole === 'true';

                            setSelectedUtility(p);
                            setSelectedBuilding(null);

                            if (map.getLayer('utilities-highlight')) {
                                map.setLayoutProperty('utilities-highlight', 'visibility', 'visible');
                                map.setFilter('utilities-highlight', ['==', 'utility_id', p.utility_id || '']);
                            }
                            if (map.getLayer('buildings-3d-highlight')) {
                                map.setFilter('buildings-3d-highlight', ['==', 'spatial_id', '']);
                            }

                            // Show instant 3D interactive floating popup anchored to clicked location
                            if (window.utilityPopup) window.utilityPopup.remove();
                            window.utilityPopup = new maplibregl.Popup({
                                closeButton: true,
                                closeOnClick: false,
                                offset: [0, -10],
                                className: 'subterranean-popup'
                            })
                            .setLngLat(e.lngLat)
                            .setHTML(createUtilityPopupHTML(p))
                            .addTo(map);

                            return; // Stop propagation: Utility inspected!
                        }

                        // Check 3D Buildings (Secondary Priority)
                        const clickLayers = ['buildings-3d-glass', 'buildings-3d-slabs', 'buildings-3d-roofs', 'buildings-3d-base-rim'].filter(id => map.getLayer(id));
                        const bldHits = map.queryRenderedFeatures(bbox, { layers: clickLayers });

                        if (bldHits && bldHits.length > 0) {
                            if (window.utilityPopup) window.utilityPopup.remove();
                            const f = bldHits[0];
                            const spId = f.properties.spatial_id;
                            const masterFeat = bldGeo.features.find(b => b.properties.spatial_id === spId) || f;
                            setSelectedBuilding(masterFeat);
                            setSelectedUtility(null);

                            if (map.getLayer('buildings-3d-highlight')) {
                                map.setFilter('buildings-3d-highlight', ['==', 'spatial_id', spId]);
                            }
                            if (map.getLayer('utilities-highlight')) {
                                map.setFilter('utilities-highlight', ['==', 'utility_id', '']);
                            }
                            return;
                        }

                        // Empty Space Clicked: Deselect both
                        if (window.utilityPopup) window.utilityPopup.remove();
                        setSelectedBuilding(null);
                        setSelectedUtility(null);
                        if (map.getLayer('buildings-3d-highlight')) {
                            map.setFilter('buildings-3d-highlight', ['==', 'spatial_id', '']);
                        }
                        if (map.getLayer('utilities-highlight')) {
                            map.setFilter('utilities-highlight', ['==', 'utility_id', '']);
                        }
                    });

                    // 5. Interactive Mouse Cursor Pointer Feedback
                    map.on('mousemove', (e) => {
                        const bbox = [[e.point.x - 16, e.point.y - 16], [e.point.x + 16, e.point.y + 16]];
                        const allUtilLayers = [
                            'utilities-click-hitbox',
                            'utilities-trunks-core',
                            'utilities-pipe-casing',
                            'utilities-station-boxes',
                            'utilities-station-boxes-outline',
                            'utilities-coastal-inner',
                            'utilities-metro-rails',
                            'utilities-pedestrian-stripes',
                            'utilities-laterals',
                            'utilities-manholes'
                        ].filter(id => map.getLayer(id) && map.getLayoutProperty(id, 'visibility') !== 'none');

                        const utilHits = allUtilLayers.length > 0 ? map.queryRenderedFeatures(bbox, { layers: allUtilLayers }) : [];
                        if (utilHits && utilHits.length > 0) {
                            map.getCanvas().style.cursor = 'pointer';
                            return;
                        }

                        const clickLayers = ['buildings-3d-glass', 'buildings-3d-slabs', 'buildings-3d-roofs', 'buildings-3d-base-rim'].filter(id => map.getLayer(id));
                        const bldHits = map.queryRenderedFeatures(bbox, { layers: clickLayers });
                        if (bldHits && bldHits.length > 0) {
                            map.getCanvas().style.cursor = 'pointer';
                            return;
                        }

                        map.getCanvas().style.cursor = '';
                    });

                    // 6. Subterranean Flow Pulse Animation Loop
                    let flowOffset = 0;
                    let lastFlowTs = 0;
                    function loopUtilityFlow(ts) {
                        if (ts - lastFlowTs > 75) {
                            lastFlowTs = ts;
                            flowOffset = (flowOffset + 1) % 12;
                            if (window.mapInstance && window.mapInstance.getLayer('utilities-flow-pulse')) {
                                try {
                                    if (window.mapInstance.getLayoutProperty('utilities-flow-pulse', 'visibility') === 'visible') {
                                        const d1 = flowOffset % 6;
                                        const d2 = 6 - d1;
                                        window.mapInstance.setPaintProperty('utilities-flow-pulse', 'line-dasharray', [0.8, d1, 2.5, d2]);
                                    }
                                } catch(err) {}
                            }
                        }
                        window.flowPulseRaf = requestAnimationFrame(loopUtilityFlow);
                    }
                    window.flowPulseRaf = requestAnimationFrame(loopUtilityFlow);
                });

                window.mapInstance = map;

                // Keyboard 3D Navigation Controls (WASD + RF)
                if (!window.mapKeyboardNavInitialized) {
                    window.mapKeyboardNavInitialized = true;
                    const pressedKeys = new Set();
                    const NAV_KEYS = ['w', 'a', 's', 'd', 'r', 'f', 'arrowup', 'arrowdown', 'arrowleft', 'arrowright'];

                    window.addEventListener('keydown', (e) => {
                        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
                        const k = e.key.toLowerCase();
                        if (NAV_KEYS.includes(k)) {
                            e.preventDefault();
                            pressedKeys.add(k);
                        }
                    });

                    window.addEventListener('keyup', (e) => {
                        const k = e.key.toLowerCase();
                        pressedKeys.delete(k);
                    });

                    function loopKeyboardNav() {
                        if (window.mapInstance && pressedKeys.size > 0) {
                            const m = window.mapInstance;
                            const center = m.getCenter();
                            const bearing = m.getBearing();
                            const pitch = m.getPitch();
                            const zoom = m.getZoom();

                            const zoomFactor = Math.pow(2, 16.5 - zoom);
                            const moveDist = 0.000045 * zoomFactor;
                            const rad = (bearing * Math.PI) / 180;
                            const dLng = Math.sin(rad) * moveDist;
                            const dLat = Math.cos(rad) * moveDist;

                            let newLng = center.lng;
                            let newLat = center.lat;
                            let newBearing = bearing;
                            let newPitch = pitch;

                            // W: Moving forward along current camera view
                            if (pressedKeys.has('w') || pressedKeys.has('arrowup')) {
                                newLng += dLng;
                                newLat += dLat;
                            }
                            // S: Backward moving
                            if (pressedKeys.has('s') || pressedKeys.has('arrowdown')) {
                                newLng -= dLng;
                                newLat -= dLat;
                            }
                            // A: Rotate right (as requested: a - right)
                            if (pressedKeys.has('a') || pressedKeys.has('arrowright')) {
                                newBearing = (newBearing + 1.25) % 360;
                            }
                            // D: Rotate left (as requested: d - left)
                            if (pressedKeys.has('d') || pressedKeys.has('arrowleft')) {
                                newBearing = (newBearing - 1.25) % 360;
                            }
                            // R: Upwards angle (pitch up towards horizon)
                            if (pressedKeys.has('r')) {
                                newPitch = Math.min(85, newPitch + 0.9);
                            }
                            // F: Downwards angle (pitch down towards ground)
                            if (pressedKeys.has('f')) {
                                newPitch = Math.max(0, newPitch - 0.9);
                            }

                            if (newLng !== center.lng || newLat !== center.lat) {
                                m.setCenter([newLng, newLat]);
                            }
                            if (newBearing !== bearing) {
                                m.setBearing(newBearing);
                            }
                            if (newPitch !== pitch) {
                                m.setPitch(newPitch);
                            }
                        }
                        requestAnimationFrame(loopKeyboardNav);
                    }
                    requestAnimationFrame(loopKeyboardNav);
                }
            };

            return (
                <div style={{ width: '100%', height: '100%', position: 'relative', pointerEvents: 'none' }}>
                    {viewMode === 'map' && (
                        <React.Fragment>
                            {/* 1. Page 1 Top Navigation Bar (Consistent with Page 2) */}
                            <div style={{
                                position: 'absolute', top: 0, left: 0, right: 0, height: 48,
                                background: '#20364A', borderBottom: '1px solid rgba(255,255,255,0.1)',
                                padding: '0 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                                zIndex: 70, pointerEvents: 'auto'
                            }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                                    <IconLogoStack />
                                    <div>
                                        <div style={{ fontWeight: 700, fontSize: 14.5, color: '#ffffff', letterSpacing: '-0.01em', lineHeight: 1.15 }}>
                                            3D ULPIN
                                        </div>
                                        <div style={{ fontSize: 10, color: '#9DB2C7', lineHeight: 1.1 }}>
                                            South Mumbai Property & Infrastructure Cadastre
                                        </div>
                                    </div>
                                </div>

                                {/* Center Search Bar */}
                                <div style={{ position: 'relative', width: 380 }}>
                                    <div style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: '#9DB2C7', display: 'flex', pointerEvents: 'none' }}>
                                        <IconSearch />
                                    </div>
                                    <input
                                        type="text"
                                        value={searchQuery}
                                        onChange={(e) => handleSearch(e.target.value)}
                                        placeholder="Search ULPIN, building, street, or parcel..."
                                        style={{
                                            width: '100%', background: 'rgba(255, 255, 255, 0.12)',
                                            border: '1px solid rgba(255, 255, 255, 0.22)', borderRadius: 4,
                                            padding: '5px 12px 5px 30px', color: '#fff', fontSize: 11.5, outline: 'none'
                                        }}
                                    />
                                    {searchResults.length > 0 && (
                                        <div style={{
                                            position: 'absolute', top: 38, left: 0, right: 0, maxHeight: 280, overflowY: 'auto',
                                            zIndex: 100, padding: 6, background: '#FFFFFF', border: '1px solid #D5DCE3',
                                            borderRadius: 4, boxShadow: '0 8px 24px rgba(0,0,0,0.15)'
                                        }}>
                                            {searchResults.map(b => (
                                                <div
                                                    key={b.properties.spatial_id}
                                                    onClick={() => {
                                                        setSelectedBuilding(b);
                                                        setSearchResults([]);
                                                        setSearchQuery('');
                                                        if (window.mapInstance && b.geometry) {
                                                            let coords = null;
                                                            if (b.geometry.type === 'Polygon' && b.geometry.coordinates[0]) {
                                                                coords = b.geometry.coordinates[0][0];
                                                            } else if (b.geometry.type === 'MultiPolygon' && b.geometry.coordinates[0] && b.geometry.coordinates[0][0]) {
                                                                coords = b.geometry.coordinates[0][0][0];
                                                            }
                                                            if (coords) {
                                                                window.mapInstance.flyTo({ center: coords, zoom: 17.2, pitch: 62, duration: 1000 });
                                                            }
                                                        }
                                                    }}
                                                    style={{
                                                        padding: '7px 9px', borderRadius: 4, cursor: 'pointer', fontSize: 11.5,
                                                        marginBottom: 2, background: '#FFFFFF', transition: 'background 0.12s'
                                                    }}
                                                    onMouseEnter={(e) => e.currentTarget.style.background = '#F4F6F8'}
                                                    onMouseLeave={(e) => e.currentTarget.style.background = '#FFFFFF'}
                                                >
                                                    <div style={{ fontWeight: 600, color: '#2563A6' }}>{b.properties.name}</div>
                                                    <div style={{ fontSize: 10, color: '#66717A', marginTop: 2 }}>
                                                        <span className="code-font">{b.properties.land_ulpin}</span> • {b.properties.street}
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>

                                {/* Right Navigation Pills & Profile */}
                                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                    <button
                                        style={{
                                            background: 'rgba(255, 255, 255, 0.16)', border: '1px solid rgba(255, 255, 255, 0.28)',
                                            color: '#ffffff', padding: '5px 10px',
                                            borderRadius: 4, fontSize: 11.5, fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5
                                        }}
                                    >
                                        <IconMap size={13} />
                                        <span>Map</span>
                                    </button>
                                    <button
                                        onClick={() => {
                                            if (selectedBuilding) handleOpenTwin(selectedBuilding);
                                        }}
                                        style={{
                                            background: 'none', border: 'none',
                                            color: selectedBuilding ? '#ffffff' : '#9DB2C7',
                                            padding: '5px 9px', borderRadius: 4, fontSize: 11.5,
                                            cursor: selectedBuilding ? 'pointer' : 'default',
                                            display: 'flex', alignItems: 'center', gap: 5
                                        }}
                                        title={selectedBuilding ? "Open Property Explorer for selected building" : "Select a building on map first"}
                                    >
                                        <IconProperty size={13} />
                                        <span>Property</span>
                                    </button>

                                    <div style={{ width: 1, height: 16, background: 'rgba(255, 255, 255, 0.18)', margin: '0 4px' }} />

                                    <div style={{
                                        display: 'flex', alignItems: 'center', gap: 5, padding: '3px 8px',
                                        borderRadius: 4, background: 'rgba(255, 255, 255, 0.08)',
                                        border: '1px solid rgba(255, 255, 255, 0.15)', color: '#CAD5E0', fontSize: 11
                                    }}>
                                        <span>📍 South Mumbai</span>
                                    </div>

                                    <div style={{
                                        width: 26, height: 26, borderRadius: '50%', background: '#132130',
                                        border: '1px solid rgba(255, 255, 255, 0.25)', color: '#CAD5E0',
                                        fontSize: 10, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center', marginLeft: 4
                                    }} title="Government of Maharashtra Cadastral Officer">
                                        MH
                                    </div>
                                </div>
                            </div>

                            {/* 2. Page 1 Left Sidebar: GIS Layers, View & Tools Panel */}
                            <div style={{
                                position: 'absolute', top: 48, left: 0, bottom: 28, width: 280,
                                background: '#FFFFFF', borderRight: '1px solid #D5DCE3',
                                zIndex: 60, pointerEvents: 'auto', overflowY: 'auto', display: 'flex', flexDirection: 'column'
                            }}>
                                <div style={{ padding: '12px 14px 10px', borderBottom: '1px solid #E2E8F0' }}>
                                    <div style={{ fontSize: 11, fontWeight: 700, color: '#20364A', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                        GIS Layers & Navigation
                                    </div>
                                    <div style={{ fontSize: 10, color: '#66717A', marginTop: 1 }}>
                                        Municipal cadastre and infrastructure stack
                                    </div>
                                </div>

                                {/* Section A: LAYERS */}
                                <div style={{ padding: '12px 14px', borderBottom: '1px solid #E2E8F0' }}>
                                    <div style={{ fontSize: 9.5, fontWeight: 700, color: '#66717A', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                        <span>Cadastral Layers</span>
                                        <span style={{ fontSize: 9, color: '#2563A6', fontWeight: 600 }}>Active (9)</span>
                                    </div>
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                                        {[
                                            { key: 'parcels', label: 'Surface Parcels', desc: 'Cadastral Boundaries' },
                                            { key: 'buildings', label: 'Buildings', desc: '3D Extrusions' },
                                            { key: 'roads', label: 'Roads', desc: 'Street Network' },
                                            { key: 'metro', label: 'Metro Corridors', desc: 'Aqua Line 3' },
                                            { key: 'utilities', label: 'Underground Utilities', desc: 'Subsurface Conduits', isSpecial: true },
                                            { key: 'drainage', label: 'Drainage Network', desc: 'Storm & Sewer' },
                                            { key: 'coastalRoad', label: 'Coastal Road', desc: 'Undersea Tunnel' },
                                            { key: 'satellite', label: 'Satellite Imagery', desc: 'High-Res Ortho' },
                                            { key: 'terrainDem', label: 'Terrain DEM', desc: 'Digital Elevation' }
                                        ].map(l => {
                                            const isChecked = l.key === 'utilities' ? undergroundMode : gisLayers[l.key];
                                            return (
                                                <label
                                                    key={l.key}
                                                    style={{
                                                        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                                                        padding: '4px 6px', borderRadius: 4, cursor: 'pointer',
                                                        background: isChecked ? '#F4F7FA' : 'transparent',
                                                        border: `1px solid ${isChecked ? '#E2E8F0' : 'transparent'}`,
                                                        transition: 'background 0.12s'
                                                    }}
                                                >
                                                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                                        <input
                                                            type="checkbox"
                                                            checked={!!isChecked}
                                                            onChange={() => handleToggleGisLayer(l.key)}
                                                            style={{
                                                                accentColor: '#2563A6', width: 13, height: 13, cursor: 'pointer', margin: 0
                                                            }}
                                                        />
                                                        <span style={{ fontSize: 11, color: isChecked ? '#20364A' : '#66717A', fontWeight: isChecked ? 600 : 400 }}>
                                                            {l.label}
                                                        </span>
                                                    </div>
                                                    <span style={{ fontSize: 9.5, color: '#94A3B8' }}>
                                                        {l.desc}
                                                    </span>
                                                </label>
                                            );
                                        })}
                                    </div>
                                </div>

                                {/* Section B: VIEW */}
                                <div style={{ padding: '12px 14px', borderBottom: '1px solid #E2E8F0' }}>
                                    <div style={{ fontSize: 9.5, fontWeight: 700, color: '#66717A', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8 }}>
                                        Camera View Angles
                                    </div>
                                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 5 }}>
                                        {[
                                            { id: 'iso', label: 'Isometric' },
                                            { id: 'top', label: 'Top (2D)' },
                                            { id: 'front', label: 'Front' },
                                            { id: 'side', label: 'Side' },
                                            { id: 'section', label: 'Section' }
                                        ].map(v => {
                                            const isActive = (mapViewAngle === v.id);
                                            return (
                                                <button
                                                    key={v.id}
                                                    onClick={() => handleSetMapAngle(v.id)}
                                                    style={{
                                                        padding: '6px 4px', borderRadius: 4, fontSize: 10.5, fontWeight: isActive ? 600 : 500,
                                                        background: isActive ? '#E8F1FA' : '#FFFFFF',
                                                        color: isActive ? '#2563A6' : '#263238',
                                                        border: `1px solid ${isActive ? '#C4DCF2' : '#D5DCE3'}`,
                                                        cursor: 'pointer', textAlign: 'center', transition: 'all 0.12s'
                                                    }}
                                                >
                                                    {v.label}
                                                </button>
                                            );
                                        })}
                                    </div>
                                </div>

                                {/* Section C: TOOLS */}
                                <div style={{ padding: '12px 14px', borderBottom: '1px solid #E2E8F0' }}>
                                    <div style={{ fontSize: 9.5, fontWeight: 700, color: '#66717A', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8 }}>
                                        GIS Survey Tools
                                    </div>
                                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 5 }}>
                                        {[
                                            { id: 'select', label: 'Select Asset', icon: <IconSelect size={12} /> },
                                            { id: 'measure', label: 'Measure Tool', icon: <IconMeasure size={12} /> },
                                            { id: 'section', label: 'Cut Section', icon: <IconSection size={12} /> },
                                            { id: 'reset', label: 'Reset View', icon: <IconReset size={12} />, isAction: true }
                                        ].map(t => {
                                            const isActive = (activeMapTool === t.id && !t.isAction);
                                            return (
                                                <button
                                                    key={t.id}
                                                    onClick={() => {
                                                        if (t.isAction) handleResetMapView();
                                                        else setActiveMapTool(t.id);
                                                    }}
                                                    style={{
                                                        padding: '6px 8px', borderRadius: 4, fontSize: 10.5, fontWeight: isActive ? 600 : 500,
                                                        background: isActive ? '#E8F1FA' : '#FFFFFF',
                                                        color: isActive ? '#2563A6' : '#263238',
                                                        border: `1px solid ${isActive ? '#C4DCF2' : '#D5DCE3'}`,
                                                        cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, transition: 'all 0.12s'
                                                    }}
                                                >
                                                    {t.icon}
                                                    <span>{t.label}</span>
                                                </button>
                                            );
                                        })}
                                    </div>
                                </div>

                                {/* Subterranean Quick Controls (Visible when underground mode is active) */}
                                {undergroundMode && (
                                    <div style={{ padding: '12px 14px', flex: 1 }}>
                                        <div style={{ fontSize: 9.5, fontWeight: 700, color: '#2563A6', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8 }}>
                                            Subterranean Networks
                                        </div>
                                        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                                            {[
                                                { id: 'all', label: 'All Conduits' },
                                                { id: 'coastal_road_tunnel', label: 'Coastal Road Tunnel' },
                                                { id: 'metro_underground', label: 'Metro 3 Railway' },
                                                { id: 'water_supply', label: 'Water Transmission' },
                                                { id: 'power_best', label: 'BEST 110kV Power' },
                                                { id: 'gas_mgl', label: 'MGL City Gas' },
                                                { id: 'drainage_trunk', label: 'Deep Sewer Outfall' }
                                            ].map(cat => {
                                                const isCatActive = (activeUtilityCat === cat.id);
                                                return (
                                                    <div
                                                        key={cat.id}
                                                        onClick={() => handleUtilityCategoryChange(cat.id)}
                                                        style={{
                                                            padding: '5px 8px', borderRadius: 4, cursor: 'pointer', fontSize: 10.5,
                                                            background: isCatActive ? '#E8F1FA' : '#F8FAFC',
                                                            border: `1px solid ${isCatActive ? '#C4DCF2' : '#E2E8F0'}`,
                                                            color: isCatActive ? '#2563A6' : '#263238',
                                                            fontWeight: isCatActive ? 600 : 400
                                                        }}
                                                    >
                                                        {cat.label}
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    </div>
                                )}
                            </div>

                            {/* 3. Floating Map Controls (top-right of viewport) */}
                            <div style={{
                                position: 'absolute', top: 58, right: selectedBuilding ? 362 : 16,
                                display: 'flex', flexDirection: 'column', gap: 4, zIndex: 60, pointerEvents: 'auto',
                                transition: 'right 0.2s ease'
                            }}>
                                <div style={{
                                    background: '#FFFFFF', border: '1px solid #D5DCE3', borderRadius: 4,
                                    boxShadow: '0 2px 8px rgba(0,0,0,0.08)', display: 'flex', flexDirection: 'column', overflow: 'hidden'
                                }}>
                                    <button
                                        onClick={() => { if (window.mapInstance) window.mapInstance.zoomIn(); }}
                                        style={{ width: 32, height: 32, background: '#FFFFFF', border: 'none', borderBottom: '1px solid #E2E8F0', cursor: 'pointer', fontSize: 16, color: '#20364A', fontWeight: 600 }}
                                        title="Zoom In"
                                    >
                                        +
                                    </button>
                                    <button
                                        onClick={() => { if (window.mapInstance) window.mapInstance.zoomOut(); }}
                                        style={{ width: 32, height: 32, background: '#FFFFFF', border: 'none', cursor: 'pointer', fontSize: 16, color: '#20364A', fontWeight: 600 }}
                                        title="Zoom Out"
                                    >
                                        −
                                    </button>
                                </div>

                                <div style={{
                                    background: '#FFFFFF', border: '1px solid #D5DCE3', borderRadius: 4,
                                    boxShadow: '0 2px 8px rgba(0,0,0,0.08)', display: 'flex', flexDirection: 'column', overflow: 'hidden'
                                }}>
                                    <button
                                        onClick={() => { if (window.mapInstance) window.mapInstance.resetNorth(); }}
                                        style={{ width: 32, height: 32, background: '#FFFFFF', border: 'none', borderBottom: '1px solid #E2E8F0', cursor: 'pointer', fontSize: 11, color: '#20364A', fontWeight: 700 }}
                                        title="Reset North Orientation"
                                    >
                                        N
                                    </button>
                                    <button
                                        onClick={handleToggle2D3D}
                                        style={{ width: 32, height: 32, background: '#FFFFFF', border: 'none', borderBottom: '1px solid #E2E8F0', cursor: 'pointer', fontSize: 10.5, color: '#20364A', fontWeight: 600 }}
                                        title="Toggle 2D / 3D Perspective"
                                    >
                                        3D
                                    </button>
                                    <button
                                        onClick={handleToggleBaseMap}
                                        style={{ width: 32, height: 32, background: '#FFFFFF', border: 'none', cursor: 'pointer', fontSize: 10, color: '#2563A6', fontWeight: 600 }}
                                        title="Toggle Satellite / Streets Basemap"
                                    >
                                        MAP
                                    </button>
                                </div>

                                <button
                                    onClick={toggleOrbit}
                                    style={{
                                        width: 32, height: 32, background: isOrbiting ? '#2563A6' : '#FFFFFF',
                                        border: `1px solid ${isOrbiting ? '#2563A6' : '#D5DCE3'}`, borderRadius: 4,
                                        color: isOrbiting ? '#FFFFFF' : '#20364A', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
                                        boxShadow: '0 2px 8px rgba(0,0,0,0.08)'
                                    }}
                                    title={isOrbiting ? "Pause 360° Aerial Orbit" : "Start 360° Aerial Orbit"}
                                >
                                    <IconOrbit size={14} />
                                </button>
                            </div>

                            {/* 4. Bottom Scale / Coordinates HUD */}
                            <div style={{
                                position: 'absolute', bottom: 38, left: 296,
                                background: 'rgba(255, 255, 255, 0.95)', border: '1px solid #D5DCE3',
                                borderRadius: 4, padding: '5px 12px', display: 'flex', alignItems: 'center', gap: 14,
                                fontSize: 11, color: '#263238', boxShadow: '0 2px 6px rgba(0,0,0,0.08)',
                                zIndex: 50, pointerEvents: 'auto'
                            }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                    <div style={{ width: 60, height: 3, background: '#20364A', position: 'relative' }}>
                                        <div style={{ position: 'absolute', top: -3, left: 0, width: 1, height: 9, background: '#20364A' }} />
                                        <div style={{ position: 'absolute', top: -3, left: 30, width: 1, height: 5, background: '#20364A' }} />
                                        <div style={{ position: 'absolute', top: -3, right: 0, width: 1, height: 9, background: '#20364A' }} />
                                    </div>
                                    <span style={{ fontSize: 9.5, fontWeight: 600, color: '#66717A' }}>0 50 100 200 m</span>
                                </div>
                                <div style={{ width: 1, height: 12, background: '#D5DCE3' }} />
                                <div style={{ fontSize: 10.5, color: '#66717A' }}>
                                    Elev: <b style={{ color: '#20364A' }}>+12.4 m MSL</b>
                                </div>
                                <div style={{ width: 1, height: 12, background: '#D5DCE3' }} />
                                <div className="code-font" style={{ fontSize: 10.5, color: '#20364A' }}>
                                    18.9256° N, 72.8247° E
                                </div>
                                <div style={{ width: 1, height: 12, background: '#D5DCE3' }} />
                                <div style={{ fontSize: 10, color: '#66717A' }}>
                                    CRS: <b style={{ color: '#2563A6' }}>WGS-84</b>
                                </div>
                            </div>
                        </React.Fragment>
                    )}

                    {/* Right Sidebar: Property Information Panel (Page 1 - ONLY opens when building selected) */}
                    {viewMode === 'map' && selectedBuilding && !selectedUtility && (
                        <div style={{
                            position: 'absolute', top: 48, right: 0, bottom: 28, width: 350,
                            background: '#FFFFFF', borderLeft: '1px solid #D5DCE3',
                            zIndex: 60, pointerEvents: 'auto', overflowY: 'auto', display: 'flex', flexDirection: 'column'
                        }}>
                            {/* Card Header */}
                            <div style={{ padding: '14px 16px 12px', borderBottom: '1px solid #E2E8F0' }}>
                                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
                                    <span style={{
                                        fontSize: 9.5, fontWeight: 700, padding: '2px 8px', borderRadius: 4,
                                        background: '#E8F1FA', color: '#2563A6', border: '1px solid #C4DCF2',
                                        letterSpacing: '0.03em'
                                    }}>
                                        PROPERTY INFORMATION
                                    </span>
                                    <button
                                        onClick={() => {
                                            setSelectedBuilding(null);
                                            if (window.mapInstance && window.mapInstance.getLayer('buildings-3d-highlight')) {
                                                window.mapInstance.setFilter('buildings-3d-highlight', ['==', 'spatial_id', '']);
                                            }
                                        }}
                                        style={{ background: 'none', border: 'none', color: '#66717A', cursor: 'pointer', fontSize: 15, padding: '2px 4px' }}
                                        title="Close property information"
                                    >
                                        ✕
                                    </button>
                                </div>
                                <div style={{ fontSize: 16, fontWeight: 700, color: '#20364A', marginTop: 6, lineHeight: 1.25 }}>
                                    {selectedBuilding.properties.name}
                                </div>
                                <div style={{ fontSize: 11, color: '#66717A', marginTop: 2 }}>
                                    {selectedBuilding.properties.street || "Colaba Ward, South Mumbai"}
                                </div>
                            </div>

                            {/* Tabs Row */}
                            <div style={{ display: 'flex', borderBottom: '1px solid #E2E8F0', background: '#F8FAFC' }}>
                                {[
                                    { id: 'overview', label: 'Overview' },
                                    { id: 'floors', label: 'Floors' },
                                    { id: 'infrastructure', label: 'Infrastructure' },
                                    { id: 'documents', label: 'Documents' }
                                ].map(t => {
                                    const isTabActive = (propertyTab === t.id);
                                    return (
                                        <button
                                            key={t.id}
                                            onClick={() => setPropertyTab(t.id)}
                                            style={{
                                                flex: 1, padding: '8px 4px', border: 'none',
                                                borderBottom: `2px solid ${isTabActive ? '#2563A6' : 'transparent'}`,
                                                background: 'transparent',
                                                color: isTabActive ? '#2563A6' : '#66717A',
                                                fontSize: 10.5, fontWeight: isTabActive ? 600 : 500, cursor: 'pointer'
                                            }}
                                        >
                                            {t.label}
                                        </button>
                                    );
                                })}
                            </div>

                            {/* Tab Content */}
                            <div style={{ padding: '14px 16px', flex: 1, overflowY: 'auto' }}>
                                {propertyTab === 'overview' && (
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                                        {/* Section: Basic Details */}
                                        <div>
                                            <div style={{ fontSize: 10, fontWeight: 700, color: '#66717A', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 6 }}>
                                                Basic Details
                                            </div>
                                            <div style={{ background: '#F8FAFC', border: '1px solid #E2E8F0', borderRadius: 4, padding: '8px 10px', display: 'flex', flexDirection: 'column', gap: 5 }}>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                                                    <span style={{ color: '#66717A' }}>ULPIN</span>
                                                    <span className="code-font" style={{ fontWeight: 700, color: '#2563A6' }}>
                                                        {selectedBuilding.properties.land_ulpin || "27010482910472"}
                                                    </span>
                                                </div>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                                                    <span style={{ color: '#66717A' }}>Building Type</span>
                                                    <span style={{ fontWeight: 600, color: '#20364A' }}>{selectedBuilding.properties.building_type || "Commercial / Mixed"}</span>
                                                </div>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                                                    <span style={{ color: '#66717A' }}>Year Built</span>
                                                    <span style={{ color: '#20364A' }}>{selectedBuilding.properties.year_built || "2018"}</span>
                                                </div>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                                                    <span style={{ color: '#66717A' }}>Structural Type</span>
                                                    <span style={{ color: '#20364A' }}>{selectedBuilding.properties.structural_type || "RCC Framed Structure"}</span>
                                                </div>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                                                    <span style={{ color: '#66717A' }}>Status</span>
                                                    <span style={{ color: '#1F8A4C', fontWeight: 600, background: '#EBF7EE', padding: '1px 6px', borderRadius: 3, fontSize: 10 }}>
                                                        Operational (OC Issued)
                                                    </span>
                                                </div>
                                            </div>
                                        </div>

                                        {/* Section: Area Details */}
                                        <div>
                                            <div style={{ fontSize: 10, fontWeight: 700, color: '#66717A', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 6 }}>
                                                Area & Dimension Details
                                            </div>
                                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
                                                <div style={{ background: '#F8FAFC', border: '1px solid #E2E8F0', borderRadius: 4, padding: '7px 9px' }}>
                                                    <div style={{ fontSize: 9.5, color: '#66717A' }}>Footprint Area</div>
                                                    <div style={{ fontSize: 12.5, fontWeight: 700, color: '#20364A', marginTop: 1 }}>
                                                        {selectedBuilding.properties.area_sqm} m²
                                                    </div>
                                                </div>
                                                <div style={{ background: '#F8FAFC', border: '1px solid #E2E8F0', borderRadius: 4, padding: '7px 9px' }}>
                                                    <div style={{ fontSize: 9.5, color: '#66717A' }}>Built-up Area</div>
                                                    <div style={{ fontSize: 12.5, fontWeight: 700, color: '#20364A', marginTop: 1 }}>
                                                        {(selectedBuilding.properties.area_sqm * (selectedBuilding.properties.floors || 5) * 0.85).toFixed(0)} m²
                                                    </div>
                                                </div>
                                                <div style={{ background: '#F8FAFC', border: '1px solid #E2E8F0', borderRadius: 4, padding: '7px 9px' }}>
                                                    <div style={{ fontSize: 9.5, color: '#66717A' }}>Total Height</div>
                                                    <div style={{ fontSize: 12.5, fontWeight: 700, color: '#20364A', marginTop: 1 }}>
                                                        {selectedBuilding.properties.height_m} m
                                                    </div>
                                                </div>
                                                <div style={{ background: '#F8FAFC', border: '1px solid #E2E8F0', borderRadius: 4, padding: '7px 9px' }}>
                                                    <div style={{ fontSize: 9.5, color: '#66717A' }}>FSI / FAR</div>
                                                    <div style={{ fontSize: 12.5, fontWeight: 700, color: '#20364A', marginTop: 1 }}>
                                                        2.45
                                                    </div>
                                                </div>
                                            </div>
                                        </div>

                                        {/* Section: Cadastral & Ownership */}
                                        <div>
                                            <div style={{ fontSize: 10, fontWeight: 700, color: '#66717A', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 6 }}>
                                                Cadastral & Ownership
                                            </div>
                                            <div style={{ background: '#F8FAFC', border: '1px solid #E2E8F0', borderRadius: 4, padding: '8px 10px', display: 'flex', flexDirection: 'column', gap: 5 }}>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                                                    <span style={{ color: '#66717A' }}>CTS Survey No.</span>
                                                    <span style={{ fontWeight: 600, color: '#20364A' }}>{selectedBuilding.properties.cts_no || "CTS 418/A"}</span>
                                                </div>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                                                    <span style={{ color: '#66717A' }}>Ward / Division</span>
                                                    <span style={{ color: '#20364A' }}>A Ward (Colaba)</span>
                                                </div>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                                                    <span style={{ color: '#66717A' }}>Tenure</span>
                                                    <span style={{ color: '#20364A', fontWeight: 600 }}>Freehold Title</span>
                                                </div>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                                                    <span style={{ color: '#66717A' }}>Municipal Tax Zone</span>
                                                    <span style={{ color: '#20364A' }}>Zone 1-A (South City)</span>
                                                </div>
                                            </div>
                                        </div>

                                        {/* Section: Infrastructure Connections */}
                                        <div>
                                            <div style={{ fontSize: 10, fontWeight: 700, color: '#66717A', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 6 }}>
                                                Infrastructure Connections
                                            </div>
                                            <div style={{ background: '#F8FAFC', border: '1px solid #E2E8F0', borderRadius: 4, padding: '8px 10px', display: 'flex', flexDirection: 'column', gap: 5 }}>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                                                    <span style={{ color: '#66717A' }}>Water Supply</span>
                                                    <span style={{ color: '#20364A' }}>MCGM 900mm Line</span>
                                                </div>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                                                    <span style={{ color: '#66717A' }}>Sewerage Outfall</span>
                                                    <span style={{ color: '#20364A' }}>Deep 1800mm Box</span>
                                                </div>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                                                    <span style={{ color: '#66717A' }}>Electric Substation</span>
                                                    <span style={{ color: '#20364A' }}>BEST 110kV Grid</span>
                                                </div>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                                                    <span style={{ color: '#66717A' }}>Metro 3 Proximity</span>
                                                    <span style={{ color: '#2563A6', fontWeight: 600 }}>180m (Vidhan Bhavan)</span>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                )}

                                {propertyTab === 'floors' && (
                                    <div style={{ fontSize: 11, color: '#263238', lineHeight: 1.5 }}>
                                        <div style={{ fontWeight: 600, color: '#20364A', marginBottom: 6 }}>
                                            Storey Allocation ({selectedBuilding.properties.floors || 5} Levels)
                                        </div>
                                        <div style={{ background: '#F8FAFC', border: '1px solid #E2E8F0', borderRadius: 4, padding: '8px 10px', marginBottom: 10 }}>
                                            <div>• Ground Floor: Entrance Lobby & Retail Units</div>
                                            <div>• Floors 1 – {selectedBuilding.properties.floors ? selectedBuilding.properties.floors - 1 : 4}: Typical Commercial Suites</div>
                                            <div>• Floor {selectedBuilding.properties.floors || 5}: Penthouse Executive Offices</div>
                                            <div>• Basement: Utilities & Substation Connections</div>
                                        </div>
                                        <div style={{ fontSize: 10.5, color: '#66717A', background: '#E8F1FA', padding: 8, borderRadius: 4, border: '1px solid #C4DCF2' }}>
                                            ℹ️ Full 3D floor-by-floor breakdown, individual flat deeds, and BIM models are available in <b>Property Explorer</b>.
                                        </div>
                                    </div>
                                )}

                                {propertyTab === 'infrastructure' && (
                                    <div style={{ fontSize: 11, color: '#263238', lineHeight: 1.5 }}>
                                        <div style={{ fontWeight: 600, color: '#20364A', marginBottom: 6 }}>
                                            Municipal Utility Status
                                        </div>
                                        <div style={{ background: '#F8FAFC', border: '1px solid #E2E8F0', borderRadius: 4, padding: '8px 10px', display: 'flex', flexDirection: 'column', gap: 4 }}>
                                            <div>• Feeder Lateral: Connected (Active)</div>
                                            <div>• Inspection Chamber: Node #MCGM-418</div>
                                            <div>• Stormwater Clearance: 100% (Compliant)</div>
                                        </div>
                                    </div>
                                )}

                                {propertyTab === 'documents' && (
                                    <div style={{ fontSize: 11, color: '#263238', display: 'flex', flexDirection: 'column', gap: 6 }}>
                                        {[
                                            { title: "CTS Cadastral Sanad Certificate", date: "Verified 2021" },
                                            { title: "Commencement Certificate (CC)", date: "Approved 2016" },
                                            { title: "Occupancy Certificate (OC)", date: "Issued 2018" },
                                            { title: "3D Cadastral Digital Boundary", date: "GIS Verified" }
                                        ].map((d, i) => (
                                            <div key={i} style={{ background: '#F8FAFC', border: '1px solid #E2E8F0', borderRadius: 4, padding: '7px 9px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                                <div>
                                                    <div style={{ fontWeight: 600, color: '#20364A' }}>{d.title}</div>
                                                    <div style={{ fontSize: 9.5, color: '#66717A' }}>{d.date}</div>
                                                </div>
                                                <span style={{ color: '#2563A6', fontSize: 10, fontWeight: 600 }}>PDF</span>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>

                            {/* Primary Action Button */}
                            <div style={{ padding: '12px 16px', borderTop: '1px solid #E2E8F0', background: '#FFFFFF' }}>
                                <button
                                    onClick={() => handleOpenTwin(selectedBuilding)}
                                    style={{
                                        width: '100%', background: '#2563A6',
                                        color: '#FFFFFF', border: 'none', padding: '10px 14px', borderRadius: 4,
                                        fontWeight: 600, fontSize: 12, cursor: 'pointer', display: 'flex', alignItems: 'center',
                                        justifyContent: 'center', gap: 8, transition: 'background 0.12s'
                                    }}
                                    onMouseEnter={(e) => e.currentTarget.style.background = '#1E4E8C'}
                                    onMouseLeave={(e) => e.currentTarget.style.background = '#2563A6'}
                                >
                                    <IconBuilding size={14} />
                                    <span>Open Property Explorer →</span>
                                </button>
                            </div>
                        </div>
                    )}

                    {/* Subterranean Utility Card (when a pipe/tunnel is clicked) */}
                    {viewMode === 'map' && selectedUtility && (
                        <div style={{
                            position: 'absolute', bottom: 38, right: 16, width: 340, padding: 14,
                            pointerEvents: 'auto', zIndex: 60, background: '#FFFFFF', border: '1px solid #D5DCE3',
                            borderRadius: 4, boxShadow: '0 8px 24px rgba(0,0,0,0.12)'
                        }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                                <span style={{
                                    fontSize: 9.5, fontWeight: 700, padding: '2px 8px', borderRadius: 4,
                                    background: '#E8F1FA', color: '#2563A6', border: '1px solid #C4DCF2', letterSpacing: '0.03em'
                                }}>
                                    SUBTERRANEAN CONDUIT
                                </span>
                                <button
                                    onClick={() => {
                                        setSelectedUtility(null);
                                        if (window.utilityPopup) window.utilityPopup.remove();
                                        if (window.mapInstance && window.mapInstance.getLayer('utilities-highlight')) {
                                            window.mapInstance.setFilter('utilities-highlight', ['==', 'utility_id', '']);
                                        }
                                    }}
                                    style={{ background: 'none', border: 'none', color: '#66717A', cursor: 'pointer', fontSize: 14 }}
                                >
                                    ✕
                                </button>
                            </div>
                            <div style={{ fontSize: 14, fontWeight: 700, color: '#20364A' }}>
                                {selectedUtility.label}
                            </div>
                            <div style={{ fontSize: 10.5, color: '#66717A', marginBottom: 8 }}>
                                {selectedUtility.corridor_name}
                            </div>
                            <div style={{ background: '#F8FAFC', border: '1px solid #E2E8F0', borderRadius: 4, padding: '6px 8px', marginBottom: 10, fontSize: 10.5, display: 'flex', flexDirection: 'column', gap: 3 }}>
                                <div>ULPIN: <b className="code-font" style={{ color: '#2563A6' }}>{selectedUtility.utility_ulpin}</b></div>
                                <div>Depth: <b>-{selectedUtility.depth_msl_m} m MSL</b></div>
                                <div>Diameter: <b>Ø {selectedUtility.nominal_diameter_mm} mm</b></div>
                                <div>Authority: <b style={{ color: '#20364A' }}>{selectedUtility.authority}</b></div>
                            </div>
                            {selectedUtility.building_spatial_id && (
                                <button
                                    onClick={() => {
                                        const bld = buildingsData && buildingsData.features.find(b => b.properties.spatial_id === selectedUtility.building_spatial_id);
                                        if (bld) handleOpenTwin(bld);
                                    }}
                                    style={{
                                        width: '100%', background: '#2563A6', color: '#fff', border: 'none',
                                        padding: '8px', borderRadius: 4, fontSize: 11, fontWeight: 600, cursor: 'pointer'
                                    }}
                                >
                                    Open Connected Building Explorer →
                                </button>
                            )}
                        </div>
                    )}

                    {/* Page 1 Full-width Footer */}
                    {viewMode === 'map' && (
                        <div style={{
                            position: 'absolute', bottom: 0, left: 0, right: 0, height: 28,
                            background: '#20364A', borderTop: '1px solid rgba(255,255,255,0.1)',
                            padding: '0 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                            zIndex: 65, pointerEvents: 'auto'
                        }}>
                            <div style={{ fontSize: 10.5, color: '#9DB2C7' }}>
                                3D ULPIN v1.0 | Government of Maharashtra (Prototype)
                            </div>
                            <div style={{ fontSize: 10.5, color: '#9DB2C7' }}>
                                Data Source: Municipal Records | CRS: WGS-84 | Scale 1:2500
                            </div>
                        </div>
                    )}

                    {viewMode === 'twin' && cadastre && (
                        <React.Fragment>
                            {/* 1. Full-width Top Navigation Bar */}
                            <div style={{
                                position: 'absolute', top: 0, left: 0, right: 0, height: 48,
                                background: '#20364A', borderBottom: '1px solid rgba(255,255,255,0.1)',
                                padding: '0 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                                zIndex: 70, pointerEvents: 'auto'
                            }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                                    <IconLogoStack />
                                    <div>
                                        <div style={{ fontWeight: 700, fontSize: 14.5, color: '#ffffff', letterSpacing: '-0.01em', lineHeight: 1.15 }}>
                                            3D ULPIN
                                        </div>
                                        <div style={{ fontSize: 10, color: '#9DB2C7', lineHeight: 1.1 }}>
                                            South Mumbai Property & Infrastructure Cadastre
                                        </div>
                                    </div>
                                </div>

                                <div style={{ position: 'relative', width: 380 }}>
                                    <div style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: '#9DB2C7', display: 'flex', pointerEvents: 'none' }}>
                                        <IconSearch />
                                    </div>
                                    <input
                                        type="text"
                                        value={searchQuery}
                                        onChange={(e) => handleSearch(e.target.value)}
                                        placeholder="Search ULPIN / Property / Building / Street..."
                                        style={{
                                            width: '100%', background: 'rgba(255, 255, 255, 0.12)',
                                            border: '1px solid rgba(255, 255, 255, 0.22)', borderRadius: 4,
                                            padding: '5px 12px 5px 30px', color: '#fff', fontSize: 11.5, outline: 'none'
                                        }}
                                    />
                                </div>

                                <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                                    <button
                                        onClick={handleCloseTwin}
                                        style={{
                                            background: 'none', border: 'none', color: '#CAD5E0', padding: '5px 9px',
                                            borderRadius: 4, fontSize: 11.5, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5
                                        }}
                                    >
                                        <IconMap size={13} />
                                        <span>Map</span>
                                    </button>
                                    <button
                                        style={{
                                            background: 'rgba(255, 255, 255, 0.16)', border: '1px solid rgba(255, 255, 255, 0.28)',
                                            color: '#ffffff', padding: '5px 10px',
                                            borderRadius: 4, fontSize: 11.5, fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5
                                        }}
                                    >
                                        <IconProperty size={13} />
                                        <span>Property</span>
                                    </button>
                                    <button
                                        style={{
                                            background: 'none', border: 'none', color: '#CAD5E0', padding: '5px 9px',
                                            borderRadius: 4, fontSize: 11.5, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5
                                        }}
                                    >
                                        <IconLayers size={13} />
                                        <span>Layers</span>
                                    </button>
                                    <button
                                        style={{
                                            background: 'none', border: 'none', color: '#CAD5E0', padding: '5px 9px',
                                            borderRadius: 4, fontSize: 11.5, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5
                                        }}
                                    >
                                        <IconTools size={13} />
                                        <span>Tools</span>
                                    </button>
                                    <button
                                        style={{
                                            background: 'none', border: 'none', color: '#CAD5E0', padding: '5px 9px',
                                            borderRadius: 4, fontSize: 11.5, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5
                                        }}
                                    >
                                        <IconReports size={13} />
                                        <span>Reports</span>
                                    </button>

                                    <div style={{ height: 16, width: 1, background: 'rgba(255,255,255,0.2)', margin: '0 6px' }} />

                                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                                        <div style={{ width: 24, height: 24, borderRadius: '50%', background: '#2563A6', color: '#fff', fontSize: 11, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                            N
                                        </div>
                                        <span style={{ fontSize: 11.5, color: '#f1f5f9', fontWeight: 600 }}>Nisarg</span>
                                        <IconChevronDown size={9} />
                                    </div>
                                </div>
                            </div>

                            {/* 2. Sub-header Bar: Back to Map & Clickable Breadcrumbs */}
                            <div style={{
                                position: 'absolute', top: 48, left: 0, right: 0, height: 34,
                                background: '#ffffff', borderBottom: '1px solid #D5DCE3',
                                padding: '0 16px', display: 'flex', alignItems: 'center',
                                zIndex: 65, pointerEvents: 'auto'
                            }}>
                                <button
                                    onClick={handleCloseTwin}
                                    style={{
                                        background: 'none', border: 'none', color: '#263238', fontWeight: 600,
                                        fontSize: 11.5, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5,
                                        padding: '3px 6px', borderRadius: 4
                                    }}
                                >
                                    <IconBack size={12} />
                                    <span>Back to Map</span>
                                </button>

                                <div style={{ height: 14, width: 1, background: '#D5DCE3', margin: '0 10px' }} />

                                <div style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: '#66717A' }}>
                                    <span style={{ cursor: 'pointer' }}>South Mumbai</span>
                                    <IconChevronRight size={9} />
                                    <span style={{ cursor: 'pointer' }}>{cadastre.cadastral_division.replace(' Division', '')}</span>
                                    <IconChevronRight size={9} />
                                    <span
                                        onClick={() => {
                                            setSelectedFloor(null);
                                            setSelectedFlat(null);
                                            if (twinRef.current) twinRef.current.selectFlat(null);
                                        }}
                                        style={{ cursor: 'pointer', fontWeight: 600, color: '#263238' }}
                                    >
                                        CTS {cadastre.cts_no}
                                    </span>
                                    <IconChevronRight size={9} />
                                    <span
                                        onClick={() => {
                                            setSelectedFloor(null);
                                            setSelectedFlat(null);
                                            if (twinRef.current) twinRef.current.selectFlat(null);
                                        }}
                                        style={{ cursor: 'pointer' }}
                                    >
                                        Building
                                    </span>
                                    {selectedFloor !== null && (
                                        <React.Fragment>
                                            <IconChevronRight size={9} />
                                            <span style={{ cursor: 'pointer', fontWeight: 600, color: '#263238' }}>
                                                Floor {selectedFloor + 1}
                                            </span>
                                        </React.Fragment>
                                    )}
                                    {selectedFlat && (
                                        <React.Fragment>
                                            <IconChevronRight size={9} />
                                            <span style={{ fontWeight: 600, color: '#2563A6' }}>
                                                Flat {selectedFlat.unit_number}
                                            </span>
                                        </React.Fragment>
                                    )}
                                </div>
                            </div>

                            {/* 3. Left Sidebar: Property Explorer Tree & Quick Actions */}
                            <div style={{
                                position: 'absolute', top: 92, left: 14, bottom: 32, width: 270,
                                background: '#ffffff', border: '1px solid #D5DCE3', borderRadius: 5,
                                boxShadow: '0 1px 3px rgba(0,0,0,0.04)', display: 'flex', flexDirection: 'column',
                                zIndex: 60, pointerEvents: 'auto', overflow: 'hidden'
                            }}>
                                <div style={{
                                    padding: '9px 12px', borderBottom: '1px solid #E8ECEF',
                                    display: 'flex', alignItems: 'center', justifyContent: 'space-between'
                                }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 12, fontWeight: 700, color: '#263238' }}>
                                        <IconFolder size={13} color="#2563A6" />
                                        <span>Property Explorer</span>
                                    </div>
                                    <button style={{ background: 'none', border: 'none', color: '#66717A', cursor: 'pointer', fontSize: 11 }}>
                                        «
                                    </button>
                                </div>

                                <div style={{ flex: 1, overflowY: 'auto', padding: '8px 6px' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '3px 6px', fontSize: 11, color: '#263238', fontWeight: 600 }}>
                                        <IconChevronDown size={9} />
                                        <IconFolder size={12} color="#66717A" />
                                        <span>South Mumbai</span>
                                    </div>

                                    <div style={{ paddingLeft: 14 }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '3px 6px', fontSize: 11, color: '#263238', fontWeight: 600 }}>
                                            <IconChevronDown size={9} />
                                            <IconFolder size={12} color="#66717A" />
                                            <span>{cadastre.cadastral_division.replace(' Division', '')}</span>
                                        </div>

                                        <div style={{ paddingLeft: 14 }}>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '3px 6px', fontSize: 11, color: '#263238' }}>
                                                <IconChevronDown size={9} />
                                                <IconFolder size={12} color="#66717A" />
                                                <span>CTS {cadastre.cts_no}</span>
                                            </div>

                                            <div style={{ paddingLeft: 14 }}>
                                                <div style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '3px 6px', fontSize: 11, color: '#263238', fontWeight: 600 }}>
                                                    <IconChevronDown size={9} />
                                                    <IconBuilding size={12} color="#66717A" />
                                                    <span>Building</span>
                                                </div>

                                                <div style={{ paddingLeft: 14 }}>
                                                    <div style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '3px 6px', fontSize: 11, color: '#66717A' }}>
                                                        <IconChevronRight size={8} />
                                                        <IconFolder size={12} color="#8A96A3" />
                                                        <span>Terrace</span>
                                                    </div>

                                                    {cadastre.floors.slice().reverse().map(fl => {
                                                        const isExpanded = !!expandedFloors[fl.floor_index];
                                                        const isFloorSelected = (selectedFloor === fl.floor_index);
                                                        return (
                                                            <div key={fl.floor_index}>
                                                                <div
                                                                    onClick={() => handleTreeFloorClick(fl.floor_index)}
                                                                    style={{
                                                                        display: 'flex', alignItems: 'center', gap: 5, padding: '3px 6px',
                                                                        fontSize: 11, color: isFloorSelected ? '#2563A6' : '#263238',
                                                                        fontWeight: isFloorSelected ? 600 : 500, cursor: 'pointer',
                                                                        borderRadius: 4, background: isFloorSelected ? '#E8F1FA' : 'transparent'
                                                                    }}
                                                                >
                                                                    <span
                                                                        onClick={(e) => toggleFloorExpanded(fl.floor_index, e)}
                                                                        style={{ display: 'flex', alignItems: 'center', cursor: 'pointer', padding: 2 }}
                                                                    >
                                                                        {isExpanded ? <IconChevronDown size={8} /> : <IconChevronRight size={8} />}
                                                                    </span>
                                                                    {isExpanded ? <IconFolderOpen size={12} color="#2563A6" /> : <IconFolder size={12} color="#8A96A3" />}
                                                                    <span>{fl.floor_label}</span>
                                                                </div>

                                                                {isExpanded && fl.units && (
                                                                    <div style={{ paddingLeft: 16, margin: '2px 0' }}>
                                                                        {fl.units.map(u => {
                                                                            const isFlatActive = (selectedFlat && selectedFlat.unit_id === u.unit_id);
                                                                            return (
                                                                                <div
                                                                                    key={u.unit_id}
                                                                                    onClick={() => handleTreeFlatClick(u)}
                                                                                    style={{
                                                                                        display: 'flex', alignItems: 'center', gap: 5,
                                                                                        padding: '3px 7px', borderRadius: 4, fontSize: 10.5,
                                                                                        cursor: 'pointer', marginBottom: 2, transition: 'all 0.1s',
                                                                                        background: isFlatActive ? '#E8F1FA' : 'transparent',
                                                                                        color: isFlatActive ? '#2563A6' : '#263238',
                                                                                        fontWeight: isFlatActive ? 600 : 500,
                                                                                        border: isFlatActive ? '1px solid #C4DCF2' : '1px solid transparent'
                                                                                    }}
                                                                                >
                                                                                    <IconUnit size={11} color={isFlatActive ? '#2563A6' : '#8A96A3'} />
                                                                                    <span>Flat {u.unit_number}</span>
                                                                                </div>
                                                                            );
                                                                        })}
                                                                    </div>
                                                                )}
                                                            </div>
                                                        );
                                                    })}
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                <div style={{ borderTop: '1px solid #E8ECEF', padding: '10px 12px', background: '#F8FAFC' }}>
                                    <div style={{ fontSize: 10, fontWeight: 700, color: '#66717A', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                        Quick Actions
                                    </div>
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                                        <button
                                            onClick={() => setActiveTool('select')}
                                            style={{
                                                background: activeTool === 'select' ? '#E8F1FA' : 'transparent',
                                                border: activeTool === 'select' ? '1px solid #C4DCF2' : '1px solid transparent',
                                                color: activeTool === 'select' ? '#2563A6' : '#263238',
                                                borderRadius: 4, padding: '4px 7px', fontSize: 11, fontWeight: activeTool === 'select' ? 600 : 500,
                                                cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 7, textAlign: 'left'
                                            }}
                                        >
                                            <IconSelect size={12} />
                                            <span>Select</span>
                                        </button>
                                        <button
                                            onClick={() => setActiveTool('measure')}
                                            style={{
                                                background: activeTool === 'measure' ? '#E8F1FA' : 'transparent',
                                                border: activeTool === 'measure' ? '1px solid #C4DCF2' : '1px solid transparent',
                                                color: activeTool === 'measure' ? '#2563A6' : '#263238',
                                                borderRadius: 4, padding: '4px 7px', fontSize: 11, fontWeight: activeTool === 'measure' ? 600 : 500,
                                                cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 7, textAlign: 'left'
                                            }}
                                        >
                                            <IconMeasure size={12} />
                                            <span>Measure</span>
                                        </button>
                                        <button
                                            onClick={() => handleExplodeChange(explodeRatio > 0.1 ? 0 : 0.8)}
                                            style={{
                                                background: explodeRatio > 0.1 ? '#E8F1FA' : 'transparent',
                                                border: explodeRatio > 0.1 ? '1px solid #C4DCF2' : '1px solid transparent',
                                                color: explodeRatio > 0.1 ? '#2563A6' : '#263238',
                                                borderRadius: 4, padding: '4px 7px', fontSize: 11, fontWeight: explodeRatio > 0.1 ? 600 : 500,
                                                cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 7, textAlign: 'left'
                                            }}
                                        >
                                            <IconExplode size={12} />
                                            <span>Explode Floors</span>
                                        </button>
                                        <button
                                            onClick={() => setActiveTool('section')}
                                            style={{
                                                background: activeTool === 'section' ? '#E8F1FA' : 'transparent',
                                                border: activeTool === 'section' ? '1px solid #C4DCF2' : '1px solid transparent',
                                                color: activeTool === 'section' ? '#2563A6' : '#263238',
                                                borderRadius: 4, padding: '4px 7px', fontSize: 11, fontWeight: activeTool === 'section' ? 600 : 500,
                                                cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 7, textAlign: 'left'
                                            }}
                                        >
                                            <IconSection size={12} />
                                            <span>Section View</span>
                                        </button>
                                        <button
                                            onClick={() => {
                                                if (twinRef.current) twinRef.current.setCameraPreset('3d');
                                            }}
                                            style={{
                                                background: 'transparent', border: '1px solid transparent', color: '#263238',
                                                borderRadius: 4, padding: '4px 7px', fontSize: 11, fontWeight: 500,
                                                cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 7, textAlign: 'left'
                                            }}
                                        >
                                            <IconReset size={12} />
                                            <span>Reset View</span>
                                        </button>
                                    </div>
                                </div>
                            </div>

                            {/* 4. Floating 3D Viewport Controls & Overlays */}
                            {/* View Mode Switcher: 3D / Floor Plan / Exploded View */}
                            <div style={{
                                position: 'absolute', top: 94, left: 298, zIndex: 60,
                                display: 'flex', background: '#ffffff', border: '1px solid #D5DCE3',
                                borderRadius: 4, padding: 2, boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
                                pointerEvents: 'auto'
                            }}>
                                {[
                                    { id: '3d', label: '3D' },
                                    { id: 'plan', label: 'Floor Plan' },
                                    { id: 'exploded', label: 'Exploded View' }
                                ].map(m => {
                                    const isActive = (twinViewMode === m.id);
                                    return (
                                        <button
                                            key={m.id}
                                            onClick={() => {
                                                setTwinViewMode(m.id);
                                                if (twinRef.current) twinRef.current.setCameraPreset(m.id);
                                                if (m.id === 'exploded') handleExplodeChange(0.8);
                                            }}
                                            style={{
                                                background: isActive ? '#2563A6' : 'transparent',
                                                color: isActive ? '#ffffff' : '#263238',
                                                border: 'none',
                                                borderRadius: 3, padding: '4px 11px', fontSize: 11, fontWeight: isActive ? 600 : 500,
                                                cursor: 'pointer', transition: 'all 0.12s'
                                            }}
                                        >
                                            {m.label}
                                        </button>
                                    );
                                })}
                            </div>

                            {/* Left Floating CAD Tools */}
                            <div style={{
                                position: 'absolute', top: 136, left: 298, zIndex: 60,
                                display: 'flex', flexDirection: 'column', gap: 3,
                                background: '#ffffff', border: '1px solid #D5DCE3',
                                borderRadius: 4, padding: 3, pointerEvents: 'auto', boxShadow: '0 1px 3px rgba(0,0,0,0.05)'
                            }}>
                                <button
                                    onClick={() => setActiveTool('select')}
                                    style={{
                                        background: activeTool === 'select' ? '#E8F1FA' : 'transparent',
                                        border: 'none', color: activeTool === 'select' ? '#2563A6' : '#263238',
                                        borderRadius: 3, padding: 6, cursor: 'pointer', display: 'flex'
                                    }}
                                    title="Select"
                                >
                                    <IconSelect size={14} />
                                </button>
                                <button
                                    onClick={() => {
                                        if (twinRef.current) twinRef.current.alignNorth();
                                    }}
                                    style={{
                                        background: 'transparent', border: 'none', color: '#263238',
                                        borderRadius: 3, padding: 6, cursor: 'pointer', display: 'flex'
                                    }}
                                    title="360° Orbit Rotate"
                                >
                                    <IconOrbit size={14} />
                                </button>
                                <button
                                    onClick={() => setActiveTool('measure')}
                                    style={{
                                        background: activeTool === 'measure' ? '#E8F1FA' : 'transparent',
                                        border: 'none', color: activeTool === 'measure' ? '#2563A6' : '#263238',
                                        borderRadius: 3, padding: 6, cursor: 'pointer', display: 'flex'
                                    }}
                                    title="Measure"
                                >
                                    <IconMeasure size={14} />
                                </button>
                                <button
                                    onClick={() => {
                                        if (twinRef.current) twinRef.current.setCameraPreset('3d');
                                    }}
                                    style={{
                                        background: 'transparent', border: 'none', color: '#263238',
                                        borderRadius: 3, padding: 6, cursor: 'pointer', display: 'flex'
                                    }}
                                    title="Frame Extents"
                                >
                                    <IconSection size={14} />
                                </button>
                            </div>

                            {/* Right Floating Navigation Controls */}
                            <div style={{
                                position: 'absolute', top: 94, right: 378, zIndex: 60,
                                display: 'flex', flexDirection: 'column', gap: 5,
                                alignItems: 'center', pointerEvents: 'auto'
                            }}>
                                <button
                                    onClick={() => {
                                        if (twinRef.current) twinRef.current.alignNorth();
                                    }}
                                    style={{
                                        width: 30, height: 30, borderRadius: '50%',
                                        background: '#ffffff', border: '1px solid #D5DCE3',
                                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                                        cursor: 'pointer', boxShadow: '0 1px 3px rgba(0,0,0,0.06)'
                                    }}
                                    title="North Indicator"
                                >
                                    <IconCompassRose size={15} />
                                </button>

                                <button
                                    onClick={() => {
                                        if (twinRef.current) twinRef.current.zoom(0.85);
                                    }}
                                    style={{
                                        width: 26, height: 26, borderRadius: 4,
                                        background: '#ffffff', border: '1px solid #D5DCE3',
                                        color: '#263238', fontSize: 13, fontWeight: 600, display: 'flex', alignItems: 'center', justifyContent: 'center',
                                        cursor: 'pointer', boxShadow: '0 1px 2px rgba(0,0,0,0.04)'
                                    }}
                                    title="Zoom In"
                                >
                                    +
                                </button>

                                <button
                                    onClick={() => {
                                        if (twinRef.current) twinRef.current.zoom(1.15);
                                    }}
                                    style={{
                                        width: 26, height: 26, borderRadius: 4,
                                        background: '#ffffff', border: '1px solid #D5DCE3',
                                        color: '#263238', fontSize: 13, fontWeight: 600, display: 'flex', alignItems: 'center', justifyContent: 'center',
                                        cursor: 'pointer', boxShadow: '0 1px 2px rgba(0,0,0,0.04)'
                                    }}
                                    title="Zoom Out"
                                >
                                    -
                                </button>

                                <button
                                    onClick={() => {
                                        if (twinRef.current) twinRef.current.setCameraPreset('plan');
                                    }}
                                    style={{
                                        width: 26, height: 26, borderRadius: 4,
                                        background: '#ffffff', border: '1px solid #D5DCE3',
                                        color: '#263238', display: 'flex', alignItems: 'center', justifyContent: 'center',
                                        cursor: 'pointer', boxShadow: '0 1px 2px rgba(0,0,0,0.04)'
                                    }}
                                    title="Toggle Perspective (2D/3D)"
                                >
                                    <IconPerspective size={13} />
                                </button>
                            </div>

                            {/* Floating Bottom HUD Inside Viewport */}
                            <div style={{
                                position: 'absolute', bottom: 80, left: 298, zIndex: 60,
                                pointerEvents: 'none', display: 'flex', alignItems: 'center', gap: 8
                            }}>
                                <div style={{
                                    background: 'rgba(255, 255, 255, 0.94)', border: '1px solid #D5DCE3',
                                    borderRadius: 4, padding: '3px 8px', display: 'flex', flexDirection: 'column', gap: 2,
                                    boxShadow: '0 1px 3px rgba(0,0,0,0.04)'
                                }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9.5, color: '#263238', width: 110, fontWeight: 500 }}>
                                        <span>0</span>
                                        <span>10</span>
                                        <span>20</span>
                                        <span>30 m</span>
                                    </div>
                                    <div style={{ height: 2, width: 110, background: '#263238', borderRadius: 1 }} />
                                </div>
                            </div>

                            <div style={{
                                position: 'absolute', bottom: 80, right: 378, zIndex: 60,
                                pointerEvents: 'none', display: 'flex', gap: 6
                            }}>
                                <div style={{
                                    background: 'rgba(255, 255, 255, 0.94)', border: '1px solid #D5DCE3',
                                    borderRadius: 4, padding: '4px 8px', fontSize: 10.5, color: '#263238', fontWeight: 600,
                                    boxShadow: '0 1px 3px rgba(0,0,0,0.04)'
                                }}>
                                    Elevation: {selectedFlat ? `+${selectedFlat.elevation_base_m} m` : '+19.44 m'}
                                </div>
                                <div style={{
                                    background: 'rgba(255, 255, 255, 0.94)', border: '1px solid #D5DCE3',
                                    borderRadius: 4, padding: '4px 8px', fontSize: 10.5, color: '#263238', fontWeight: 600,
                                    boxShadow: '0 1px 3px rgba(0,0,0,0.04)'
                                }}>
                                    Coordinates: 18.9256° N, 72.8247° E
                                </div>
                            </div>

                            {/* 5. Floating Bottom Toolbar Underneath 3D Viewport */}
                            <div style={{
                                position: 'absolute', bottom: 30, left: 298, right: 378, height: 40,
                                background: '#ffffff', border: '1px solid #D5DCE3', borderRadius: 5,
                                boxShadow: '0 1px 3px rgba(0,0,0,0.04)', display: 'flex', alignItems: 'center',
                                justifyContent: 'space-between', padding: '0 14px', zIndex: 60, pointerEvents: 'auto'
                            }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1, maxWidth: 360 }}>
                                    <span style={{ fontSize: 11, fontWeight: 600, color: '#263238', whiteSpace: 'nowrap' }}>
                                        Explode Floors
                                    </span>
                                    <span style={{ fontSize: 10, color: '#66717A' }}>0%</span>
                                    <input
                                        type="range"
                                        min="0"
                                        max="1"
                                        step="0.01"
                                        value={explodeRatio}
                                        onChange={(e) => handleExplodeChange(e.target.value)}
                                        style={{ flex: 1 }}
                                    />
                                    <span style={{ fontSize: 10, color: '#66717A' }}>100%</span>
                                </div>

                                <div style={{ display: 'flex', gap: 6, marginLeft: 14 }}>
                                    <button
                                        onClick={() => handleExplodeChange(0)}
                                        style={{
                                            background: explodeRatio === 0 ? '#E8F1FA' : '#ffffff',
                                            border: explodeRatio === 0 ? '1px solid #C4DCF2' : '1px solid #D5DCE3',
                                            color: explodeRatio === 0 ? '#2563A6' : '#263238',
                                            borderRadius: 4, padding: '4px 10px', fontSize: 11, fontWeight: explodeRatio === 0 ? 600 : 500,
                                            cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5
                                        }}
                                    >
                                        <IconLayers size={11} />
                                        <span>Stack</span>
                                    </button>
                                    <button
                                        onClick={() => handleExplodeChange(0.5)}
                                        style={{
                                            background: Math.abs(explodeRatio - 0.5) < 0.08 ? '#E8F1FA' : '#ffffff',
                                            border: Math.abs(explodeRatio - 0.5) < 0.08 ? '1px solid #C4DCF2' : '1px solid #D5DCE3',
                                            color: Math.abs(explodeRatio - 0.5) < 0.08 ? '#2563A6' : '#263238',
                                            borderRadius: 4, padding: '4px 10px', fontSize: 11, fontWeight: Math.abs(explodeRatio - 0.5) < 0.08 ? 600 : 500,
                                            cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5
                                        }}
                                    >
                                        <IconOrbit size={11} />
                                        <span>Inspect</span>
                                    </button>
                                    <button
                                        onClick={() => handleExplodeChange(1.0)}
                                        style={{
                                            background: explodeRatio >= 0.95 ? '#E8F1FA' : '#ffffff',
                                            border: explodeRatio >= 0.95 ? '1px solid #C4DCF2' : '1px solid #D5DCE3',
                                            color: explodeRatio >= 0.95 ? '#2563A6' : '#263238',
                                            borderRadius: 4, padding: '4px 10px', fontSize: 11, fontWeight: explodeRatio >= 0.95 ? 600 : 500,
                                            cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5
                                        }}
                                    >
                                        <IconExplode size={11} />
                                        <span>Explode</span>
                                    </button>
                                </div>
                            </div>

                            {/* 6. Right Sidebar: Property Information Card, Tabs & Cadastre */}
                            <div style={{
                                position: 'absolute', top: 92, right: 14, bottom: 32, width: 350,
                                background: '#ffffff', border: '1px solid #D5DCE3', borderRadius: 5,
                                boxShadow: '0 1px 3px rgba(0,0,0,0.04)', display: 'flex', flexDirection: 'column',
                                zIndex: 60, pointerEvents: 'auto', overflow: 'hidden'
                            }}>
                                <div style={{
                                    padding: '9px 12px', borderBottom: '1px solid #E8ECEF',
                                    display: 'flex', alignItems: 'center', justifyContent: 'space-between'
                                }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 12, fontWeight: 700, color: '#263238' }}>
                                        <IconDoc size={13} color="#2563A6" />
                                        <span>Property Information</span>
                                    </div>
                                    <button style={{ background: 'none', border: 'none', color: '#66717A', cursor: 'pointer', fontSize: 13 }}>
                                        <IconMore size={13} />
                                    </button>
                                </div>

                                <div style={{ padding: '10px 12px', display: 'flex', gap: 10, alignItems: 'center', borderBottom: '1px solid #E8ECEF' }}>
                                    <div style={{
                                        width: 44, height: 44, borderRadius: 4, background: '#20364A',
                                        display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden', flexShrink: 0
                                    }}>
                                        <IconThumbnail />
                                    </div>
                                    <div style={{ flex: 1, minWidth: 0 }}>
                                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                                            <div style={{ fontSize: 9.5, fontWeight: 700, color: '#66717A', textTransform: 'uppercase' }}>
                                                ULPIN
                                            </div>
                                            <span style={{
                                                fontSize: 9.5, fontWeight: 700, color: '#1F8A4C', background: '#EBF7EE',
                                                border: '1px solid #C6E7D0', padding: '1px 6px', borderRadius: 3
                                            }}>
                                                Active
                                            </span>
                                        </div>
                                        <div className="code-font" style={{ fontSize: 11, fontWeight: 600, color: '#263238', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', marginTop: 2 }}>
                                            {selectedFlat ? selectedFlat.unit_ulpin : (cadastre.land_ulpin || '27019017369979-WB-FL05-U504')}
                                        </div>
                                    </div>
                                </div>

                                <div style={{ display: 'flex', borderBottom: '1px solid #D5DCE3', padding: '0 12px', background: '#F8FAFC' }}>
                                    {[
                                        { id: 'overview', label: 'Overview' },
                                        { id: 'floors', label: 'Floors' },
                                        { id: 'infrastructure', label: 'Infrastructure' },
                                        { id: 'documents', label: 'Documents' }
                                    ].map(t => {
                                        const isActive = (activeTab === t.id);
                                        return (
                                            <button
                                                key={t.id}
                                                onClick={() => setActiveTab(t.id)}
                                                style={{
                                                    background: 'none', border: 'none', padding: '7px 8px',
                                                    fontSize: 11, fontWeight: isActive ? 600 : 500,
                                                    color: isActive ? '#2563A6' : '#66717A',
                                                    borderBottom: isActive ? '2px solid #2563A6' : '2px solid transparent',
                                                    cursor: 'pointer', transition: 'all 0.1s'
                                                }}
                                            >
                                                {t.label}
                                            </button>
                                        );
                                    })}
                                </div>

                                <div style={{ flex: 1, overflowY: 'auto', padding: '10px 12px' }}>
                                    {activeTab === 'overview' && (
                                        <React.Fragment>
                                            <div style={{ marginBottom: 12 }}>
                                                <div style={{ fontSize: 10, fontWeight: 700, color: '#263238', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 5, paddingBottom: 2, borderBottom: '1px solid #F1F4F7' }}>
                                                    Basic Details
                                                </div>
                                                <div style={{ display: 'flex', flexDirection: 'column', gap: 3.5, fontSize: 10.5 }}>
                                                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                                        <span style={{ color: '#66717A' }}>Property ID</span>
                                                        <span className="code-font" style={{ color: '#263238', fontWeight: 600 }}>{cadastre.land_ulpin ? cadastre.land_ulpin.slice(-14) : '27019017369979'}</span>
                                                    </div>
                                                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                                        <span style={{ color: '#66717A' }}>Parcel ID</span>
                                                        <span className="code-font" style={{ color: '#263238', fontWeight: 600 }}>{cadastre.land_ulpin || '27019017369979'}</span>
                                                    </div>
                                                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                                        <span style={{ color: '#66717A' }}>Building Name</span>
                                                        <span style={{ color: '#263238', fontWeight: 600 }}>{cadastre.name || '—'}</span>
                                                    </div>
                                                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                                        <span style={{ color: '#66717A' }}>Floor</span>
                                                        <span style={{ color: '#263238', fontWeight: 600 }}>{selectedFlat ? selectedFlat.floor_number : (selectedFloor !== null ? selectedFloor + 1 : '5')}</span>
                                                    </div>
                                                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                                        <span style={{ color: '#66717A' }}>Unit / Flat</span>
                                                        <span style={{ color: '#263238', fontWeight: 600 }}>{selectedFlat ? selectedFlat.unit_number : '504'}</span>
                                                    </div>
                                                </div>
                                            </div>

                                            <div style={{ marginBottom: 12 }}>
                                                <div style={{ fontSize: 10, fontWeight: 700, color: '#263238', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 5, paddingBottom: 2, borderBottom: '1px solid #F1F4F7' }}>
                                                    Area Details
                                                </div>
                                                <div style={{ display: 'flex', flexDirection: 'column', gap: 3.5, fontSize: 10.5 }}>
                                                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                                        <span style={{ color: '#66717A' }}>Carpet Area</span>
                                                        <span style={{ color: '#263238', fontWeight: 600 }}>{selectedFlat ? `${selectedFlat.carpet_area_sqm} m²` : '296.57 m²'}</span>
                                                    </div>
                                                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                                        <span style={{ color: '#66717A' }}>Built-up Area</span>
                                                        <span style={{ color: '#263238', fontWeight: 600 }}>{selectedFlat ? `${selectedFlat.built_up_area_sqm} m²` : '370.71 m²'}</span>
                                                    </div>
                                                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                                        <span style={{ color: '#66717A' }}>Land Share</span>
                                                        <span style={{ color: '#263238', fontWeight: 600 }}>{selectedFlat ? selectedFlat.uds_percentage : '3.57%'}</span>
                                                    </div>
                                                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                                        <span style={{ color: '#66717A' }}>Elevation (MSL)</span>
                                                        <span style={{ color: '#263238', fontWeight: 600 }}>{selectedFlat ? `+${selectedFlat.elevation_base_m} m` : '+19.44 m'}</span>
                                                    </div>
                                                </div>
                                            </div>

                                            <div style={{ marginBottom: 12 }}>
                                                <div style={{ fontSize: 10, fontWeight: 700, color: '#263238', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 5, paddingBottom: 2, borderBottom: '1px solid #F1F4F7' }}>
                                                    Cadastral & Ownership
                                                </div>
                                                <div style={{ display: 'flex', flexDirection: 'column', gap: 3.5, fontSize: 10.5 }}>
                                                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                                        <span style={{ color: '#66717A' }}>Titleholder</span>
                                                        <span style={{ color: '#263238', fontWeight: 600, textAlign: 'right', maxWidth: 190 }}>
                                                            {selectedFlat ? selectedFlat.owner_name : 'Smt. Sunita Kapoor & Shri Devendra Kapoor'}
                                                        </span>
                                                    </div>
                                                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                                        <span style={{ color: '#66717A' }}>CTS Survey No.</span>
                                                        <span style={{ color: '#263238', fontWeight: 600 }}>CTS No. {cadastre.cts_no || '175/D'}, {cadastre.cadastral_division ? cadastre.cadastral_division.replace(' Division', '') : 'Nariman Point'}</span>
                                                    </div>
                                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                                        <span style={{ color: '#66717A' }}>Title Status</span>
                                                        <span style={{ fontSize: 9.5, fontWeight: 700, color: '#1F8A4C', background: '#EBF7EE', border: '1px solid #C6E7D0', padding: '1px 5px', borderRadius: 3 }}>
                                                            Freehold
                                                        </span>
                                                    </div>
                                                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                                        <span style={{ color: '#66717A' }}>Clear Title</span>
                                                        <span style={{ color: '#263238', fontWeight: 600 }}>Yes</span>
                                                    </div>
                                                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                                        <span style={{ color: '#66717A' }}>Registered</span>
                                                        <span style={{ color: '#263238', fontWeight: 600 }}>Yes</span>
                                                    </div>
                                                </div>
                                            </div>

                                            <div style={{ marginBottom: 12 }}>
                                                <div style={{ fontSize: 10, fontWeight: 700, color: '#263238', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 5, paddingBottom: 2, borderBottom: '1px solid #F1F4F7' }}>
                                                    Infrastructure (Connected)
                                                </div>
                                                <div style={{ display: 'flex', flexDirection: 'column', gap: 3.5, fontSize: 10.5 }}>
                                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                                        <span style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#66717A' }}>
                                                            <IconWater size={11} color="#2563A6" />
                                                            Water Supply
                                                        </span>
                                                        <span style={{ color: '#263238', fontWeight: 600 }}>Connected</span>
                                                    </div>
                                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                                        <span style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#66717A' }}>
                                                            <IconSewer size={11} color="#1F8A4C" />
                                                            Sewerage
                                                        </span>
                                                        <span style={{ color: '#263238', fontWeight: 600 }}>Connected</span>
                                                    </div>
                                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                                        <span style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#66717A' }}>
                                                            <IconPower size={11} color="#D97706" />
                                                            Electricity
                                                        </span>
                                                        <span style={{ color: '#263238', fontWeight: 600 }}>Connected</span>
                                                    </div>
                                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                                        <span style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#66717A' }}>
                                                            <IconRain size={11} color="#4F46E5" />
                                                            Stormwater
                                                        </span>
                                                        <span style={{ color: '#263238', fontWeight: 600 }}>Connected</span>
                                                    </div>
                                                </div>
                                            </div>

                                            <button
                                                onClick={() => {
                                                    const spatialId = selectedBuilding && selectedBuilding.properties
                                                        ? selectedBuilding.properties.spatial_id
                                                        : '';
                                                    const unitId = selectedFlat ? selectedFlat.unit_id : '';
                                                    if (spatialId) {
                                                        window.open(`/api/building/${encodeURIComponent(spatialId)}/document?unit_id=${encodeURIComponent(unitId)}`, '_blank');
                                                    }
                                                }}
                                                style={{
                                                    width: '100%', background: '#2563A6', border: 'none',
                                                    color: '#ffffff', padding: '8px 12px', borderRadius: 4, fontWeight: 600,
                                                    fontSize: 11, cursor: 'pointer', display: 'flex', alignItems: 'center',
                                                    justifyContent: 'space-between', transition: 'background 0.12s', marginTop: 8
                                                }}
                                            >
                                                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                                    <IconDoc size={12} color="#ffffff" />
                                                    <span>Open Ownership Document Preview</span>
                                                </div>
                                                <IconDownload size={12} color="#ffffff" />
                                            </button>
                                        </React.Fragment>
                                    )}

                                    {activeTab === 'floors' && (
                                        <div>
                                            <div style={{ fontSize: 10, fontWeight: 700, color: '#263238', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 6 }}>
                                                Storey Hierarchy ({cadastre.floors_count} Levels)
                                            </div>
                                            {cadastre.floors.slice().reverse().map(fl => (
                                                <div
                                                    key={fl.floor_index}
                                                    onClick={() => handleTreeFloorClick(fl.floor_index)}
                                                    style={{
                                                        padding: '6px 8px', borderRadius: 4, marginBottom: 3, cursor: 'pointer',
                                                        background: selectedFloor === fl.floor_index ? '#E8F1FA' : '#F8FAFC',
                                                        border: selectedFloor === fl.floor_index ? '1px solid #C4DCF2' : '1px solid #E8ECEF',
                                                        display: 'flex', justifyContent: 'space-between', alignItems: 'center'
                                                    }}
                                                >
                                                    <span style={{ fontSize: 11, fontWeight: 600, color: '#263238' }}>{fl.floor_label}</span>
                                                    <span style={{ fontSize: 10, color: '#66717A' }}>+{fl.elevation_base_m}m • {fl.units_count} Units</span>
                                                </div>
                                            ))}
                                        </div>
                                    )}

                                    {activeTab === 'infrastructure' && (
                                        <div>
                                            <div style={{ fontSize: 10, fontWeight: 700, color: '#263238', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 6 }}>
                                                Municipal Utility Subterranean Laterals
                                            </div>
                                            {[
                                                { name: 'Potable Water Main', dept: 'MCGM Hydraulic Dept', depth: '3.8m', dia: '1200mm' },
                                                { name: 'Sewer Interceptor', dept: 'MCGM Sewerage Operations', depth: '5.5m', dia: '1500mm' },
                                                { name: 'Electrical 11kV Feeder', dept: 'BEST Undertaking', depth: '1.8m', dia: 'Vault' },
                                                { name: 'Optical Telecom Conduit', dept: 'MTNL / BMC Digital', depth: '1.2m', dia: 'Duct' }
                                            ].map((it, idx) => (
                                                <div key={idx} style={{ padding: '6px 8px', borderRadius: 4, marginBottom: 4, background: '#F8FAFC', border: '1px solid #E8ECEF' }}>
                                                    <div style={{ fontSize: 11, fontWeight: 600, color: '#263238' }}>{it.name}</div>
                                                    <div style={{ fontSize: 10, color: '#66717A', marginTop: 2 }}>{it.dept} • Depth: {it.depth}</div>
                                                </div>
                                            ))}
                                        </div>
                                    )}

                                    {activeTab === 'documents' && (
                                        <div>
                                            <div style={{ fontSize: 10, fontWeight: 700, color: '#263238', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 6 }}>
                                                Cadastral Registry Documents
                                            </div>
                                            {[
                                                { title: 'MahaBhumi 7/12 Extract', no: 'REV-MH-2024-8819', type: 'Verified Record of Rights' },
                                                { title: 'CTS Property Card (PR Card)', no: `CTS-${cadastre.cts_no}`, type: 'Municipal Survey Cadastre' },
                                                { title: 'Index II Registration Deed', no: 'DOC-REG-44910', type: 'Freehold Title Deed' },
                                                { title: 'Building Completion Certificate', no: 'BCC-MCGM-A-2023', type: 'Municipal NOC' }
                                            ].map((doc, idx) => (
                                                <div key={idx} style={{ padding: '6px 8px', borderRadius: 4, marginBottom: 4, background: '#F8FAFC', border: '1px solid #E8ECEF', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                                    <div>
                                                        <div style={{ fontSize: 11, fontWeight: 600, color: '#263238' }}>{doc.title}</div>
                                                        <div style={{ fontSize: 9.5, color: '#66717A', marginTop: 1 }}>{doc.no} • {doc.type}</div>
                                                    </div>
                                                    <IconDownload size={12} color="#2563A6" />
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            </div>

                            {/* 7. Full-width Bottom Status Footer */}
                            <div style={{
                                position: 'absolute', bottom: 0, left: 0, right: 0, height: 24,
                                background: '#F4F6F8', borderTop: '1px solid #D5DCE3',
                                padding: '0 16px', display: 'flex', alignItems: 'center',
                                justifyContent: 'space-between', zIndex: 65, pointerEvents: 'auto'
                            }}>
                                <div style={{ fontSize: 10, color: '#66717A', fontWeight: 500 }}>
                                    3D ULPIN v1.0 | Government of Maharashtra (Prototype)
                                </div>
                                <div style={{ fontSize: 10, color: '#66717A', fontWeight: 500 }}>
                                    Data Source: Municipal Records | CRS: WGS-84 | Scale 1:500
                                </div>
                            </div>
                        </React.Fragment>
                    )}
                </div>
            );
        }

        ReactDOM.render(<App />, document.getElementById('react-root'));
    </script>
</body>
</html>
"""
    html_content = html_content.replace("__GOOGLE_3D_TILES_API_KEY__", google_key_literal)
    return HTMLResponse(content=html_content)

if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)