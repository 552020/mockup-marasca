# marasca_mockup.py
# Costruisce una bottiglia d'olio Marasca o Dorica con etichetta e la renderizza con Cycles (Blender 4.x).
#
# FILE SCARICATO DAL SITO: porta dentro etichetta, impostazioni ed eventuale bottiglia da file.
#   In Blender aperto: area «Scripting» → menu Testo → Apri → scegli il file → pulsante «Esegui script».
#   Dal Terminale (macOS): /Applications/Blender.app/Contents/MacOS/Blender -P mockup-marasca-blender.txt
#   Con Blender aperto lo script costruisce solo la scena; con -b (background) la renderizza in render.png.
#
# Uso generale dal Terminale (Blender in background):
#   blender -b -P marasca_mockup.py -- --label etichetta.png --out render.png
#
# Per aprire la scena in Blender e lavorarci a mano:
#   blender -P marasca_mockup.py -- --label etichetta.png
#
# Opzioni (tutte facoltative; quelle incorporate dal sito fanno da default):
#   --bottle marasca250|marasca500|marasca750|dorica500|custom   (default marasca500)
#   --diameter MM --height MM --body MM --shoulder MM --shoulder-shape 1.2..3.5 --neck-diameter MM
#                         quote a scelta, sovrascrivono quelle del modello di partenza
#   --label FILE          PNG o JPG dell'etichetta fronte (senza, viene generata un'etichetta segnaposto)
#   --label-width MM      larghezza in mm (default 90); l'altezza segue le proporzioni dell'immagine
#   --label-height MM     forza l'altezza in mm (l'immagine viene stirata)
#   --label-bottom MM     distanza dal fondo in mm (default 32)
#   --back FILE           etichetta retro, facoltativa
#   --back-width MM       larghezza del retro (default 60)
#   --model FILE          bottiglia da file GLB, glTF, OBJ o STL al posto di quella parametrica
#   --model-height MM     altezza reale della bottiglia da file (default 271)
#   --glass verde|trasparente|ambra                         (default verde)
#   --cap nero|oro|argento                                  (default nero)
#   --cap-color '#rrggbb' colore del tappo a scelta, al posto di --cap (con --cap-metal per la finitura metallica)
#   --neck anello|dritto  collo con anello sotto il tappo (default) oppure dritto
#   --no-spout            tappo senza beccuccio versatore sopra
#   --finish opaca|lucida                                   (default opaca)
#   --angle GRADI         rotazione della camera attorno alla bottiglia, 0 = frontale (default 18)
#   --res W H             risoluzione in pixel (default 1600 2000)
#   --samples N           campioni Cycles (default 256; 64 per una prova rapida)
#   --transparent         sfondo trasparente: PNG con alpha da montare in Photoshop
#   --view Standard|AgX   trasformata colore (default Standard: i colori dell'etichetta restano fedeli)
#   --out FILE            immagine di uscita (default render.png)
#   --save-blend FILE     salva anche la scena .blend
#   --no-render           costruisce solo la scena (automatico con Blender aperto)

import argparse
import base64
import json
import math
import os
import sys
import tempfile

import bpy
import bmesh
from mathutils import Vector

EMBEDDED = None  # la pagina web sostituisce questa riga con impostazioni, etichette e bottiglia da file

MM = 0.001            # la scena è in metri, le quote qui sotto in millimetri
NECK_R = 15.75        # imboccatura PP 31,5 per il tappo versatore
WALL = 3.0            # spessore del vetro
INNER_NECK_R = 9.8    # raggio interno del collo

BOTTLES = {
    'marasca250': dict(name='Marasca 250 ml', R=26.0, H=208.0, body=128.0, shoulder=12.0, p=2.4),
    'marasca500': dict(name='Marasca 500 ml', R=31.5, H=271.0, body=168.0, shoulder=15.0, p=2.4),
    'marasca750': dict(name='Marasca 750 ml', R=36.0, H=300.0, body=186.0, shoulder=17.0, p=2.4),
    'dorica500':  dict(name='Dorica 500 ml',  R=30.0, H=297.0, body=178.0, shoulder=34.0, p=1.5),
}
GLASS = {
    'verde':       dict(color=(0.10, 0.30, 0.10, 1.0), absorb=(0.30, 0.62, 0.28), density=260.0),
    'trasparente': dict(color=(0.97, 0.99, 0.97, 1.0), absorb=(0.88, 0.95, 0.88), density=15.0),
    'ambra':       dict(color=(0.60, 0.28, 0.06, 1.0), absorb=(0.75, 0.42, 0.12), density=220.0),
}
CAPS = {
    'nero':    dict(color=(0.015, 0.015, 0.015, 1.0), metallic=0.0, roughness=0.40),
    'oro':     dict(color=(0.83, 0.62, 0.22, 1.0),   metallic=1.0, roughness=0.22),
    'argento': dict(color=(0.86, 0.86, 0.85, 1.0),   metallic=1.0, roughness=0.20),
}


def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def cap_spec(args):
    """Tappo: uno dei preset, oppure un colore esadecimale a scelta."""
    if not args.cap_color:
        return CAPS[args.cap]
    h = args.cap_color.lstrip('#')
    if len(h) != 6:
        raise SystemExit(f'--cap-color vuole un colore come #8a1c1c, ricevuto {args.cap_color!r}')
    rgb = tuple(srgb_to_linear(int(h[i:i + 2], 16) / 255.0) for i in (0, 2, 4))
    return dict(color=(*rgb, 1.0), metallic=1.0 if args.cap_metal else 0.0, roughness=0.25 if args.cap_metal else 0.40)


def parse_args():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    p = argparse.ArgumentParser(prog='marasca_mockup.py')
    p.add_argument('--bottle', default='marasca500', choices=sorted(BOTTLES) + ['custom'])
    p.add_argument('--diameter', type=float)
    p.add_argument('--height', type=float)
    p.add_argument('--body', type=float)
    p.add_argument('--shoulder', type=float)
    p.add_argument('--shoulder-shape', type=float)
    p.add_argument('--neck-diameter', type=float)
    p.add_argument('--label')
    p.add_argument('--label-width', type=float, default=90.0)
    p.add_argument('--label-height', type=float)
    p.add_argument('--label-bottom', type=float, default=32.0)
    p.add_argument('--back')
    p.add_argument('--back-width', type=float, default=60.0)
    p.add_argument('--model')
    p.add_argument('--model-height', type=float, default=271.0)
    p.add_argument('--label-radius', type=float)
    p.add_argument('--glass', default='verde', choices=sorted(GLASS))
    p.add_argument('--cap', default='nero', choices=sorted(CAPS))
    p.add_argument('--cap-color')
    p.add_argument('--cap-metal', action='store_true')
    p.add_argument('--neck', default='anello', choices=['anello', 'dritto'])
    p.add_argument('--no-spout', action='store_true')
    p.add_argument('--finish', default='opaca', choices=['opaca', 'lucida'])
    p.add_argument('--angle', type=float, default=18.0)
    p.add_argument('--res', type=int, nargs=2, default=[1600, 2000], metavar=('W', 'H'))
    p.add_argument('--samples', type=int, default=256)
    p.add_argument('--transparent', action='store_true')
    p.add_argument('--view', default='Standard')
    p.add_argument('--out', default='render.png')
    p.add_argument('--save-blend')
    p.add_argument('--no-render', action='store_true')
    if EMBEDDED and EMBEDDED.get('settings'):
        known = {a.dest for a in p._actions}
        p.set_defaults(**{k: v for k, v in EMBEDDED['settings'].items() if k in known and v is not None})
    return p.parse_args(argv)


# ---------------------------------------------------------------- utilità

def set_input(node, names, value):
    """Imposta il primo socket esistente tra i nomi dati (compatibilità 3.x / 4.x)."""
    for n in names:
        if n in node.inputs:
            node.inputs[n].default_value = value
            return True
    return False


def link_object(ob):
    bpy.context.scene.collection.objects.link(ob)
    return ob


def mesh_from_bmesh(name, bm, smooth=True, sharp_angle=math.radians(35)):
    if smooth:
        for f in bm.faces:
            f.smooth = True
        for e in bm.edges:
            if len(e.link_faces) == 2 and e.calc_face_angle(0.0) > sharp_angle:
                e.smooth = False
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return link_object(bpy.data.objects.new(name, me))


def lathe(name, pts_mm, steps=128):
    """Solido di rivoluzione attorno a Z da un profilo (raggio, quota) in mm."""
    bm = bmesh.new()
    verts = [bm.verts.new((r * MM, 0.0, z * MM)) for r, z in pts_mm]
    edges = [bm.edges.new((verts[i], verts[i + 1])) for i in range(len(verts) - 1)]
    bmesh.ops.spin(bm, geom=verts + edges, cent=(0, 0, 0), axis=(0, 0, 1), dvec=(0, 0, 0),
                   angle=math.tau, steps=steps, use_merge=True)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return mesh_from_bmesh(name, bm)


def look_at(ob, target):
    direction = Vector(target) - ob.location
    ob.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()


def embedded_file(key, prefix):
    """Scrive su disco un file incorporato dalla pagina (data URL o base64) e ne restituisce il percorso."""
    if not EMBEDDED or not EMBEDDED.get(key):
        return None
    item = EMBEDDED[key]
    if isinstance(item, str):
        item = {'data': item, 'name': prefix}
    data = item['data']
    ext = item.get('ext')
    if data.startswith('data:'):
        head, data = data.split(',', 1)
        if not ext:
            ext = {'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp'}.get(head[5:].split(';')[0], 'png')
    path = os.path.join(tempfile.gettempdir(), f'{prefix}.{ext or "bin"}')
    with open(path, 'wb') as f:
        f.write(base64.b64decode(data))
    return path


# ---------------------------------------------------------------- geometria

def outer_profile(b, neck='anello'):
    R, H, a = b['R'], b['H'], min(NECK_R + 2.5, b['R'] - 2.0)
    pts = [(0, 0), (R * 0.72, 0), (R * 0.92, 1.2), (R * 0.99, 3), (R, 6), (R, b['body'])]
    n = 16
    for i in range(1, n + 1):
        t = i / n
        r = a + (R - a) * (1 - t ** b['p']) ** (1 / b['p'])
        pts.append((r, b['body'] + t * b['shoulder']))
    y0 = b['body'] + b['shoulder']
    if neck == 'dritto':
        pts += [(a - 0.9, y0 + 3), (NECK_R + 0.3, y0 + 8), (NECK_R, y0 + 12), (NECK_R, H)]
    else:
        pts += [(a - 0.9, y0 + 3), (NECK_R + 1.0, y0 + 8), (NECK_R + 0.4, y0 + 14), (NECK_R - 0.4, H - 28),
                (NECK_R + 1.0, H - 23), (NECK_R + 1.0, H - 19), (NECK_R, H - 17), (NECK_R, H)]
    return pts


def inner_profile(b):
    R, H, a = b['R'], b['H'], min(NECK_R + 2.5, b['R'] - 2.0)
    y0 = b['body'] + b['shoulder']
    ri = min(INNER_NECK_R, NECK_R - 4.0)
    pts = [(ri, H), (ri, y0 + 14), (ri + 0.6, y0 + 8), (max(a - WALL - 0.6, ri), y0 + 3)]
    n = 12
    for i in range(n, 0, -1):
        t = i / n
        r = a + (R - a) * (1 - t ** b['p']) ** (1 / b['p']) - WALL
        pts.append((max(r, ri), b['body'] + t * b['shoulder']))
    pts += [(R - WALL, b['body']), (R - WALL, 9.5), (R * 0.7, 7.5), (0, 7.0)]
    return pts


def build_bottle(b, glass_mat, oil_mat, neck='anello'):
    bottle = lathe('Bottiglia', outer_profile(b, neck) + inner_profile(b))
    bottle.data.materials.append(glass_mat)
    R = b['R']
    oil_top = b['body'] - 6.0
    oil = lathe('Olio', [(0, 7.25), (R * 0.7, 7.75), (R - WALL - 0.08, 9.75),
                         (R - WALL - 0.08, oil_top), (0, oil_top)], steps=96)
    oil.data.materials.append(oil_mat)
    return bottle, oil


def build_cap(b, cap_mat, spout=True):
    H = b['H']
    cr = NECK_R + 0.65
    cap = lathe('Tappo', [(0, H - 12), (cr, H - 12), (cr + 1.0, H - 10.5), (cr + 0.6, H + 13), (cr - 0.9, H + 14), (0, H + 14)], steps=96)
    cap.data.materials.append(cap_mat)
    if not spout:
        return cap, None
    spout_mat = bpy.data.materials.new('Beccuccio')
    spout_mat.use_nodes = True
    bsdf = spout_mat.node_tree.nodes['Principled BSDF']
    bsdf.inputs['Base Color'].default_value = (0.02, 0.02, 0.02, 1)
    bsdf.inputs['Roughness'].default_value = 0.5
    spout = lathe('Beccuccio', [(0, H + 14), (8, H + 14), (6, H + 20), (4.5, H + 20), (4.5, H + 15), (0, H + 15)], steps=48)
    spout.data.materials.append(spout_mat)
    return cap, spout


def import_model(path, real_h_mm, glass_mat):
    """Importa GLB/glTF, OBJ o STL, lo raddrizza, lo scala all'altezza reale e lo appoggia a terra."""
    ext = os.path.splitext(path)[1].lower()
    before = set(bpy.data.objects)
    if ext in ('.glb', '.gltf'):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == '.obj':
        bpy.ops.wm.obj_import(filepath=path)
    elif ext == '.stl':
        try:
            bpy.ops.wm.stl_import(filepath=path)
        except AttributeError:
            bpy.ops.import_mesh.stl(filepath=path)
    else:
        raise SystemExit(f'Formato non supportato per --model: {ext}. Usa GLB, glTF, OBJ o STL.')
    objs = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in objs if o.type == 'MESH']
    if not meshes:
        raise SystemExit('Il modello non contiene mesh.')
    root = link_object(bpy.data.objects.new('Bottiglia da file', None))
    for o in objs:
        if o.parent is None or o.parent not in objs:
            o.parent = root

    def bounds():
        bpy.context.view_layer.update()
        pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
        lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        return lo, hi

    lo, hi = bounds()
    ext3 = hi - lo
    if ext3.y > ext3.z and ext3.y >= ext3.x:
        root.rotation_euler = (math.radians(90), 0, 0)      # l'asse lungo era Y: lo porto su Z
    elif ext3.x > ext3.z and ext3.x > ext3.y:
        root.rotation_euler = (0, math.radians(-90), 0)     # l'asse lungo era X
    lo, hi = bounds()
    h = max(1e-9, hi.z - lo.z)
    root.scale = (real_h_mm * MM / h,) * 3
    lo, hi = bounds()
    root.location = (-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2, -lo.z)
    lo, hi = bounds()
    for o in meshes:
        o.data.materials.clear()
        o.data.materials.append(glass_mat)
    radius_mm = max(hi.x - lo.x, hi.y - lo.y) / 2 / MM
    return root, dict(name=os.path.basename(path), R=radius_mm, H=real_h_mm, body=real_h_mm * 0.6)


def build_label(name, b, width_mm, height_mm, bottom_mm, center_angle, mat, segments=128, radius_mm=None):
    """Fascia cilindrica con UV 0..1: l'immagine si avvolge senza distorsioni."""
    R = radius_mm or b['R']
    circ = math.tau * R
    if width_mm > circ:
        print(f'[avviso] {name}: larghezza {width_mm:.0f} mm oltre la circonferenza ({circ:.0f} mm), ridotta.')
        width_mm = circ - 0.5
    half = (width_mm / R) / 2.0
    r = (R + 0.15) * MM
    bm = bmesh.new()
    uv_layer = bm.loops.layers.uv.new('UVMap')
    columns = []
    for i in range(segments + 1):
        u = i / segments
        phi = center_angle - half + u * 2 * half
        x, y = r * math.sin(phi), -r * math.cos(phi)
        columns.append((bm.verts.new((x, y, bottom_mm * MM)),
                        bm.verts.new((x, y, (bottom_mm + height_mm) * MM)), u))
    for i in range(segments):
        a0, a1, ua = columns[i]
        b0, b1, ub = columns[i + 1]
        f = bm.faces.new((a0, b0, b1, a1))
        uvs = {a0: (ua, 0.0), b0: (ub, 0.0), b1: (ub, 1.0), a1: (ua, 1.0)}
        for loop in f.loops:
            loop[uv_layer].uv = uvs[loop.vert]
    ob = mesh_from_bmesh(name, bm, sharp_angle=math.radians(89))
    ob.data.materials.append(mat)
    return ob, width_mm


# ---------------------------------------------------------------- materiali

def new_material(name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    return mat, nt, nt.nodes['Principled BSDF'], nt.nodes['Material Output']


def glass_material(g):
    mat, nt, bsdf, out = new_material('Vetro')
    bsdf.inputs['Base Color'].default_value = g['color']
    bsdf.inputs['Roughness'].default_value = 0.02
    bsdf.inputs['IOR'].default_value = 1.50
    set_input(bsdf, ['Transmission Weight', 'Transmission'], 1.0)
    set_input(bsdf, ['Specular IOR Level', 'Specular'], 0.5)
    vol = nt.nodes.new('ShaderNodeVolumeAbsorption')
    vol.inputs['Color'].default_value = (*g['absorb'], 1.0)
    vol.inputs['Density'].default_value = g['density']
    nt.links.new(vol.outputs['Volume'], out.inputs['Volume'])
    return mat


def oil_material():
    mat, nt, bsdf, out = new_material('Olio')
    bsdf.inputs['Base Color'].default_value = (0.92, 0.74, 0.22, 1.0)
    bsdf.inputs['Roughness'].default_value = 0.04
    bsdf.inputs['IOR'].default_value = 1.47
    set_input(bsdf, ['Transmission Weight', 'Transmission'], 1.0)
    vol = nt.nodes.new('ShaderNodeVolumeAbsorption')
    vol.inputs['Color'].default_value = (0.95, 0.76, 0.22, 1.0)
    vol.inputs['Density'].default_value = 28.0
    nt.links.new(vol.outputs['Volume'], out.inputs['Volume'])
    return mat


def cap_material(c):
    mat, nt, bsdf, out = new_material('Tappo')
    bsdf.inputs['Base Color'].default_value = c['color']
    bsdf.inputs['Metallic'].default_value = c['metallic']
    bsdf.inputs['Roughness'].default_value = c['roughness']
    return mat


def placeholder_image(name='etichetta_segnaposto', w=720, h=960):
    """Etichetta crema con cornice verde e fascia oro, quando non viene passato un file."""
    import numpy as np
    px = np.empty((h, w, 4), dtype=np.float32)
    px[:] = (0.86, 0.80, 0.64, 1.0)
    frame, thick = 28, 5
    px[frame:frame + thick, frame:w - frame] = (0.16, 0.22, 0.07, 1)
    px[h - frame - thick:h - frame, frame:w - frame] = (0.16, 0.22, 0.07, 1)
    px[frame:h - frame, frame:frame + thick] = (0.16, 0.22, 0.07, 1)
    px[frame:h - frame, w - frame - thick:w - frame] = (0.16, 0.22, 0.07, 1)
    px[int(h * 0.56):int(h * 0.56) + 6, int(w * 0.35):int(w * 0.65)] = (0.62, 0.42, 0.08, 1)
    px[int(h * 0.30):int(h * 0.48), int(w * 0.28):int(w * 0.72)] = (0.28, 0.36, 0.14, 1)
    img = bpy.data.images.new(name, w, h, alpha=True)
    img.pixels.foreach_set(px[::-1].ravel())
    img.pack()
    return img


def label_material(name, image, finish):
    mat, nt, bsdf, out = new_material(name)
    tex = nt.nodes.new('ShaderNodeTexImage')
    tex.image = image
    tex.interpolation = 'Cubic'
    geo = nt.nodes.new('ShaderNodeNewGeometry')
    mix = nt.nodes.new('ShaderNodeMixRGB')          # fronte: immagine; retro della carta: bianco caldo
    mix.inputs['Color2'].default_value = (0.90, 0.88, 0.82, 1.0)
    nt.links.new(geo.outputs['Backfacing'], mix.inputs['Fac'])
    nt.links.new(tex.outputs['Color'], mix.inputs['Color1'])
    nt.links.new(mix.outputs['Color'], bsdf.inputs['Base Color'])
    nt.links.new(tex.outputs['Alpha'], bsdf.inputs['Alpha'])
    if finish == 'lucida':
        bsdf.inputs['Roughness'].default_value = 0.30
        set_input(bsdf, ['Coat Weight', 'Clearcoat'], 0.8)
        set_input(bsdf, ['Coat Roughness', 'Clearcoat Roughness'], 0.10)
    else:
        bsdf.inputs['Roughness'].default_value = 0.62
        set_input(bsdf, ['Specular IOR Level', 'Specular'], 0.35)
    for attr, val in (('surface_render_method', 'DITHERED'), ('blend_method', 'HASHED')):
        try:
            setattr(mat, attr, val)
        except Exception:
            pass
    return mat


def floor_material():
    mat, nt, bsdf, out = new_material('Pavimento')
    bsdf.inputs['Base Color'].default_value = (0.45, 0.44, 0.40, 1.0)
    bsdf.inputs['Roughness'].default_value = 0.75
    return mat


# ---------------------------------------------------------------- scena

def add_area(name, location, target, size, power, color=(1.0, 1.0, 1.0)):
    ld = bpy.data.lights.new(name, 'AREA')
    ld.energy, ld.size, ld.color = power, size, color
    ob = link_object(bpy.data.objects.new(name, ld))
    ob.location = location
    look_at(ob, target)
    return ob


def setup_render(scene, args):
    scene.render.engine = 'CYCLES'
    cy = scene.cycles
    cy.samples = args.samples
    cy.use_denoising = True
    cy.max_bounces = 12
    cy.transmission_bounces = 12
    cy.transparent_max_bounces = 12
    cy.glossy_bounces = 6
    cy.volume_bounces = 2
    try:
        prefs = bpy.context.preferences.addons['cycles'].preferences
        prefs.compute_device_type = 'METAL'
        prefs.refresh_devices()
        for d in prefs.devices:
            d.use = True
        cy.device = 'GPU'
        print('[cycles] GPU Metal')
    except Exception as e:
        cy.device = 'CPU'
        print('[cycles] CPU', e)
    scene.render.resolution_x, scene.render.resolution_y = args.res
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = args.transparent
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA' if args.transparent else 'RGB'
    scene.render.image_settings.color_depth = '8'
    try:
        scene.view_settings.view_transform = args.view
    except TypeError:
        scene.view_settings.view_transform = 'Standard'
    scene.view_settings.look = 'None'
    scene.view_settings.exposure = 0.0


def reset_scene():
    """In background riparto da un file vuoto; con Blender aperto svuoto la scena corrente senza toccare l'interfaccia."""
    if bpy.app.background:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        return
    scene = bpy.context.scene
    for ob in list(scene.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.lights, bpy.data.cameras):
        for block in list(coll):
            if block.users == 0:
                coll.remove(block)


def show_in_viewport():
    """Con Blender aperto: anteprima materiali e vista dalla camera."""
    try:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    for space in area.spaces:
                        if space.type == 'VIEW_3D':
                            space.shading.type = 'MATERIAL'
                            space.region_3d.view_perspective = 'CAMERA'
    except Exception:
        pass


def main():
    global NECK_R
    args = parse_args()
    if not bpy.app.background:
        args.no_render = True
    reset_scene()
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.length_unit = 'MILLIMETERS'

    b = dict(BOTTLES[args.bottle if args.bottle in BOTTLES else 'marasca500'])
    if args.bottle == 'custom':
        b['name'] = 'Personalizzata'
    if args.diameter:
        b['R'] = args.diameter / 2
    if args.height:
        b['H'] = args.height
    if args.body:
        b['body'] = args.body
    if args.shoulder:
        b['shoulder'] = args.shoulder
    if args.shoulder_shape:
        b['p'] = args.shoulder_shape
    if args.neck_diameter:
        NECK_R = args.neck_diameter / 2
    H = b['H']

    glass_mat = glass_material(GLASS[args.glass])
    model_path = args.model or embedded_file('model', 'mockup_marasca_bottiglia')
    label_radius = args.label_radius
    if model_path:
        _, info = import_model(model_path, args.model_height, glass_mat)
        b.update(info)
        H = b['H']
        label_radius = label_radius or b['R']
    else:
        build_bottle(b, glass_mat, oil_material(), args.neck)
        build_cap(b, cap_material(cap_spec(args)), spout=not args.no_spout)

    # etichetta fronte (rivolta verso -Y, dove sta la camera con --angle 0)
    front_path = args.label or embedded_file('label_front', 'mockup_marasca_etichetta_fronte')
    if front_path:
        front_img = bpy.data.images.load(os.path.abspath(front_path))
        front_img.pack()
    else:
        print('[avviso] nessun file passato con --label: uso un\'etichetta segnaposto.')
        front_img = placeholder_image()
    aspect = front_img.size[1] / front_img.size[0]
    front_h = args.label_height if args.label_height else args.label_width * aspect
    front_h = min(front_h, b['body'] - 4.0)
    bottom = max(0.0, min(args.label_bottom, b['body'] - front_h))
    _, front_w = build_label('Etichetta fronte', b, args.label_width, front_h, bottom, 0.0,
                             label_material('Etichetta fronte', front_img, args.finish), radius_mm=label_radius)

    back_w = back_h = None
    back_path = args.back or embedded_file('label_back', 'mockup_marasca_etichetta_retro')
    if back_path:
        back_img = bpy.data.images.load(os.path.abspath(back_path))
        back_img.pack()
        back_h = min(args.back_width * back_img.size[1] / back_img.size[0], b['body'] - 4.0)
        _, back_w = build_label('Etichetta retro', b, args.back_width, back_h, bottom, math.pi,
                                label_material('Etichetta retro', back_img, args.finish), radius_mm=label_radius)

    # studio: pavimento, mondo, luci
    bpy.ops.mesh.primitive_plane_add(size=6.0, location=(0, 0, 0))
    floor = bpy.context.active_object
    floor.name = 'Pavimento'
    floor.data.materials.append(floor_material())
    world = bpy.data.worlds.new('Studio')
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes['Background']
    bg.inputs['Color'].default_value = (0.22, 0.22, 0.21, 1.0)
    bg.inputs['Strength'].default_value = 1.0

    target = (0.0, 0.0, H * 0.5 * MM)
    add_area('Chiave', (0.50, -0.65, 0.70), target, 1.20, 26.0, (1.0, 0.96, 0.90))
    add_area('Riempimento', (-0.85, -0.45, 0.35), target, 1.60, 8.0, (0.90, 0.93, 1.0))
    add_area('Controluce', (-0.35, 0.75, 0.60), target, 0.80, 14.0)
    add_area('Alto', (0.0, 0.10, 1.30), target, 2.00, 10.0)

    # camera
    cam_data = bpy.data.cameras.new('Camera')
    cam_data.lens = 85.0
    cam_data.sensor_fit = 'AUTO'
    cam = link_object(bpy.data.objects.new('Camera', cam_data))
    d = H * MM * 3.05
    th = math.radians(args.angle)
    cam.location = (d * math.sin(th), -d * math.cos(th), H * 0.56 * MM)
    look_at(cam, (0.0, 0.0, H * 0.47 * MM))
    scene.camera = cam

    setup_render(scene, args)

    circ = math.tau * (label_radius or b['R'])
    print(f"[bottiglia] {b['name']}: Ø {2*b['R']:.0f} mm, h {H:.0f} mm, circonferenza {circ:.0f} mm, corpo dritto {b['body']:.0f} mm")
    if not model_path:
        print(f"[tappo] {'colore ' + args.cap_color if args.cap_color else args.cap}, collo {args.neck}, {'senza' if args.no_spout else 'con'} beccuccio")
    print(f'[etichetta] fronte {front_w:.0f} × {front_h:.0f} mm, dal fondo {bottom:.0f} mm, copre il {100*front_w/circ:.0f} % del giro')
    if back_w:
        print(f'[etichetta] retro {back_w:.0f} × {back_h:.0f} mm')

    if args.save_blend:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.save_blend))
        print('[salvato]', os.path.abspath(args.save_blend))
    if not bpy.app.background:
        show_in_viewport()
    if not args.no_render:
        scene.render.filepath = os.path.abspath(args.out)
        bpy.ops.render.render(write_still=True)
        print('[render]', scene.render.filepath)


if __name__ == '__main__':
    main()
