import json
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
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
            background: #0f172a; border: 1px solid var(--border-medium);
            border-radius: 6px; padding: 8px 12px; font-size: 11px;
            box-shadow: var(--shadow-panel);
            transform: translate(-50%, -120%); transition: opacity 0.15s;
        }

        #twin-workspace {
            position: absolute; top: 0; left: 0; width: 100vw; height: 100vh;
            background: #090d16;
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
                <div id="tt-title" style="font-weight: 700; color: var(--accent-cyan); margin-bottom: 2px;"></div>
                <div id="tt-sub" style="color: var(--text-secondary);"></div>
                <div id="tt-ulpin" class="code-font" style="color: var(--accent-amber); font-size: 10px; margin-top: 4px;"></div>
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
                        color: 0xffffff, roughness: 0.65, metalness: 0.15
                    }),
                    slabEdge: new THREE.MeshStandardMaterial({
                        color: 0xffffff, roughness: 0.5, metalness: 0.2
                    }),
                    roofSlate: new THREE.MeshStandardMaterial({
                        color: 0x7b92b1, roughness: 0.65, metalness: 0.25
                    }),
                    exteriorStone: new THREE.MeshStandardMaterial({
                        color: 0x161f2e, roughness: 0.75, metalness: 0.25
                    }),
                    exteriorAccent: new THREE.MeshStandardMaterial({
                        color: 0x1e293b, roughness: 0.6, metalness: 0.35
                    }),
                    windowGlass: new THREE.MeshPhysicalMaterial({
                        color: 0x38bdf8, roughness: 0.08, transmission: 0.82, opacity: 0.75,
                        transparent: true, reflectivity: 0.92, clearcoat: 1.0, clearcoatRoughness: 0.1
                    }),
                    windowGlassWarm: new THREE.MeshPhysicalMaterial({
                        color: 0x0284c7, roughness: 0.12, transmission: 0.78, opacity: 0.8,
                        transparent: true, reflectivity: 0.88, clearcoat: 1.0
                    }),
                    aluminumFrame: new THREE.MeshStandardMaterial({
                        color: 0x0f172a, roughness: 0.4, metalness: 0.85
                    }),
                    balconyDeck: new THREE.MeshStandardMaterial({
                        color: 0x475569, roughness: 0.85, metalness: 0.1
                    }),
                    balconyGlassRailing: new THREE.MeshPhysicalMaterial({
                        color: 0x38bdf8, roughness: 0.15, transmission: 0.9, opacity: 0.5,
                        transparent: true, reflectivity: 0.85
                    }),
                    metalRailing: new THREE.MeshStandardMaterial({
                        color: 0x94a3b8, roughness: 0.35, metalness: 0.9
                    }),
                    entranceDoor: new THREE.MeshPhysicalMaterial({
                        color: 0x0284c7, roughness: 0.1, transmission: 0.9, opacity: 0.85,
                        transparent: true
                    }),
                    roofHVAC: new THREE.MeshStandardMaterial({
                        color: 0x4b5563, roughness: 0.65, metalness: 0.7
                    }),
                    flatFloorSelected: new THREE.MeshStandardMaterial({
                        color: 0x2563eb, emissive: 0x1d4ed8, emissiveIntensity: 0.35,
                        roughness: 0.3, metalness: 0.2
                    }),
                    ghostedMaterial: new THREE.MeshPhysicalMaterial({
                        color: 0x0f172a, roughness: 0.2, transmission: 0.85, opacity: 0.18,
                        transparent: true, reflectivity: 0.7
                    })
                };
            }

            init() {
                const w = this.container.clientWidth || window.innerWidth;
                const h = this.container.clientHeight || window.innerHeight;

                this.scene = new THREE.Scene();
                this.scene.background = new THREE.Color(0x090d16);

                this.camera = new THREE.PerspectiveCamera(42, w / h, 0.5, 3000);

                this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
                this.renderer.setSize(w, h);
                this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
                this.renderer.shadowMap.enabled = true;
                this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
                this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
                this.renderer.toneMappingExposure = 1.15;
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
                const ambient = new THREE.AmbientLight(0xffffff, 0.9);
                this.scene.add(ambient);

                const hemiLight = new THREE.HemisphereLight(0xf1f5f9, 0x0f172a, 0.85);
                hemiLight.position.set(0, 200, 0);
                this.scene.add(hemiLight);

                const sun = new THREE.DirectionalLight(0xfffbeb, 1.8);
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

                const rimLight = new THREE.DirectionalLight(0x94a3b8, 0.65);
                rimLight.position.set(-140, 90, -140);
                this.scene.add(rimLight);
            }

            setupGround() {
                const gridHelper = new THREE.GridHelper(260, 52, 0x475569, 0x1e293b);
                gridHelper.position.y = -0.05;
                gridHelper.material.opacity = 0.5;
                gridHelper.material.transparent = true;
                this.scene.add(gridHelper);

                const groundGeo = new THREE.PlaneGeometry(360, 360);
                const groundMat = new THREE.MeshStandardMaterial({
                    color: 0x090d16, roughness: 0.95, metalness: 0.05
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
                this.floorGroups = [];
                this.flatMeshes = [];
                this.allInteractiveMeshes = [];
                this.selectedFlatId = null;
                this.selectedFloorIndex = null;
                this.explodeRatio = 0.0;
                this.targetExplodeRatio = 0.0;
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

                this.buildArchitecturalFloors(centeredShape, centeredPoints, cadastre, floorHeight, size);
                this.buildGroundEntrance(size, floorHeight);
                this.buildRooftopCrown(centeredShape, floors * floorHeight, size);
                this.resetCameraToFraming(maxDim, p.height_m || 50);
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
                        color: 0x94a3b8, transparent: true, opacity: 0.35
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

                        const wallGeom = new THREE.ExtrudeGeometry(flatShape, { depth: hWall, bevelEnabled: false });
                        wallGeom.rotateX(-Math.PI / 2);
                        const wallMesh = new THREE.Mesh(wallGeom, this.materials.exteriorStone.clone());
                        wallMesh.castShadow = true;
                        wallMesh.receiveShadow = true;
                        wallMesh.userData = { isFlatClickable: true, unitId: unit.unit_id, unitData: unit };
                        flatGroup.add(wallMesh);

                        const glassInsetShape = this.createInsetShape(flatShape, 0.35);
                        if (glassInsetShape) {
                            const glassGeom = new THREE.ExtrudeGeometry(glassInsetShape, { depth: hWall * 0.82, bevelEnabled: false });
                            glassGeom.rotateX(-Math.PI / 2);
                            const glassMat = (uIdx % 2 === 0 ? this.materials.windowGlass : this.materials.windowGlassWarm).clone();
                            const glassMesh = new THREE.Mesh(glassGeom, glassMat);
                            glassMesh.position.y = hWall * 0.12;
                            glassMesh.userData = { isFlatClickable: true, unitId: unit.unit_id, unitData: unit };
                            flatGroup.add(glassMesh);

                            const frameEdges = new THREE.EdgesGeometry(glassGeom);
                            const frameLine = new THREE.LineSegments(frameEdges, new THREE.LineBasicMaterial({
                                color: 0x94a3b8, transparent: true, opacity: 0.65
                            }));
                            frameLine.position.y = hWall * 0.12;
                            flatGroup.add(frameLine);
                        }

                        const balconyMesh = this.createBalcony(unit.quadrant, bboxSize, hWall);
                        if (balconyMesh) {
                            balconyMesh.userData = { isFlatClickable: true, unitId: unit.unit_id, unitData: unit };
                            flatGroup.add(balconyMesh);
                        }

                        const flatEdgeGeom = new THREE.EdgesGeometry(wallGeom, 30);
                        const flatOutline = new THREE.LineSegments(flatEdgeGeom, new THREE.LineBasicMaterial({
                            color: 0x3b82f6, transparent: true, opacity: 0.0, linewidth: 2
                        }));
                        flatGroup.add(flatOutline);

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
                const core = new THREE.Mesh(coreGeo, this.materials.exteriorStone);
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
                        fg.userData.wallMesh.material = this.materials.exteriorStone;
                        fg.userData.plateMesh.material = this.materials.exteriorAccent;
                        fg.userData.outline.material.opacity = 0.0;
                    } else if (isTarget) {
                        fg.userData.wallMesh.material = this.materials.flatFloorSelected;
                        fg.userData.plateMesh.material = this.materials.flatFloorSelected;
                        fg.userData.outline.material.opacity = 1.0;
                    } else {
                        fg.userData.wallMesh.material = this.materials.ghostedMaterial;
                        fg.userData.plateMesh.material = this.materials.ghostedMaterial;
                        fg.userData.outline.material.opacity = isSameFloor ? 0.35 : 0.08;
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
                                child.material = this.materials.exteriorStone;
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

                if (preset === 'iso') {
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
                }
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

            animate() {
                this.animId = requestAnimationFrame(this.animate);
                this.controls.update();
                this.updateExplodeAnimation();
                this.updateCameraTween();
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

                // Look up master feature from buildingsData to guarantee full polygon coordinates
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
                setViewMode('twin');

                const workspaceEl = document.getElementById('twin-workspace');
                if (workspaceEl) workspaceEl.style.display = 'flex';

                try {
                    const spId = bldFeat.properties.spatial_id;
                    const res = await fetch(`/api/building/${spId}/cadastre`);
                    if (!res.ok) throw new Error(`Cadastre API returned status ${res.status}`);
                    const cad = await res.json();
                    setCadastre(cad);

                    // Ensure renderer instance exists and loads the building
                    if (!twinRef.current) {
                        twinRef.current = new ArchitecturalDigitalTwinRenderer('twin-canvas-container');
                    }
                    setTimeout(() => {
                        if (twinRef.current) {
                            twinRef.current.onResize();
                            twinRef.current.loadBuilding(master, cad);
                        }
                    }, 60);
                } catch (err) {
                    console.error("Cadastre fetch failed for", spId, err);
                }
            };

            const handleCloseTwin = () => {
                setViewMode('map');
                document.getElementById('twin-workspace').style.display = 'none';
                if (twinRef.current) {
                    twinRef.current.clearBuilding();
                }
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
                            'fill-extrusion-color': '#00e5ff',
                            'fill-extrusion-opacity': 0.85
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
                    <div className="glass-panel" style={{
                        position: 'absolute', top: 16, left: 16, right: 16, height: 60,
                        padding: '0 18px', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                        zIndex: 60, pointerEvents: 'auto', background: '#0f172a', border: '1px solid var(--border-medium)'
                    }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                            <div style={{
                                width: 34, height: 34, borderRadius: 7, background: '#1e293b',
                                border: '1px solid rgba(255, 255, 255, 0.12)',
                                display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#3b82f6'
                            }}>
                                <IconEmblem />
                            </div>
                            <div>
                                <div style={{ fontWeight: 700, fontSize: 14.5, letterSpacing: '-0.01em', color: '#fff', display: 'flex', alignItems: 'center', gap: 8 }}>
                                    SOUTH MUMBAI 3D DIGITAL TWIN
                                    <span style={{ fontSize: 9.5, fontWeight: 700, padding: '2px 7px', borderRadius: 4, background: 'rgba(59, 130, 246, 0.12)', color: '#60a5fa', border: '1px solid rgba(59, 130, 246, 0.25)', letterSpacing: '0.04em' }}>
                                        BHU-AADHAAR CADASTRE
                                    </span>
                                </div>
                                <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 1 }}>
                                    {cadastre ? (
                                        <span>
                                            <b style={{ color: '#fff' }}>{cadastre.name}</b> • <span className="code-font" style={{ color: '#94a3b8' }}>{cadastre.land_ulpin}</span> • {cadastre.cts_no}
                                        </span>
                                    ) : "Department of Land Resources • 3D Cadastral Property Twin"}
                                </div>
                            </div>
                        </div>

                        <div style={{ position: 'relative', width: 320 }}>
                            <div style={{ position: 'absolute', left: 11, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-dim)', pointerEvents: 'none', display: 'flex' }}>
                                <IconSearch />
                            </div>
                            <input
                                type="text"
                                value={searchQuery}
                                onChange={(e) => handleSearch(e.target.value)}
                                placeholder="Search by ULPIN, Building or Street..."
                                style={{
                                    width: '100%', background: '#131b2e', border: '1px solid var(--border-subtle)',
                                    borderRadius: 6, padding: '7px 12px 7px 32px', color: '#fff', fontSize: 11.5, outline: 'none'
                                }}
                            />
                            {searchResults.length > 0 && (
                                <div className="glass-panel" style={{
                                    position: 'absolute', top: 38, left: 0, right: 0, maxHeight: 280, overflowY: 'auto',
                                    zIndex: 100, padding: 6, background: '#0f172a', border: '1px solid var(--border-medium)'
                                }}>
                                    {searchResults.map(b => (
                                        <div
                                            key={b.properties.spatial_id}
                                            onClick={() => {
                                                handleOpenTwin(b);
                                                setSearchResults([]);
                                                setSearchQuery('');
                                            }}
                                            style={{
                                                padding: '7px 9px', borderRadius: 5, cursor: 'pointer', fontSize: 11.5,
                                                marginBottom: 3, background: '#131b2e', transition: 'background 0.15s'
                                            }}
                                            onMouseEnter={(e) => e.currentTarget.style.background = '#1e293b'}
                                            onMouseLeave={(e) => e.currentTarget.style.background = '#131b2e'}
                                        >
                                            <div style={{ fontWeight: 600, color: '#60a5fa' }}>{b.properties.name}</div>
                                            <div style={{ fontSize: 10, color: 'var(--text-secondary)', marginTop: 2 }}>
                                                <span className="code-font">{b.properties.land_ulpin}</span> • {b.properties.street}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>

                        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                            {viewMode === 'twin' && (
                                <div style={{ display: 'flex', background: '#131b2e', borderRadius: 7, padding: 3, border: '1px solid var(--border-subtle)' }}>
                                    <button
                                        onClick={() => handleCameraPreset('iso')}
                                        style={{
                                            background: twinPreset === 'iso' ? '#2563eb' : 'transparent',
                                            color: twinPreset === 'iso' ? '#ffffff' : 'var(--text-secondary)',
                                            border: 'none', padding: '6px 12px', borderRadius: 5, fontSize: 11, fontWeight: 600,
                                            cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, transition: 'all 0.15s'
                                        }}
                                    >
                                        <IconIsometric />
                                        <span>3D Isometric</span>
                                    </button>
                                    <button
                                        onClick={() => handleCameraPreset('elevation')}
                                        style={{
                                            background: twinPreset === 'elevation' ? '#2563eb' : 'transparent',
                                            color: twinPreset === 'elevation' ? '#ffffff' : 'var(--text-secondary)',
                                            border: 'none', padding: '6px 12px', borderRadius: 5, fontSize: 11, fontWeight: 600,
                                            cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, transition: 'all 0.15s'
                                        }}
                                    >
                                        <IconElevation />
                                        <span>Elevation</span>
                                    </button>
                                    <button
                                        onClick={() => handleCameraPreset('plan')}
                                        style={{
                                            background: twinPreset === 'plan' ? '#2563eb' : 'transparent',
                                            color: twinPreset === 'plan' ? '#ffffff' : 'var(--text-secondary)',
                                            border: 'none', padding: '6px 12px', borderRadius: 5, fontSize: 11, fontWeight: 600,
                                            cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, transition: 'all 0.15s'
                                        }}
                                    >
                                        <IconTopPlan />
                                        <span>Top Plan</span>
                                    </button>
                                </div>
                            )}

                            {viewMode === 'twin' ? (
                                <button
                                    onClick={handleCloseTwin}
                                    style={{
                                        background: 'rgba(255, 255, 255, 0.05)', color: '#cbd5e1', border: '1px solid var(--border-subtle)',
                                        padding: '7px 14px', borderRadius: 7, fontWeight: 600, fontSize: 11.5, cursor: 'pointer',
                                        display: 'flex', alignItems: 'center', gap: 6, transition: 'all 0.15s'
                                    }}
                                    onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(255, 255, 255, 0.1)'; e.currentTarget.style.color = '#fff'; }}
                                    onMouseLeave={(e) => { e.currentTarget.style.background = 'rgba(255, 255, 255, 0.05)'; e.currentTarget.style.color = '#cbd5e1'; }}
                                >
                                    <span>← Exit 3D Digital Twin</span>
                                </button>
                            ) : (
                                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                                    <button
                                        onClick={toggleStoreys}
                                        style={{
                                            background: showStoreys ? 'rgba(59, 130, 246, 0.15)' : '#131b2e',
                                            color: showStoreys ? '#60a5fa' : 'var(--text-dim)',
                                            border: `1px solid ${showStoreys ? 'rgba(59, 130, 246, 0.4)' : 'var(--border-subtle)'}`,
                                            padding: '6px 12px', borderRadius: 7, fontSize: 11, fontWeight: 600, cursor: 'pointer',
                                            display: 'flex', alignItems: 'center', gap: 6, transition: 'all 0.15s'
                                        }}
                                        title="Toggle 3D Multi-Storey Architecture"
                                    >
                                        <IconBuilding />
                                        <span>3D Storeys</span>
                                    </button>
                                    <button
                                        onClick={toggleOrbit}
                                        style={{
                                            background: isOrbiting ? '#2563eb' : '#131b2e',
                                            color: isOrbiting ? '#ffffff' : 'var(--text-secondary)',
                                            border: `1px solid ${isOrbiting ? '#3b82f6' : 'var(--border-subtle)'}`,
                                            padding: '6px 12px', borderRadius: 7, fontSize: 11, fontWeight: 600, cursor: 'pointer',
                                            display: 'flex', alignItems: 'center', gap: 6, transition: 'all 0.15s'
                                        }}
                                        title="Toggle Continuous 3D Aerial Orbit"
                                    >
                                        <IconOrbit />
                                        <span>{isOrbiting ? "Pause Orbit" : "3D Orbit"}</span>
                                    </button>
                                    <button
                                        onClick={handleToggleUnderground}
                                        style={{
                                            background: undergroundMode ? '#1e293b' : '#131b2e',
                                            color: undergroundMode ? '#38bdf8' : 'var(--text-secondary)',
                                            border: `1px solid ${undergroundMode ? '#38bdf8' : 'var(--border-subtle)'}`,
                                            padding: '6px 12px', borderRadius: 7, fontSize: 11, fontWeight: 600, cursor: 'pointer',
                                            display: 'flex', alignItems: 'center', gap: 6, transition: 'all 0.15s'
                                        }}
                                        title="Toggle Subsurface 3D Cutaway & Pipeline Network Filter"
                                    >
                                        <IconUnderground />
                                        <span>Underground 3D</span>
                                        {undergroundMode && <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#38bdf8' }} />}
                                    </button>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Keyboard 3D Navigation HUD */}
                    {viewMode === 'map' && (
                        <div style={{
                            position: 'absolute', bottom: 24, left: 24,
                            background: 'rgba(11, 18, 33, 0.88)', backdropFilter: 'blur(12px)',
                            WebkitBackdropFilter: 'blur(12px)',
                            border: '1px solid rgba(56, 189, 248, 0.25)', borderRadius: 8,
                            padding: '8px 14px', zIndex: 50, pointerEvents: 'auto',
                            display: 'flex', alignItems: 'center', gap: 12, fontSize: 11, color: '#94a3b8',
                            boxShadow: '0 8px 24px rgba(0,0,0,0.5)'
                        }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                                <span style={{ padding: '2px 6px', background: 'rgba(255,255,255,0.12)', borderRadius: 4, fontWeight: 800, color: '#fff' }}>W</span>
                                <span style={{ padding: '2px 6px', background: 'rgba(255,255,255,0.12)', borderRadius: 4, fontWeight: 800, color: '#fff' }}>S</span>
                                <span style={{ color: '#cbd5e1', fontSize: 10.5 }}>Move</span>
                            </div>
                            <div style={{ width: 1, height: 12, background: 'rgba(255,255,255,0.15)' }} />
                            <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                                <span style={{ padding: '2px 6px', background: 'rgba(0, 229, 255, 0.15)', color: 'var(--accent-cyan)', borderRadius: 4, fontWeight: 800 }}>A</span>
                                <span style={{ color: '#cbd5e1', fontSize: 10.5 }}>Right</span>
                                <span style={{ padding: '2px 6px', background: 'rgba(0, 229, 255, 0.15)', color: 'var(--accent-cyan)', borderRadius: 4, fontWeight: 800 }}>D</span>
                                <span style={{ color: '#cbd5e1', fontSize: 10.5 }}>Left</span>
                                <span style={{ color: '#cbd5e1', fontSize: 10.5 }}>360° Rotate</span>
                            </div>
                            <div style={{ width: 1, height: 12, background: 'rgba(255,255,255,0.15)' }} />
                            <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                                <span style={{ padding: '2px 6px', background: 'rgba(245, 158, 11, 0.15)', color: 'var(--accent-amber)', borderRadius: 4, fontWeight: 800 }}>R</span>
                                <span style={{ padding: '2px 6px', background: 'rgba(245, 158, 11, 0.15)', color: 'var(--accent-amber)', borderRadius: 4, fontWeight: 800 }}>F</span>
                                <span style={{ color: '#cbd5e1', fontSize: 10.5 }}>Angle</span>
                            </div>
                        </div>
                    )}

                    {/* Left-Hand 3D Integrated Pipe Network Analytical Panel */}
                    {viewMode === 'map' && undergroundMode && (
                        <div className="glass-panel" style={{
                            position: 'absolute', top: 88, left: 16, width: 330, maxHeight: 'calc(100vh - 120px)',
                            display: 'flex', flexDirection: 'column', padding: 16, zIndex: 60, pointerEvents: 'auto',
                            overflowY: 'auto', background: '#0f172a', border: '1px solid var(--border-medium)'
                        }}>
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                                <span style={{
                                    fontSize: 9, fontWeight: 700, padding: '2px 7px', borderRadius: 4,
                                    background: 'rgba(59, 130, 246, 0.12)', color: '#60a5fa', border: '1px solid rgba(59, 130, 246, 0.3)',
                                    letterSpacing: '0.04em'
                                }}>
                                    3D SUBTERRANEAN INFRASTRUCTURE
                                </span>
                                <span style={{ fontSize: 10, color: 'var(--accent-emerald)', display: 'flex', alignItems: 'center', gap: 4, fontWeight: 600 }}>
                                    <span className="pulsing-dot" style={{ width: 6, height: 6 }}></span> Active
                                </span>
                            </div>

                            <h3 style={{ margin: '0 0 2px 0', fontSize: 14.5, color: '#fff', fontWeight: 700 }}>
                                Subterranean 3D Cadastre
                            </h3>
                            <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 12, lineHeight: 1.4 }}>
                                Tunnels, Metro 3, subways, and utility infrastructure networks.
                            </div>

                            {/* Subterranean Category Filters */}
                            <div style={{ marginBottom: 12 }}>
                                <div style={{ fontSize: 9.5, fontWeight: 700, color: 'var(--text-dim)', textTransform: 'uppercase', marginBottom: 7, letterSpacing: '0.04em' }}>
                                    Subterranean Network Layers
                                </div>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                                    {[
                                        { id: 'all', label: 'All Subterranean Networks', color: '#38bdf8', count: '134 Assets' },
                                        { id: 'coastal_road_tunnel', label: 'Coastal Road Undersea Tunnel', color: '#38bdf8', count: 'Twin 12.2m Tubes' },
                                        { id: 'metro_underground', label: 'Metro 3 Aqua Line Railway', color: '#f43f5e', count: '8 Stations + Tunnels' },
                                        { id: 'vehicular_subway', label: 'Vehicular Roads & Underpasses', color: '#fb923c', count: '3 Road Tunnels' },
                                        { id: 'pedestrian_subway', label: 'Pedestrian Subway Networks', color: '#10b981', count: 'CSMT & Churchgate' },
                                        { id: 'water_supply', label: 'Potable Water Transmission', color: '#0284c7', count: '1800mm - 600mm' },
                                        { id: 'power_best', label: 'BEST 110kV / 33kV Grid', color: '#ef4444', count: 'High-Voltage Conduits' },
                                        { id: 'gas_mgl', label: 'MGL City Gas Pipeline', color: '#f59e0b', count: 'Steel & MDPE Grid' },
                                        { id: 'drainage_trunk', label: 'Deep Sewer & Storm Drainage', color: '#14b8a6', count: '2400mm Box Outfalls' },
                                        { id: 'telecom', label: 'Telecom Optical Fiber Banks', color: '#a855f7', count: '4-Way Duct Banks' }
                                    ].map(cat => {
                                        const isActive = (activeUtilityCat === cat.id);
                                        return (
                                            <div
                                                key={cat.id}
                                                onClick={() => handleUtilityCategoryChange(cat.id)}
                                                style={{
                                                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                                                    padding: '6px 9px', borderRadius: 5, cursor: 'pointer', fontSize: 11,
                                                    background: isActive ? 'rgba(59, 130, 246, 0.15)' : 'rgba(255, 255, 255, 0.03)',
                                                    border: isActive ? '1px solid #3b82f6' : '1px solid var(--border-subtle)',
                                                    transition: 'all 0.15s'
                                                }}
                                                onMouseEnter={(e) => { if (!isActive) e.currentTarget.style.background = 'rgba(255,255,255,0.06)'; }}
                                                onMouseLeave={(e) => { if (!isActive) e.currentTarget.style.background = isActive ? 'rgba(59, 130, 246, 0.15)' : 'rgba(255, 255, 255, 0.03)'; }}
                                            >
                                                <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                                                    <span style={{ width: 7, height: 7, borderRadius: '50%', background: cat.color }} />
                                                    <span style={{ fontWeight: isActive ? 600 : 400, color: isActive ? '#fff' : 'var(--text-secondary)' }}>
                                                        {cat.label}
                                                    </span>
                                                </div>
                                                <span className="code-font" style={{ fontSize: 9.5, color: 'var(--text-dim)' }}>
                                                    {cat.count}
                                                </span>
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>

                            {/* Subsurface Component Toggles */}
                            <div style={{
                                background: '#131b2e', borderRadius: 7, padding: 10,
                                border: '1px solid var(--border-subtle)', marginBottom: 12
                            }}>
                                <div style={{ fontSize: 9.5, fontWeight: 700, color: 'var(--text-dim)', textTransform: 'uppercase', marginBottom: 8, letterSpacing: '0.04em' }}>
                                    Cadastral Sub-Components
                                </div>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                                    <div
                                        onClick={handleToggleLaterals}
                                        style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer' }}
                                    >
                                        <div style={{ fontSize: 11, color: '#e2e8f0', display: 'flex', alignItems: 'center', gap: 6 }}>
                                            <span>Building Feeder Laterals (21 Basements)</span>
                                        </div>
                                        <div style={{
                                            width: 32, height: 18, borderRadius: 9, padding: 2,
                                            background: showLaterals ? '#2563eb' : 'rgba(255,255,255,0.15)',
                                            display: 'flex', alignItems: 'center', justifyContent: showLaterals ? 'flex-end' : 'flex-start',
                                            transition: 'background 0.2s'
                                        }}>
                                            <div style={{ width: 14, height: 14, borderRadius: '50%', background: '#fff' }} />
                                        </div>
                                    </div>
                                    <div
                                        onClick={handleToggleManholes}
                                        style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer' }}
                                    >
                                        <div style={{ fontSize: 11, color: '#e2e8f0', display: 'flex', alignItems: 'center', gap: 6 }}>
                                            <span>Shafts, Portals & Chambers (20 Nodes)</span>
                                        </div>
                                        <div style={{
                                            width: 32, height: 18, borderRadius: 9, padding: 2,
                                            background: showManholes ? '#2563eb' : 'rgba(255,255,255,0.15)',
                                            display: 'flex', alignItems: 'center', justifyContent: showManholes ? 'flex-end' : 'flex-start',
                                            transition: 'background 0.2s'
                                        }}>
                                            <div style={{ width: 14, height: 14, borderRadius: '50%', background: '#fff' }} />
                                        </div>
                                    </div>
                                </div>
                            </div>

                            {/* Subsurface Engineering Statistics */}
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginBottom: 12 }}>
                                <div style={{ background: '#131b2e', padding: 8, borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                                    <div style={{ fontSize: 9, color: 'var(--text-dim)', fontWeight: 600 }}>SPATIAL CLEARANCE</div>
                                    <div style={{ fontSize: 11.5, fontWeight: 700, color: 'var(--accent-emerald)', marginTop: 2 }}>
                                        0 Clashes (100%)
                                    </div>
                                </div>
                                <div style={{ background: '#131b2e', padding: 8, borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                                    <div style={{ fontSize: 9, color: 'var(--text-dim)', fontWeight: 600 }}>DEPTH RANGE</div>
                                    <div style={{ fontSize: 11.5, fontWeight: 700, color: '#38bdf8', marginTop: 2 }}>
                                        -1.0m to -70.0m
                                    </div>
                                </div>
                                <div style={{ background: '#131b2e', padding: 8, borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                                    <div style={{ fontSize: 9, color: 'var(--text-dim)', fontWeight: 600 }}>TOTAL ASSETS</div>
                                    <div style={{ fontSize: 11.5, fontWeight: 700, color: '#fff', marginTop: 2 }}>
                                        134 Features
                                    </div>
                                </div>
                                <div style={{ background: '#131b2e', padding: 8, borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                                    <div style={{ fontSize: 9, color: 'var(--text-dim)', fontWeight: 600 }}>METRO STATIONS</div>
                                    <div style={{ fontSize: 11.5, fontWeight: 700, color: 'var(--accent-amber)', marginTop: 2 }}>
                                        8 Aqua Boxes
                                    </div>
                                </div>
                            </div>

                            {/* Subsurface Depth Strata Guide */}
                            <div style={{
                                background: '#131b2e', borderRadius: 7, padding: 9,
                                border: '1px solid var(--border-subtle)', fontSize: 10
                            }}>
                                <div style={{ fontWeight: 700, color: 'var(--text-dim)', textTransform: 'uppercase', marginBottom: 6, letterSpacing: '0.04em' }}>
                                    Subterranean Depth Strata
                                </div>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: 3.5 }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', color: '#a855f7' }}>
                                        <span>• -1.0m to -1.2m</span>
                                        <span>Telecom Optical Ducts</span>
                                    </div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', color: '#ef4444' }}>
                                        <span>• -1.6m to -2.2m</span>
                                        <span>BEST 110kV/33kV Power Grid</span>
                                    </div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', color: '#f59e0b' }}>
                                        <span>• -2.1m to -2.5m</span>
                                        <span>MGL City Gas Steel Network</span>
                                    </div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', color: '#38bdf8' }}>
                                        <span>• -2.8m to -3.8m</span>
                                        <span>MCGM Potable Water Aqueducts</span>
                                    </div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', color: '#10b981' }}>
                                        <span>• -4.0m to -5.0m</span>
                                        <span>CSMT & Churchgate Subways</span>
                                    </div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', color: '#14b8a6' }}>
                                        <span>• -4.8m to -5.8m</span>
                                        <span>Deep Sewer & Storm Outfalls</span>
                                    </div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', color: '#fb923c' }}>
                                        <span>• -6.5m to -8.0m</span>
                                        <span>Vehicular Highway Underpasses</span>
                                    </div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', color: '#f43f5e' }}>
                                        <span>• -20.0m to -24.5m</span>
                                        <span>MMRC Metro 3 Aqua Line Stations</span>
                                    </div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', color: '#38bdf8' }}>
                                        <span>• -25.0m to -70.0m</span>
                                        <span>Coastal Road Undersea Tunnels</span>
                                    </div>
                                </div>
                            </div>

                            {/* Subterranean 360° View Quick Controls */}
                            <div style={{
                                background: '#131b2e', borderRadius: 7, padding: 9,
                                border: '1px solid var(--border-subtle)', marginTop: 10
                            }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                                    <span style={{ fontSize: 9, fontWeight: 700, color: 'var(--text-secondary)', letterSpacing: '0.04em' }}>
                                        360° VIEW & ROTATION
                                    </span>
                                    <span className="code-font" style={{ fontSize: 9.5, color: '#94a3b8' }}>
                                        {Math.round(((currentBearing % 360) + 360) % 360)}° {getCardinal(currentBearing)}
                                    </span>
                                </div>
                                <div style={{ display: 'flex', gap: 5, marginBottom: 5 }}>
                                    <button
                                        onClick={() => handleRotateStep(-45)}
                                        style={{
                                            flex: 1, padding: '5px 4px', background: 'rgba(255,255,255,0.05)',
                                            border: '1px solid var(--border-subtle)', color: '#fff', borderRadius: 4,
                                            fontSize: 10, fontWeight: 600, cursor: 'pointer'
                                        }}
                                    >
                                        -45°
                                    </button>
                                    <button
                                        onClick={toggleOrbit}
                                        style={{
                                            flex: 1.3, padding: '5px 4px',
                                            background: isOrbiting ? '#2563eb' : 'rgba(255,255,255,0.05)',
                                            border: `1px solid ${isOrbiting ? '#3b82f6' : 'var(--border-subtle)'}`,
                                            color: isOrbiting ? '#fff' : 'var(--text-secondary)',
                                            borderRadius: 4, fontSize: 10, fontWeight: 600, cursor: 'pointer'
                                        }}
                                    >
                                        {isOrbiting ? "Pause" : "360° Orbit"}
                                    </button>
                                    <button
                                        onClick={() => handleRotateStep(45)}
                                        style={{
                                            flex: 1, padding: '5px 4px', background: 'rgba(255,255,255,0.05)',
                                            border: '1px solid var(--border-subtle)', color: '#fff', borderRadius: 4,
                                            fontSize: 10, fontWeight: 600, cursor: 'pointer'
                                        }}
                                    >
                                        +45°
                                    </button>
                                </div>
                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 4 }}>
                                    {[
                                        { label: 'N', deg: 0 },
                                        { label: 'E', deg: 90 },
                                        { label: 'S', deg: 180 },
                                        { label: 'W', deg: 270 }
                                    ].map(dir => (
                                        <button
                                            key={dir.label}
                                            onClick={() => handleSetCardinalBearing(dir.deg)}
                                            style={{
                                                padding: '3px 2px', background: 'rgba(255,255,255,0.03)',
                                                border: '1px solid var(--border-subtle)', color: '#cbd5e1', borderRadius: 4,
                                                fontSize: 9.5, fontWeight: 600, cursor: 'pointer'
                                            }}
                                        >
                                            {dir.label}
                                        </button>
                                    ))}
                                </div>
                            </div>

                            <div style={{ fontSize: 10, color: 'var(--text-dim)', textAlign: 'center', marginTop: 8 }}>
                                Select any subterranean conduit or structure in 3D to inspect cadastral records.
                            </div>
                        </div>
                    )}

                    {/* Floating 360° Subterranean Orbit & Camera Control HUD */}
                    {viewMode === 'map' && undergroundMode && (
                        <div className="glass-panel" style={{
                            position: 'absolute', top: 96, right: 24, padding: '12px 16px', borderRadius: 12,
                            pointerEvents: 'auto', zIndex: 50, border: '1px solid rgba(0, 229, 255, 0.35)',
                            boxShadow: '0 16px 36px rgba(0,0,0,0.75)', width: 280
                        }}>
                            {/* Header with Heading Compass readout */}
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                    <span className="pulsing-dot" style={{ width: 6, height: 6, background: 'var(--accent-cyan)' }} />
                                    <span style={{ fontSize: 10, fontWeight: 800, color: 'var(--accent-cyan)', letterSpacing: '0.05em' }}>
                                        360° SUBTERRANEAN VIEW
                                    </span>
                                </div>
                                <span style={{
                                    fontSize: 10, fontWeight: 800, color: '#fff', background: 'rgba(15,23,42,0.8)',
                                    padding: '2px 7px', borderRadius: 6, border: '1px solid rgba(255,255,255,0.1)'
                                }}>
                                    🧭 {Math.round(((currentBearing % 360) + 360) % 360)}° {getCardinal(currentBearing)}
                                </span>
                            </div>

                            {/* Drag Mode Selector */}
                            <div style={{
                                display: 'flex', background: 'rgba(15,23,42,0.85)', borderRadius: 7, padding: 3,
                                border: '1px solid rgba(255,255,255,0.08)', marginBottom: 10
                            }}>
                                <button
                                    onClick={() => setUndergroundOrbitMode(true)}
                                    style={{
                                        flex: 1, padding: '5px 8px', borderRadius: 5, fontSize: 10.5, fontWeight: 700,
                                        border: 'none', cursor: 'pointer', transition: 'all 0.15s',
                                        background: undergroundOrbitMode ? 'var(--accent-cyan)' : 'transparent',
                                        color: undergroundOrbitMode ? '#000' : 'var(--text-dim)'
                                    }}
                                    title="Left-click drag anywhere to rotate 360° around the underground network"
                                >
                                    🔄 360° Drag Orbit
                                </button>
                                <button
                                    onClick={() => setUndergroundOrbitMode(false)}
                                    style={{
                                        flex: 1, padding: '5px 8px', borderRadius: 5, fontSize: 10.5, fontWeight: 700,
                                        border: 'none', cursor: 'pointer', transition: 'all 0.15s',
                                        background: !undergroundOrbitMode ? 'var(--accent-cyan)' : 'transparent',
                                        color: !undergroundOrbitMode ? '#000' : 'var(--text-dim)'
                                    }}
                                    title="Left-click drag to pan the map"
                                >
                                    🖐️ Pan Mode
                                </button>
                            </div>

                            {/* Quick Rotation Buttons */}
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.3fr 1fr', gap: 5, marginBottom: 8 }}>
                                <button
                                    onClick={() => handleRotateStep(-45)}
                                    style={{
                                        background: 'rgba(15,23,42,0.8)', border: '1px solid rgba(255,255,255,0.12)',
                                        color: '#fff', padding: '6px 4px', borderRadius: 6, fontSize: 10.5, fontWeight: 700,
                                        cursor: 'pointer'
                                    }}
                                    title="Turn 45° Counter-Clockwise"
                                >
                                    ↺ -45°
                                </button>
                                <button
                                    onClick={toggleOrbit}
                                    style={{
                                        background: isOrbiting ? 'linear-gradient(135deg, #00e5ff 0%, #3b82f6 100%)' : 'rgba(0,229,255,0.15)',
                                        border: '1px solid rgba(0,229,255,0.3)',
                                        color: isOrbiting ? '#000' : 'var(--accent-cyan)',
                                        padding: '6px 4px', borderRadius: 6, fontSize: 10.5, fontWeight: 800,
                                        cursor: 'pointer'
                                    }}
                                    title="Toggle continuous 360° auto-orbit"
                                >
                                    {isOrbiting ? "⏸️ Pause" : "🔄 Auto 360°"}
                                </button>
                                <button
                                    onClick={() => handleRotateStep(45)}
                                    style={{
                                        background: 'rgba(15,23,42,0.8)', border: '1px solid rgba(255,255,255,0.12)',
                                        color: '#fff', padding: '6px 4px', borderRadius: 6, fontSize: 10.5, fontWeight: 700,
                                        cursor: 'pointer'
                                    }}
                                    title="Turn 45° Clockwise"
                                >
                                    ↻ +45°
                                </button>
                            </div>

                            {/* Cardinal Directions 4-Grid */}
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 4, marginBottom: 8 }}>
                                {[
                                    { label: 'N (0°)', deg: 0 },
                                    { label: 'E (90°)', deg: 90 },
                                    { label: 'S (180°)', deg: 180 },
                                    { label: 'W (270°)', deg: 270 }
                                ].map(c => (
                                    <button
                                        key={c.label}
                                        onClick={() => handleSetCardinalBearing(c.deg)}
                                        style={{
                                            background: 'rgba(15,23,42,0.7)', border: '1px solid rgba(255,255,255,0.08)',
                                            color: '#cbd5e1', padding: '4px 0', borderRadius: 5, fontSize: 9.5, fontWeight: 700,
                                            cursor: 'pointer'
                                        }}
                                        title={`Orient view towards ${c.label}`}
                                    >
                                        {c.label.split(' ')[0]}
                                    </button>
                                ))}
                            </div>

                            {/* Pitch Angle Selector */}
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 4 }}>
                                <button
                                    onClick={() => handleSetPitchAngle(0)}
                                    style={{
                                        background: 'rgba(15,23,42,0.6)', border: '1px solid rgba(255,255,255,0.06)',
                                        color: '#94a3b8', padding: '4px 2px', borderRadius: 5, fontSize: 9.5, fontWeight: 600,
                                        cursor: 'pointer'
                                    }}
                                    title="Top-Down Plan View (0°)"
                                >
                                    Top (0°)
                                </button>
                                <button
                                    onClick={() => handleSetPitchAngle(58)}
                                    style={{
                                        background: 'rgba(15,23,42,0.6)', border: '1px solid rgba(255,255,255,0.06)',
                                        color: '#94a3b8', padding: '4px 2px', borderRadius: 5, fontSize: 9.5, fontWeight: 600,
                                        cursor: 'pointer'
                                    }}
                                    title="Isometric 3D Angle (58°)"
                                >
                                    3D (58°)
                                </button>
                                <button
                                    onClick={() => handleSetPitchAngle(78)}
                                    style={{
                                        background: 'rgba(15,23,42,0.6)', border: '1px solid rgba(255,255,255,0.06)',
                                        color: '#94a3b8', padding: '4px 2px', borderRadius: 5, fontSize: 9.5, fontWeight: 600,
                                        cursor: 'pointer'
                                    }}
                                    title="Deep Subterranean Horizon Angle (78°)"
                                >
                                    Deep (78°)
                                </button>
                            </div>

                            <div style={{ fontSize: 9, color: 'var(--text-dim)', textAlign: 'center', marginTop: 8, lineHeight: 1.25 }}>
                                Drag with left mouse, use A/D keys, or click above to orbit 360° freely.
                            </div>
                        </div>
                    )}

                    {/* Selected Subterranean Cadastre Card (Styled identically to 3D Building Card) */}
                    {viewMode === 'map' && selectedUtility && (
                        <div className="glass-panel" style={{
                            position: 'absolute', bottom: 30, right: 30, width: 390, padding: 22,
                            pointerEvents: 'auto', zIndex: 60, boxShadow: '0 20px 48px rgba(0,0,0,0.85)',
                            border: `1px solid ${selectedUtility.color || 'var(--accent-cyan)'}`
                        }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <span style={{
                                    fontSize: 10, fontWeight: 800, padding: '3px 9px', borderRadius: 20,
                                    background: selectedUtility.color || 'var(--accent-cyan)', color: '#000', letterSpacing: '0.04em'
                                }}>
                                    SUBTERRANEAN 3D CADASTRE
                                </span>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                    <button
                                        onClick={() => handleFlyToUtility(selectedUtility)}
                                        style={{
                                            background: 'rgba(0,229,255,0.15)', border: '1px solid rgba(0,229,255,0.4)',
                                            color: 'var(--accent-cyan)', padding: '3px 8px', borderRadius: 6,
                                            fontSize: 10.5, fontWeight: 700, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4
                                        }}
                                        title="Fly 3D Camera to Subterranean Conduit"
                                    >
                                        🎯 Focus
                                    </button>
                                    <button
                                        onClick={() => {
                                            setSelectedUtility(null);
                                            if (window.utilityPopup) window.utilityPopup.remove();
                                            if (window.mapInstance && window.mapInstance.getLayer('utilities-highlight')) {
                                                window.mapInstance.setFilter('utilities-highlight', ['==', 'utility_id', '']);
                                            }
                                        }}
                                        style={{ background: 'none', border: 'none', color: 'var(--text-dim)', cursor: 'pointer', fontSize: 16 }}
                                    >
                                        ✕
                                    </button>
                                </div>
                            </div>

                            <h3 style={{ margin: '12px 0 4px 0', fontSize: 17, color: '#fff', fontWeight: 800, lineHeight: 1.3 }}>
                                {selectedUtility.label}
                            </h3>
                            <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 14 }}>
                                {selectedUtility.corridor_name}
                            </div>

                            {/* 4-Grid Specifications (Matches Building Card Layout) */}
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 14 }}>
                                <div style={{ background: 'rgba(15,23,42,0.6)', padding: 8, borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                                    <div style={{ fontSize: 10, color: 'var(--text-dim)' }}>SUBTERRANEAN ULPIN</div>
                                    <div className="code-font" style={{ fontSize: 11.5, fontWeight: 700, color: 'var(--accent-amber)', wordBreak: 'break-all' }}>
                                        {selectedUtility.utility_ulpin}
                                    </div>
                                </div>
                                <div style={{ background: 'rgba(15,23,42,0.6)', padding: 8, borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                                    <div style={{ fontSize: 10, color: 'var(--text-dim)' }}>TOTAL BORE / DIAMETER</div>
                                    <div style={{ fontSize: 12, fontWeight: 700, color: selectedUtility.color || 'var(--accent-cyan)' }}>
                                        {selectedUtility.nominal_diameter_mm >= 1000
                                            ? `Ø ${(selectedUtility.nominal_diameter_mm / 1000).toFixed(1)}m (${selectedUtility.nominal_diameter_mm}mm)`
                                            : `Ø ${selectedUtility.nominal_diameter_mm} mm`}
                                    </div>
                                </div>
                                <div style={{ background: 'rgba(15,23,42,0.6)', padding: 8, borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                                    <div style={{ fontSize: 10, color: 'var(--text-dim)' }}>SUBTERRANEAN DEPTH</div>
                                    <div style={{ fontSize: 12, fontWeight: 700, color: '#38bdf8' }}>
                                        -{selectedUtility.depth_msl_m}m MSL (Bedrock)
                                    </div>
                                </div>
                                <div style={{ background: 'rgba(15,23,42,0.6)', padding: 8, borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                                    <div style={{ fontSize: 10, color: 'var(--text-dim)' }}>CLEARANCE STATUS</div>
                                    <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--accent-emerald)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                        {selectedUtility.clearance_status || "Operational RoW"}
                                    </div>
                                </div>
                            </div>

                            {/* Structural Specification & Authority Box */}
                            <div style={{ background: 'rgba(15,23,42,0.7)', borderRadius: 8, padding: 10, border: '1px solid var(--border-subtle)', marginBottom: 14, fontSize: 11 }}>
                                <div style={{ marginBottom: 4 }}>
                                    <span style={{ color: 'var(--text-dim)' }}>Structural Specification: </span>
                                    <b style={{ color: '#fff' }}>{selectedUtility.material}</b>
                                </div>
                                <div>
                                    <span style={{ color: 'var(--text-dim)' }}>Managing Authority: </span>
                                    <b style={{ color: 'var(--accent-cyan)' }}>{selectedUtility.authority}</b>
                                </div>
                                {selectedUtility.connected_building && (
                                    <div style={{ marginTop: 6, paddingTop: 6, borderTop: '1px solid rgba(255,255,255,0.08)' }}>
                                        <span style={{ color: 'var(--text-dim)' }}>Connected Landmark: </span>
                                        <b style={{ color: 'var(--accent-amber)' }}>{selectedUtility.connected_building}</b>
                                    </div>
                                )}
                            </div>

                            {/* Action Buttons */}
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                                <button
                                    onClick={() => handleFlyToUtility(selectedUtility)}
                                    style={{
                                        width: '100%', background: '#2563eb',
                                        color: '#fff', border: 'none', padding: '10px', borderRadius: 6, fontWeight: 600,
                                        fontSize: 12, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
                                        gap: 6, transition: 'background 0.15s'
                                    }}
                                    onMouseEnter={(e) => e.currentTarget.style.background = '#1d4ed8'}
                                    onMouseLeave={(e) => e.currentTarget.style.background = '#2563eb'}
                                >
                                    <span>Focus View on Subterranean Conduit</span>
                                </button>

                                {selectedUtility.building_spatial_id && (
                                    <button
                                        onClick={() => {
                                            const bld = buildingsData && buildingsData.features.find(b => b.properties.spatial_id === selectedUtility.building_spatial_id);
                                            if (bld) handleOpenTwin(bld);
                                        }}
                                        style={{
                                            width: '100%', background: 'rgba(255,255,255,0.05)',
                                            color: '#cbd5e1', border: '1px solid var(--border-subtle)', padding: '9px', borderRadius: 6, fontWeight: 600,
                                            fontSize: 11.5, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
                                            gap: 8, transition: 'all 0.15s'
                                        }}
                                        onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(255,255,255,0.1)'; e.currentTarget.style.color = '#fff'; }}
                                        onMouseLeave={(e) => { e.currentTarget.style.background = 'rgba(255,255,255,0.05)'; e.currentTarget.style.color = '#cbd5e1'; }}
                                    >
                                        <IconBuilding />
                                        <span>Launch Connected Building Digital Twin</span>
                                    </button>
                                )}
                            </div>
                        </div>
                    )}

                    {viewMode === 'map' && selectedBuilding && !selectedUtility && (
                        <div className="glass-panel" style={{
                            position: 'absolute', bottom: 30, right: 30, width: 370, padding: 20,
                            pointerEvents: 'auto', zIndex: 60, background: '#0f172a', border: '1px solid var(--border-medium)'
                        }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <span style={{
                                    fontSize: 9.5, fontWeight: 700, padding: '2px 8px', borderRadius: 4,
                                    background: 'rgba(59, 130, 246, 0.12)', color: '#60a5fa', border: '1px solid rgba(59, 130, 246, 0.3)',
                                    letterSpacing: '0.03em'
                                }}>
                                    3D URBAN CADASTRAL ASSET
                                </span>
                                <button
                                    onClick={() => setSelectedBuilding(null)}
                                    style={{ background: 'none', border: 'none', color: 'var(--text-dim)', cursor: 'pointer', fontSize: 16 }}
                                >
                                    ✕
                                </button>
                            </div>
                            <h3 style={{ margin: '12px 0 4px 0', fontSize: 16, color: '#fff', fontWeight: 700 }}>
                                {selectedBuilding.properties.name}
                            </h3>
                            <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 14 }}>
                                {selectedBuilding.properties.street}
                            </div>

                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 16 }}>
                                <div style={{ background: '#131b2e', padding: 8, borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                                    <div style={{ fontSize: 9.5, color: 'var(--text-dim)', fontWeight: 600 }}>LAND ULPIN</div>
                                    <div className="code-font" style={{ fontSize: 12, fontWeight: 700, color: 'var(--accent-amber)', marginTop: 2 }}>
                                        {selectedBuilding.properties.land_ulpin || "27010482910472"}
                                    </div>
                                </div>
                                <div style={{ background: '#131b2e', padding: 8, borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                                    <div style={{ fontSize: 9.5, color: 'var(--text-dim)', fontWeight: 600 }}>TOTAL HEIGHT</div>
                                    <div style={{ fontSize: 12, fontWeight: 700, color: '#38bdf8', marginTop: 2 }}>
                                        {selectedBuilding.properties.height_m}m ({selectedBuilding.properties.floors} Floors)
                                    </div>
                                </div>
                                <div style={{ background: '#131b2e', padding: 8, borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                                    <div style={{ fontSize: 9.5, color: 'var(--text-dim)', fontWeight: 600 }}>FOOTPRINT AREA</div>
                                    <div style={{ fontSize: 12, fontWeight: 700, color: '#fff', marginTop: 2 }}>
                                        {selectedBuilding.properties.area_sqm} m²
                                    </div>
                                </div>
                                <div style={{ background: '#131b2e', padding: 8, borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                                    <div style={{ fontSize: 9.5, color: 'var(--text-dim)', fontWeight: 600 }}>CTS SURVEY NO</div>
                                    <div style={{ fontSize: 12, fontWeight: 700, color: '#fff', marginTop: 2 }}>
                                        {selectedBuilding.properties.cts_no || "CTS 418/A"}
                                    </div>
                                </div>
                            </div>

                            <button
                                onClick={() => handleOpenTwin(selectedBuilding)}
                                style={{
                                    width: '100%', background: '#2563eb',
                                    color: '#fff', border: 'none', padding: '11px', borderRadius: 6, fontWeight: 600,
                                    fontSize: 12.5, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
                                    gap: 8, transition: 'background 0.15s'
                                }}
                                onMouseEnter={(e) => e.currentTarget.style.background = '#1d4ed8'}
                                onMouseLeave={(e) => e.currentTarget.style.background = '#2563eb'}
                            >
                                <IconBuilding />
                                <span>Launch 3D Architectural Digital Twin</span>
                            </button>
                        </div>
                    )}

                    {viewMode === 'twin' && cadastre && (
                        <React.Fragment>
                            {/* Left Panel: BIM Floor & Unit Hierarchy Inspector */}
                            <div className="glass-panel" style={{
                                position: 'absolute', top: 88, left: 16, bottom: 20, width: 330,
                                display: 'flex', flexDirection: 'column', padding: 16, zIndex: 60,
                                pointerEvents: 'auto', background: '#0f172a', border: '1px solid var(--border-medium)'
                            }}>
                                <div style={{ fontSize: 11, color: 'var(--text-dim)', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                                    <span style={{ color: '#38bdf8', fontWeight: 600 }}>South Mumbai</span>
                                    <span style={{ color: '#475569' }}>/</span>
                                    <span style={{ color: '#cbd5e1' }}>{cadastre.cadastral_division.split(' ')[0]}</span>
                                    <span style={{ color: '#475569' }}>/</span>
                                    <span style={{ color: '#fff', fontWeight: 600 }}>Floor {selectedFloor !== null ? selectedFloor + 1 : 'All'}</span>
                                    {selectedFlat && (
                                        <React.Fragment>
                                            <span style={{ color: '#475569' }}>/</span>
                                            <span style={{ color: '#fbbf24', fontWeight: 600 }}>Flat {selectedFlat.unit_number}</span>
                                        </React.Fragment>
                                    )}
                                </div>

                                {/* Vertical Separation Slider */}
                                <div style={{
                                    background: '#131b2e', borderRadius: 8, padding: 12,
                                    border: '1px solid var(--border-subtle)', marginBottom: 12
                                }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11.5, fontWeight: 600, color: '#f1f5f9' }}>
                                            <span style={{ color: '#3b82f6', display: 'flex' }}><IconExplode /></span>
                                            <span>Floor Separation</span>
                                        </div>
                                        <span className="code-font" style={{ fontSize: 11, fontWeight: 700, color: '#60a5fa', background: 'rgba(59, 130, 246, 0.12)', padding: '1px 6px', borderRadius: 4 }}>
                                            {Math.round(explodeRatio * 100)}%
                                        </span>
                                    </div>
                                    <input
                                        type="range"
                                        min="0"
                                        max="1"
                                        step="0.01"
                                        value={explodeRatio}
                                        onChange={(e) => handleExplodeChange(e.target.value)}
                                        style={{ width: '100%', marginBottom: 10 }}
                                    />
                                    <div style={{ display: 'flex', gap: 6 }}>
                                        {[
                                            { val: 0, label: 'Stack (0%)' },
                                            { val: 0.5, label: 'Inspect (50%)' },
                                            { val: 1.0, label: 'Explode (100%)' }
                                        ].map(btn => {
                                            const isCurrent = Math.abs(explodeRatio - btn.val) < 0.05;
                                            return (
                                                <button
                                                    key={btn.val}
                                                    onClick={() => handleExplodeChange(btn.val)}
                                                    style={{
                                                        flex: 1, background: isCurrent ? 'rgba(59, 130, 246, 0.15)' : 'rgba(255, 255, 255, 0.04)',
                                                        border: isCurrent ? '1px solid rgba(59, 130, 246, 0.4)' : '1px solid var(--border-subtle)',
                                                        color: isCurrent ? '#60a5fa' : 'var(--text-secondary)',
                                                        padding: '4px 0', borderRadius: 4, fontSize: 10, fontWeight: 600, cursor: 'pointer',
                                                        transition: 'all 0.15s'
                                                    }}
                                                >
                                                    {btn.label}
                                                </button>
                                            );
                                        })}
                                    </div>
                                </div>

                                {/* Wing Selector Segmented Control */}
                                <div style={{ display: 'flex', background: '#131b2e', borderRadius: 6, padding: 3, border: '1px solid var(--border-subtle)', marginBottom: 12 }}>
                                    <button
                                        onClick={() => setSelectedWing('all')}
                                        style={{
                                            flex: 1, padding: '5px 0', borderRadius: 4, fontSize: 11, fontWeight: 600,
                                            background: selectedWing === 'all' ? '#2563eb' : 'transparent',
                                            color: selectedWing === 'all' ? '#fff' : 'var(--text-secondary)',
                                            border: 'none', cursor: 'pointer', transition: 'all 0.15s'
                                        }}
                                    >
                                        All Wings
                                    </button>
                                    {cadastre.wings.map(w => (
                                        <button
                                            key={w.wing_id}
                                            onClick={() => setSelectedWing(w.wing_id)}
                                            style={{
                                                flex: 1, padding: '5px 0', borderRadius: 4, fontSize: 11, fontWeight: 600,
                                                background: selectedWing === w.wing_id ? '#2563eb' : 'transparent',
                                                color: selectedWing === w.wing_id ? '#fff' : 'var(--text-secondary)',
                                                border: 'none', cursor: 'pointer', transition: 'all 0.15s'
                                            }}
                                        >
                                            {w.wing_id}
                                        </button>
                                    ))}
                                </div>

                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                                    <span style={{ fontSize: 10.5, fontWeight: 700, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                        Storey Levels ({cadastre.floors_count})
                                    </span>
                                    {selectedFloor !== null && (
                                        <button
                                            onClick={() => handleFloorClick(selectedFloor)}
                                            style={{ background: 'none', border: 'none', color: '#60a5fa', fontSize: 10.5, cursor: 'pointer', fontWeight: 600, padding: 0 }}
                                        >
                                            Reset Isolation
                                        </button>
                                    )}
                                </div>

                                <div style={{ flex: 1, overflowY: 'auto', paddingRight: 4 }}>
                                    {cadastre.floors.slice().reverse().map(fl => {
                                        const isFlActive = (selectedFloor === fl.floor_index);
                                        return (
                                            <div
                                                key={fl.floor_index}
                                                style={{
                                                    background: isFlActive ? '#1e293b' : '#131b2e',
                                                    border: isFlActive ? '1px solid #3b82f6' : '1px solid var(--border-subtle)',
                                                    borderLeft: isFlActive ? '3px solid #3b82f6' : '1px solid var(--border-subtle)',
                                                    borderRadius: 6, padding: '9px 12px', marginBottom: 6, transition: 'all 0.15s'
                                                }}
                                            >
                                                <div
                                                    onClick={() => handleFloorClick(fl.floor_index)}
                                                    style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}
                                                >
                                                    <span style={{ fontWeight: 600, fontSize: 12, color: isFlActive ? '#fff' : '#e2e8f0' }}>
                                                        {fl.floor_label}
                                                    </span>
                                                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                                        <span className="code-font" style={{ fontSize: 10, color: 'var(--text-dim)' }}>
                                                            +{fl.elevation_base_m}m
                                                        </span>
                                                        <span style={{ fontSize: 9.5, padding: '1px 6px', borderRadius: 4, background: 'rgba(255, 255, 255, 0.05)', color: 'var(--text-secondary)' }}>
                                                            {fl.units_count} Units
                                                        </span>
                                                    </div>
                                                </div>

                                                {isFlActive && (
                                                    <div style={{ marginTop: 10, borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: 8 }}>
                                                        <div style={{ fontSize: 9.5, fontWeight: 600, color: 'var(--text-dim)', textTransform: 'uppercase', marginBottom: 6, letterSpacing: '0.04em' }}>
                                                            Select Unit to Inspect Cadastre:
                                                        </div>
                                                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
                                                            {fl.units.map(u => {
                                                                const isUActive = (selectedFlat && selectedFlat.unit_id === u.unit_id);
                                                                return (
                                                                    <div
                                                                        key={u.unit_id}
                                                                        onClick={() => handleFlatClick(u)}
                                                                        style={{
                                                                            background: isUActive ? '#2563eb' : 'rgba(255, 255, 255, 0.04)',
                                                                            color: isUActive ? '#ffffff' : '#e2e8f0',
                                                                            border: isUActive ? '1px solid #60a5fa' : '1px solid var(--border-subtle)',
                                                                            padding: '6px 8px', borderRadius: 5, cursor: 'pointer', transition: 'all 0.15s'
                                                                        }}
                                                                    >
                                                                        <div style={{ fontWeight: 700, fontSize: 11 }}>Flat {u.unit_number}</div>
                                                                        <div style={{ fontSize: 9.5, opacity: isUActive ? 0.9 : 0.6 }}>{u.carpet_area_sqm} m²</div>
                                                                    </div>
                                                                );
                                                            })}
                                                        </div>
                                                    </div>
                                                )}
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>

                            {/* Right Panel: Cadastral Ownership & Property Title Deed */}
                            <div className="glass-panel" style={{
                                position: 'absolute', top: 88, right: 16, bottom: 20, width: 370,
                                display: 'flex', flexDirection: 'column', padding: 20, zIndex: 60,
                                pointerEvents: 'auto', overflowY: 'auto', background: '#0f172a', border: '1px solid var(--border-medium)'
                            }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                                    <span style={{
                                        fontSize: 9.5, fontWeight: 700, padding: '2px 8px', borderRadius: 4,
                                        background: selectedFlat ? 'rgba(245, 158, 11, 0.12)' : 'rgba(59, 130, 246, 0.12)',
                                        color: selectedFlat ? '#fbbf24' : '#60a5fa',
                                        border: `1px solid ${selectedFlat ? 'rgba(245, 158, 11, 0.3)' : 'rgba(59, 130, 246, 0.3)'}`,
                                        letterSpacing: '0.04em'
                                    }}>
                                        {selectedFlat ? "VERTICAL UNIT 3D ULPIN" : "BUILDING BASE PARCEL"}
                                    </span>
                                    <span style={{ fontSize: 10.5, color: '#10b981', display: 'flex', alignItems: 'center', gap: 5, fontWeight: 600 }}>
                                        <span className="pulsing-dot" style={{ width: 6, height: 6 }}></span> MahaBhumi Verified
                                    </span>
                                </div>

                                {selectedFlat ? (
                                    <React.Fragment>
                                        <h3 style={{ margin: '0 0 2px 0', fontSize: 17, color: '#fff', fontWeight: 700 }}>
                                            Unit {selectedFlat.unit_number} ({selectedFlat.wing_name})
                                        </h3>
                                        <div style={{ fontSize: 11.5, color: 'var(--text-secondary)', marginBottom: 14 }}>
                                            {selectedFlat.unit_type} • Level {selectedFlat.floor_number}
                                        </div>

                                        <div style={{
                                            background: '#131b2e', border: '1px solid var(--border-subtle)',
                                            borderRadius: 7, padding: 12, marginBottom: 14
                                        }}>
                                            <div style={{ fontSize: 9.5, fontWeight: 600, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                                3D Vertical ULPIN (Bhu-Aadhaar)
                                            </div>
                                            <div className="code-font" style={{ fontSize: 12.5, fontWeight: 700, color: '#60a5fa', margin: '4px 0', letterSpacing: '0.02em' }}>
                                                {selectedFlat.unit_ulpin}
                                            </div>
                                            <div style={{ fontSize: 10, color: 'var(--text-secondary)' }}>
                                                Base Land Parcel: <span className="code-font" style={{ color: '#fff' }}>{cadastre.land_ulpin}</span>
                                            </div>
                                        </div>

                                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 14 }}>
                                            <div style={{ background: '#131b2e', padding: 10, borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                                                <div style={{ fontSize: 9.5, color: 'var(--text-dim)', fontWeight: 600, textTransform: 'uppercase' }}>RERA Carpet Area</div>
                                                <div style={{ fontSize: 13.5, fontWeight: 700, color: '#fff', marginTop: 2 }}>{selectedFlat.carpet_area_sqm} m²</div>
                                                <div style={{ fontSize: 9.5, color: 'var(--text-dim)', marginTop: 1 }}>{selectedFlat.carpet_area_sqft} sq.ft</div>
                                            </div>
                                            <div style={{ background: '#131b2e', padding: 10, borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                                                <div style={{ fontSize: 9.5, color: 'var(--text-dim)', fontWeight: 600, textTransform: 'uppercase' }}>Built-Up Area</div>
                                                <div style={{ fontSize: 13.5, fontWeight: 700, color: '#fff', marginTop: 2 }}>{selectedFlat.built_up_area_sqm} m²</div>
                                                <div style={{ fontSize: 9.5, color: 'var(--text-dim)', marginTop: 1 }}>Gross Enclosed</div>
                                            </div>
                                            <div style={{ background: '#131b2e', padding: 10, borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                                                <div style={{ fontSize: 9.5, color: 'var(--text-dim)', fontWeight: 600, textTransform: 'uppercase' }}>UDS (Land Share)</div>
                                                <div style={{ fontSize: 13.5, fontWeight: 700, color: '#fbbf24', marginTop: 2 }}>{selectedFlat.uds_percentage}</div>
                                                <div style={{ fontSize: 9.5, color: 'var(--text-dim)', marginTop: 1 }}>Undivided Share</div>
                                            </div>
                                            <div style={{ background: '#131b2e', padding: 10, borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                                                <div style={{ fontSize: 9.5, color: 'var(--text-dim)', fontWeight: 600, textTransform: 'uppercase' }}>Elevation (MSL)</div>
                                                <div style={{ fontSize: 13.5, fontWeight: 700, color: '#38bdf8', marginTop: 2 }}>+{selectedFlat.elevation_base_m}m</div>
                                                <div style={{ fontSize: 9.5, color: 'var(--text-dim)', marginTop: 1 }}>Base datum</div>
                                            </div>
                                        </div>

                                        <div style={{ background: '#131b2e', borderRadius: 8, padding: 12, border: '1px solid var(--border-subtle)', marginBottom: 14 }}>
                                            <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-secondary)', marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                                Cadastral Ownership & Title
                                            </div>
                                            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '5px 0', borderBottom: '1px solid rgba(255,255,255,0.06)', fontSize: 11.5 }}>
                                                <span style={{ color: 'var(--text-dim)' }}>Titleholder</span>
                                                <span style={{ fontWeight: 600, color: '#fff', textAlign: 'right' }}>{selectedFlat.owner_name}</span>
                                            </div>
                                            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '5px 0', borderBottom: '1px solid rgba(255,255,255,0.06)', fontSize: 11.5 }}>
                                                <span style={{ color: 'var(--text-dim)' }}>Property Card</span>
                                                <span className="code-font" style={{ color: '#fbbf24' }}>{selectedFlat.property_card_no}</span>
                                            </div>
                                            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '5px 0', borderBottom: '1px solid rgba(255,255,255,0.06)', fontSize: 11.5 }}>
                                                <span style={{ color: 'var(--text-dim)' }}>CTS Survey No</span>
                                                <span style={{ color: '#fff' }}>{selectedFlat.cts_no}</span>
                                            </div>
                                            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '5px 0', borderBottom: '1px solid rgba(255,255,255,0.06)', fontSize: 11.5 }}>
                                                <span style={{ color: 'var(--text-dim)' }}>Tax SAC Assessment</span>
                                                <span className="code-font" style={{ color: '#fff' }}>{selectedFlat.tax_assessment_sac}</span>
                                            </div>
                                            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '5px 0', fontSize: 11.5 }}>
                                                <span style={{ color: 'var(--text-dim)' }}>Title Status</span>
                                                <span style={{ color: '#10b981', fontWeight: 600 }}>Freehold • Clear Title (MahaRERA Registered)</span>
                                            </div>
                                        </div>

                                        <button
                                            onClick={() => {
                                                navigator.clipboard.writeText(selectedFlat.unit_ulpin);
                                                setCopiedCode(true);
                                                setTimeout(() => setCopiedCode(false), 2200);
                                            }}
                                            style={{
                                                width: '100%', background: copiedCode ? 'rgba(16, 185, 129, 0.15)' : 'rgba(255, 255, 255, 0.05)',
                                                color: copiedCode ? '#10b981' : '#cbd5e1',
                                                border: copiedCode ? '1px solid rgba(16, 185, 129, 0.4)' : '1px solid var(--border-subtle)',
                                                padding: '9px 12px', borderRadius: 6, fontWeight: 600, fontSize: 11.5, cursor: 'pointer',
                                                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7, transition: 'all 0.15s'
                                            }}
                                        >
                                            {copiedCode ? <IconCheck /> : <IconCopy />}
                                            <span>{copiedCode ? "Copied 3D ULPIN to Clipboard" : "Copy 3D ULPIN Code"}</span>
                                        </button>
                                    </React.Fragment>
                                ) : (
                                    <React.Fragment>
                                        <h3 style={{ margin: '0 0 3px 0', fontSize: 17, color: '#fff', fontWeight: 700 }}>
                                            {cadastre.name}
                                        </h3>
                                        <div style={{ fontSize: 11.5, color: 'var(--text-secondary)', marginBottom: 14 }}>
                                            {cadastre.street} • {cadastre.cadastral_division}
                                        </div>

                                        <div style={{
                                            background: '#131b2e', border: '1px solid var(--border-subtle)',
                                            borderRadius: 7, padding: 12, marginBottom: 14
                                        }}>
                                            <div style={{ fontSize: 9.5, fontWeight: 600, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                                Land Parcel ULPIN (Bhu-Aadhaar)
                                            </div>
                                            <div className="code-font" style={{ fontSize: 13, fontWeight: 700, color: '#60a5fa', margin: '4px 0' }}>
                                                {cadastre.land_ulpin}
                                            </div>
                                            <div style={{ fontSize: 10, color: 'var(--text-secondary)' }}>
                                                CTS Survey: <b>{cadastre.cts_no}</b>
                                            </div>
                                        </div>

                                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 14 }}>
                                            <div style={{ background: '#131b2e', padding: 10, borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                                                <div style={{ fontSize: 9.5, color: 'var(--text-dim)', fontWeight: 600, textTransform: 'uppercase' }}>TOTAL HEIGHT</div>
                                                <div style={{ fontSize: 13.5, fontWeight: 700, color: '#fff', marginTop: 2 }}>{cadastre.height_m} m</div>
                                                <div style={{ fontSize: 9.5, color: 'var(--text-dim)', marginTop: 1 }}>{cadastre.floors_count} Storeys</div>
                                            </div>
                                            <div style={{ background: '#131b2e', padding: 10, borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                                                <div style={{ fontSize: 9.5, color: 'var(--text-dim)', fontWeight: 600, textTransform: 'uppercase' }}>VERTICAL UNITS</div>
                                                <div style={{ fontSize: 13.5, fontWeight: 700, color: '#fbbf24', marginTop: 2 }}>{cadastre.total_units} Units</div>
                                                <div style={{ fontSize: 9.5, color: 'var(--text-dim)', marginTop: 1 }}>{cadastre.wings.length} Wings</div>
                                            </div>
                                            <div style={{ background: '#131b2e', padding: 10, borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                                                <div style={{ fontSize: 9.5, color: 'var(--text-dim)', fontWeight: 600, textTransform: 'uppercase' }}>FOOTPRINT AREA</div>
                                                <div style={{ fontSize: 13.5, fontWeight: 700, color: '#fff', marginTop: 2 }}>{cadastre.footprint_area_sqm} m²</div>
                                            </div>
                                            <div style={{ background: '#131b2e', padding: 10, borderRadius: 6, border: '1px solid var(--border-subtle)' }}>
                                                <div style={{ fontSize: 9.5, color: 'var(--text-dim)', fontWeight: 600, textTransform: 'uppercase' }}>TYPICAL FLOOR PLATE</div>
                                                <div style={{ fontSize: 13.5, fontWeight: 700, color: '#38bdf8', marginTop: 2 }}>{cadastre.floor_plate_sqm} m²</div>
                                            </div>
                                        </div>

                                        <div style={{
                                            background: '#131b2e', borderRadius: 7, padding: 12,
                                            border: '1px solid var(--border-subtle)', textAlign: 'center', marginTop: 'auto'
                                        }}>
                                            <div style={{ fontSize: 11.5, fontWeight: 600, color: '#94a3b8', marginBottom: 3 }}>
                                                Inspect Vertical Property Units
                                            </div>
                                            <div style={{ fontSize: 10.5, color: 'var(--text-dim)', lineHeight: 1.4 }}>
                                                Select any floor slab or residential unit in the 3D model to inspect its vertical boundary deed and titleholder registry.
                                            </div>
                                        </div>
                                    </React.Fragment>
                                )}
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