import os
import gsd.hoomd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Circle

def render_system(gsd_path, output_png_path, title):
    # Open the GSD file
    if not os.path.exists(gsd_path):
        print(f"Warning: File {gsd_path} does not exist. Skipping.")
        return

    f = gsd.hoomd.open(gsd_path, 'r')
    frame = f[0]

    positions = np.array(frame.particles.position)
    typeids = np.array(frame.particles.typeid)
    diameters = np.array(frame.particles.diameter)
    
    bond_groups = []
    if frame.bonds.N > 0:
        bond_groups = np.array(frame.bonds.group)

    # Setup colors for particle types
    # Type 0: Colloid (dark blue/indigo)
    # Type 1: A (bright cyan/blue)
    # Type 2: B (bright coral/orange)
    colors_dict = {
        0: '#1b4f72',  # Deep ocean blue
        1: '#2980b9',  # Cyan/Blue
        2: '#e74c3c'   # Coral/Orange
    }
    default_color = '#7f8c8d'

    # Pre-filter valid bonds (not wrapping across PBC) using original coordinates
    valid_bonds = []
    if len(bond_groups) > 0 and not ("linear_polymer" in gsd_path or "comb_polymer" in gsd_path):
        for bond in bond_groups:
            p1 = positions[bond[0]]
            p2 = positions[bond[1]]
            
            box_length = np.array(frame.configuration.box[:3])
            delta = p1 - p2
            delta -= np.round(delta / box_length) * box_length
            dist = np.linalg.norm(delta)
            
            if dist < 4.0: 
                valid_bonds.append(bond)

    # Apply a 5-degree tilt in xy plane and a 5-degree tilt in xz plane for comb polymers only
    # rotated individually around each molecule's center of mass (with PBC unwrapping)
    if "comb_polymer" in gsd_path:
        N_parts = len(positions)
        adj = {i: [] for i in range(N_parts)}
        if len(bond_groups) > 0:
            for bond in bond_groups:
                adj[bond[0]].append(bond[1])
                adj[bond[1]].append(bond[0])
            
        visited = [False] * N_parts
        components = []
        for i in range(N_parts):
            if not visited[i]:
                comp = []
                queue = [i]
                visited[i] = True
                while queue:
                    curr = queue.pop(0)
                    comp.append(curr)
                    for neighbor in adj[curr]:
                        if not visited[neighbor]:
                            visited[neighbor] = True
                            queue.append(neighbor)
                components.append(comp)

        theta = np.radians(5.0)
        cos_t, sin_t = np.cos(theta), np.sin(theta)
        phi = np.radians(5.0)
        cos_p, sin_p = np.cos(phi), np.sin(phi)

        # Unwrapped positions array to compute correct centers of mass
        unwrapped = np.copy(positions)
        box_length = np.array(frame.configuration.box[:3])
        
        for comp in components:
            if len(comp) <= 1:
                continue
            # BFS to unwrap coordinates relative to the first particle of the component
            visited_bfs = {comp[0]: True}
            queue = [comp[0]]
            while queue:
                curr = queue.pop(0)
                for neighbor in adj[curr]:
                    if neighbor not in visited_bfs:
                        visited_bfs[neighbor] = True
                        delta = positions[neighbor] - positions[curr]
                        delta -= np.round(delta / box_length) * box_length
                        unwrapped[neighbor] = unwrapped[curr] + delta
                        queue.append(neighbor)
                        
            # Compute the correct center of mass of the unwrapped molecule
            center = np.mean(unwrapped[comp], axis=0)
            cx, cy, cz = center[0], center[1], center[2]
            
            # Rotate each particle in the molecule around its center of mass
            for idx in comp:
                x_rel = unwrapped[idx, 0] - cx
                y_rel = unwrapped[idx, 1] - cy
                z_rel = unwrapped[idx, 2] - cz
                
                # xy rotation (5 degrees)
                x1 = x_rel * cos_t - y_rel * sin_t
                y1 = x_rel * sin_t + y_rel * cos_t
                z1 = z_rel
                
                # xz rotation (5 degrees)
                x2 = x1 * cos_p - z1 * sin_p
                y2 = y1
                z2 = x1 * sin_p + z1 * cos_p
                
                positions[idx, 0] = cx + x2
                positions[idx, 1] = cy + y2
                positions[idx, 2] = cz + z2

    # Compute bounding box of the actual particles to eliminate box whitespace
    buffer = 2.0
    buffer_y = 6.0 if "linear_polymer" in gsd_path else 2.0
    
    x_min = np.min(positions[:, 0]) - buffer
    x_max = np.max(positions[:, 0]) + buffer
    y_min = np.min(positions[:, 1]) - buffer_y
    y_max = np.max(positions[:, 1]) + buffer_y

    dx = x_max - x_min
    dy = y_max - y_min
    aspect_ratio = dx / dy

    # Define a clean, compact figure size matching the particle aspect ratio
    height = 2.0
    width = height * aspect_ratio
    # Limit maximum width to avoid extremely wide images
    if width > 8.0:
        width = 8.0
        height = width / aspect_ratio
    
    fig, ax = plt.subplots(figsize=(width, height), dpi=150)
    ax.set_aspect('equal')

    # Draw filtered bonds using rotated coordinates
    for bond in valid_bonds:
        p1 = positions[bond[0]]
        p2 = positions[bond[1]]
        ax.plot([p1[0], p2[0]], [p1[1], p2[1]], 
                color='#bdc3c7', linewidth=1.2, zorder=1)

    # Sort particles by z-coordinate to get correct depth-ordering (back to front)
    sorted_indices = np.argsort(positions[:, 2])

    # Draw particles as Circle patches
    for idx in sorted_indices:
        pos = positions[idx]
        t = typeids[idx]
        dia = diameters[idx]
        
        rad = dia / 2.0
        # If patchy or grafted colloid, increase the central particle size (type 0)
        # Note: both of these templates use type 0 for the central colloid
        if t == 0:
            rad *= 1.6
            
        circle = Circle((pos[0], pos[1]), radius=rad,
                        facecolor=colors_dict.get(t, default_color),
                        edgecolor='#2c3e50', linewidth=0.5, alpha=0.9, zorder=2)
        ax.add_patch(circle)

    # Style the title and axis limits
    fig.suptitle(title, fontsize=9, fontweight='bold', color='#2c3e50', y=0.96)
    
    ax.set_xlim(x_min, x_max)
    ax.set_ylim(y_min, y_max)
    ax.axis('off')
    
    # Save the output image with transparent background and zero margin padding
    os.makedirs(os.path.dirname(output_png_path), exist_ok=True)
    plt.savefig(output_png_path, bbox_inches='tight', pad_inches=0.01, transparent=True)
    plt.close()

    print(f"Successfully rendered system: {gsd_path} -> {output_png_path}")

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__)) # This is repo_root/docs/
    repo_root = os.path.dirname(script_dir)

    systems = [
        ("example_star_polymer.gsd", "source/_static/star_polymer_render.png", "Star Polymer Configuration"),
        ("example_linear_polymer.gsd", "source/_static/linear_polymer_render.png", "Linear Polymer Configurations"),
        ("example_ring_polymer.gsd", "source/_static/ring_polymer_render.png", "Ring Polymer Configurations"),
        ("example_comb_polymer.gsd", "source/_static/comb_polymer_render.png", "Comb Polymer Configurations"),
        ("example_grafted_colloid.gsd", "source/_static/grafted_colloid_render.png", "Polymer-Grafted Colloid Configurations"),
        ("example_patchy_colloid.gsd", "source/_static/patchy_colloid_render.png", "Patchy Colloid Configurations")
    ]

    for gsd_name, doc_rel_path, title in systems:
        gsd_path = os.path.join(repo_root, "examples", "templates", gsd_name)
        output_png_path = os.path.join(script_dir, doc_rel_path)
        render_system(gsd_path, output_png_path, title)

if __name__ == "__main__":
    main()
