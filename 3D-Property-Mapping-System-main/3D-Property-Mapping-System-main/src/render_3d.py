# src/render_3d.py
import geopandas as gpd
import numpy as np
import pyvista as pv
import trimesh
from shapely.geometry import Polygon, MultiPolygon

def generate_3d_scene():
    print("Generating full South Mumbai 3D architectural scene...")
    gdf = gpd.read_file("data/processed/buildings_processed.geojson")
    
    plotter = pv.Plotter(window_size=[1600, 900])
    plotter.set_background("#0f141d")
    
    # Calculate geographical center to normalize coordinate space
    bounds = gdf.total_bounds
    center_x = (bounds[0] + bounds[2]) / 2.0
    center_y = (bounds[1] + bounds[3]) / 2.0

    rendered = 0
    all_meshes = []
    height_scalars = []

    for _, row in gdf.iterrows():
        geom = row.geometry
        height = max(float(row['height_m']), 4.0)
        
        polys = [geom] if geom.geom_type == 'Polygon' else list(geom.geoms)
        
        for poly in polys:
            try:
                coords = np.array(poly.exterior.coords)
                coords[:, 0] -= center_x
                coords[:, 1] -= center_y
                
                # Create planar 2D polygon & extrude along Z axis
                p2d = Polygon(coords)
                mesh_3d = trimesh.creation.extrude_polygon(p2d, height=height)
                
                pv_mesh = pv.wrap(mesh_3d)
                all_meshes.append(pv_mesh)
                height_scalars.append(height)
                rendered += 1
            except Exception:
                continue

    if all_meshes:
        # Merge all building meshes into one multi-block object for smooth performance
        print(f"Combining {rendered} 3D structures into unified viewport...")
        combined_mesh = pv.MultiBlock(all_meshes).combine()
        
        plotter.add_mesh(
            combined_mesh,
            cmap="viridis",
            scalars=combined_mesh.points[:, 2],
            show_edges=True,
            edge_color="#1a2332",
            lighting=True,
            smooth_shading=True
        )
    else:
        print("No valid meshes could be rendered.")

    print(f"✓ Scene loaded with {rendered} buildings across South Mumbai.")
    plotter.add_axes()
    plotter.show_grid(color="#2a3b50")
    plotter.reset_camera()
    plotter.show(title="Full South Mumbai 3D Urban Architecture Twin")

if __name__ == "__main__":
    generate_3d_scene()