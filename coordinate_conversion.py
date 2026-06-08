import ezdxf
from pyproj import Transformer
import os
import math
import ctypes

SOURCE_EPSG = "EPSG:32642"  # UTM Zone 42N (meters)
TARGET_EPSG = "EPSG:4326"   # WGS84 (degrees)
OUTPUT_SUFFIX = "_LATLONG"
REVERSE_OUTPUT_SUFFIX = "_UTM42N"
ROUND_DIGITS = 8

forward_transformer = Transformer.from_crs(SOURCE_EPSG, TARGET_EPSG, always_xy=True)
reverse_transformer = Transformer.from_crs(TARGET_EPSG, SOURCE_EPSG, always_xy=True)


def _expand_long_path(path):
    # AutoCAD COM SaveAs rejects Windows 8.3 short paths (e.g. PRAVAN~1 from tempdir)
    parent = os.path.dirname(path)
    buf = ctypes.create_unicode_buffer(32768)
    n = ctypes.windll.kernel32.GetLongPathNameW(parent, buf, 32768)
    long_parent = buf.value if n else parent
    return os.path.join(long_parent, os.path.basename(path))


def dwg_to_dxf(dwg_path, dxf_path):
    """Convert DWG to DXF via AutoCAD or BricsCAD COM automation."""
    try:
        import win32com.client
    except ImportError:
        return False, "pywin32 is not installed. Run: pip install pywin32"

    dwg_path = os.path.abspath(dwg_path)
    dxf_path = os.path.abspath(dxf_path)

    if not os.path.exists(dwg_path):
        return False, f"DWG file not found: {dwg_path}"

    dxf_path_long = _expand_long_path(dxf_path)

    app = None
    tried = []
    for prog_id in ("AutoCAD.Application", "BricscadApp.AcadApplication"):
        tried.append(prog_id)
        try:
            app = win32com.client.Dispatch(prog_id)
            break
        except Exception:
            continue

    if app is None:
        return False, f"No supported CAD application found. Tried: {', '.join(tried)}."

    doc = None
    try:
        doc = app.Documents.Open(dwg_path)
        # SaveAs type 61 = R2013 DXF (AC1027); produces LWPOLYLINE + MTEXT
        doc.SaveAs(dxf_path_long, 61)
        doc.Close(False)
        doc = None
        return True, f"DWG converted to DXF via {prog_id}."
    except Exception as exc:
        return False, f"Error during DWG conversion: {exc}"
    finally:
        if doc is not None:
            try:
                doc.Close(False)
            except Exception:
                pass


def utm_to_latlon(x, y):
    """Convert UTM coordinates to latitude/longitude"""
    lon, lat = forward_transformer.transform(x, y)
    return round(lon, ROUND_DIGITS), round(lat, ROUND_DIGITS)


def latlon_to_utm(x, y):
    """Convert longitude/latitude to UTM coordinates"""
    utm_x, utm_y = reverse_transformer.transform(x, y)
    return round(utm_x, ROUND_DIGITS), round(utm_y, ROUND_DIGITS)


def transform_xy(x, y, reverse=False):
    if reverse:
        return latlon_to_utm(x, y)
    return utm_to_latlon(x, y)


def copy_linetypes(source_doc, target_doc):
    """Copy linetype definitions used by layers/entities."""
    for linetype in source_doc.linetypes:
        name = linetype.dxf.name
        if target_doc.linetypes.has_entry(name):
            continue

        try:
            dxfattribs = {}
            if linetype.dxf.hasattr('description'):
                dxfattribs['description'] = linetype.dxf.description
            target_doc.linetypes.new(name=name, dxfattribs=dxfattribs)
        except:
            pass


def copy_layer_properties(source_layer, target_layer):
    """Copy the main DXF layer properties supported by ezdxf."""
    layer_attrs = (
        'color',
        'linetype',
        'lineweight',
        'plot',
        'true_color',
        'transparency',
        'flags',
        'plotstyle_handle',
        'material_handle',
        'description',
    )

    for attr_name in layer_attrs:
        try:
            if source_layer.dxf.hasattr(attr_name):
                setattr(target_layer.dxf, attr_name, source_layer.dxf.get(attr_name))
        except:
            pass


def convert_dxf_file(input_file, output_file=None, reverse=False):
    """
    Convert a DXF file from UTM (meters) to WGS84 (degrees)
    
    Args:
        input_file: Path to input DXF file
        output_file: Path to output DXF file (if None, creates one with suffix)
    
    Returns:
        Tuple of (success, message, output_file_path)
    """
    try:
        # Validate input file
        if not os.path.exists(input_file):
            return False, f"Input file not found: {input_file}", None
        
        # Load the DXF file
        doc = ezdxf.readfile(input_file)
        msp = doc.modelspace()
        
        # Create output filename if not provided
        if output_file is None:
            base, ext = os.path.splitext(input_file)
            suffix = REVERSE_OUTPUT_SUFFIX if reverse else OUTPUT_SUFFIX
            output_file = f"{base}{suffix}{ext}"
        
        # Create output document with same settings
        output_doc = ezdxf.new(dxfversion=doc.dxfversion)
        output_msp = output_doc.modelspace()

        copy_linetypes(doc, output_doc)
        
        # Copy layers
        for layer in doc.layers:
            try:
                if layer.dxf.name == '0':
                    target_layer = output_doc.layers.get('0')
                elif output_doc.layers.has_entry(layer.dxf.name):
                    target_layer = output_doc.layers.get(layer.dxf.name)
                else:
                    target_layer = output_doc.layers.new(name=layer.dxf.name)

                copy_layer_properties(layer, target_layer)
            except:
                pass
        
        created_count = 0
        found_count = 0
        
        # Process each entity
        for entity in msp:
            try:
                found_count += 1
                
                if entity.dxftype() == 'POINT':
                    x, y, z = entity.dxf.location
                    new_x, new_y = transform_xy(x, y, reverse=reverse)
                    new_entity = output_msp.add_point((new_x, new_y, z))
                    new_entity.dxf.layer = entity.dxf.layer
                    created_count += 1
                
                elif entity.dxftype() == 'TEXT':
                    x, y, z = entity.dxf.insert
                    new_x, new_y = transform_xy(x, y, reverse=reverse)
                    new_entity = output_msp.add_text(
                        entity.dxf.text,
                        dxfattribs={
                            'insert': (new_x, new_y, z),
                            'height': entity.dxf.height,
                            'layer': entity.dxf.layer
                        }
                    )
                    created_count += 1
                
                elif entity.dxftype() == 'LINE':
                    x1, y1, z1 = entity.dxf.start
                    x2, y2, z2 = entity.dxf.end
                    new_x1, new_y1 = transform_xy(x1, y1, reverse=reverse)
                    new_x2, new_y2 = transform_xy(x2, y2, reverse=reverse)
                    new_entity = output_msp.add_line((new_x1, new_y1, z1), (new_x2, new_y2, z2))
                    new_entity.dxf.layer = entity.dxf.layer
                    created_count += 1
                
                elif entity.dxftype() == 'LWPOLYLINE':
                    points = entity.get_points()
                    new_points = []
                    for point in points:
                        x, y = point[0], point[1]
                        z = point[2] if len(point) > 2 else 0
                        new_x, new_y = transform_xy(x, y, reverse=reverse)
                        new_points.append((new_x, new_y, z))
                    new_entity = output_msp.add_lwpolyline(new_points)
                    new_entity.dxf.layer = entity.dxf.layer
                    if hasattr(entity.dxf, 'flags'):
                        try:
                            new_entity.close(True if (entity.dxf.flags & 1) else False)
                        except:
                            pass
                    created_count += 1
                
                elif entity.dxftype() == 'POLYLINE':
                    points = [vertex.dxf.location for vertex in entity.vertices]
                    new_points = []
                    for point in points:
                        x, y = point[0], point[1]
                        z = point[2] if len(point) > 2 else 0
                        new_x, new_y = transform_xy(x, y, reverse=reverse)
                        new_points.append((new_x, new_y, z))
                    new_entity = output_msp.add_lwpolyline(new_points)
                    new_entity.dxf.layer = entity.dxf.layer
                    created_count += 1
                
                elif entity.dxftype() == 'CIRCLE':
                    x, y, z = entity.dxf.center
                    new_x, new_y = transform_xy(x, y, reverse=reverse)
                    radius = entity.dxf.radius
                    new_entity = output_msp.add_circle((new_x, new_y, z), radius)
                    new_entity.dxf.layer = entity.dxf.layer
                    created_count += 1
                
                elif entity.dxftype() == 'ARC':
                    x, y, z = entity.dxf.center
                    new_x, new_y = transform_xy(x, y, reverse=reverse)
                    new_entity = output_msp.add_arc(
                        (new_x, new_y, z),
                        radius=entity.dxf.radius,
                        start_angle=entity.dxf.start_angle,
                        end_angle=entity.dxf.end_angle
                    )
                    new_entity.dxf.layer = entity.dxf.layer
                    created_count += 1
                
                else:
                    # Copy entity as-is for unsupported types
                    pass
            
            except Exception as ex:
                print(f"Warning: Error processing entity: {ex}")
        
        # Save output file
        output_doc.saveas(output_file)
        
        message = f"Conversion complete!\nEntities processed: {found_count}\nEntities converted: {created_count}\nOutput: {os.path.basename(output_file)}"
        return True, message, output_file
    
    except Exception as ex:
        return False, f"Error converting DXF file: {str(ex)}", None


def escape_xml(text):
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


def generate_kml(layers, doc_name):
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<kml xmlns="http://www.opengis.net/kml/2.2">',
        '  <Document>',
        f'    <name>{escape_xml(doc_name)}</name>',
    ]

    for layer_name, entities in layers.items():
        lines.append('    <Folder>')
        lines.append(f'      <name>{escape_xml(layer_name)}</name>')

        for ent in entities:
            lines.append('      <Placemark>')
            lines.append(f'        <name>{escape_xml(ent["name"])}</name>')

            if ent['type'] == 'point':
                lon, lat, z = ent['coords'][0]
                lines.append('        <Point>')
                lines.append(f'          <coordinates>{lon},{lat},{z}</coordinates>')
                lines.append('        </Point>')

            elif ent['type'] == 'line':
                coord_str = ' '.join(f'{lon},{lat},{z}' for lon, lat, z in ent['coords'])
                lines.append('        <LineString>')
                lines.append(f'          <coordinates>{coord_str}</coordinates>')
                lines.append('        </LineString>')

            elif ent['type'] == 'polygon':
                coord_str = ' '.join(f'{lon},{lat},{z}' for lon, lat, z in ent['coords'])
                lines.append('        <Polygon>')
                lines.append('          <outerBoundaryIs><LinearRing>')
                lines.append(f'            <coordinates>{coord_str}</coordinates>')
                lines.append('          </LinearRing></outerBoundaryIs>')
                lines.append('        </Polygon>')

            lines.append('      </Placemark>')

        lines.append('    </Folder>')

    lines.append('  </Document>')
    lines.append('</kml>')
    return '\n'.join(lines)


def dxf_to_kml(input_file, output_file=None, is_utm_input=False):
    """
    Export a DXF file as KML.

    Args:
        input_file: Path to input DXF file
        output_file: Path to output KML file (default: same name with .kml extension)
        is_utm_input: True if DXF coordinates are UTM Zone 42N (will convert to lat/long)

    Returns:
        Tuple of (success, message, output_file_path)
    """
    try:
        if not os.path.exists(input_file):
            return False, f"Input file not found: {input_file}", None

        doc = ezdxf.readfile(input_file)
        msp = doc.modelspace()

        if output_file is None:
            base, _ = os.path.splitext(input_file)
            output_file = f"{base}.kml"

        layers = {}
        found_count = 0
        created_count = 0

        def to_lonlat(x, y):
            if is_utm_input:
                return utm_to_latlon(x, y)
            return x, y

        for entity in msp:
            found_count += 1
            layer_name = entity.dxf.layer if entity.dxf.hasattr('layer') else '0'
            if layer_name not in layers:
                layers[layer_name] = []

            try:
                etype = entity.dxftype()

                if etype == 'POINT':
                    x, y, z = entity.dxf.location
                    lon, lat = to_lonlat(x, y)
                    layers[layer_name].append({'type': 'point', 'coords': [(lon, lat, z)], 'name': 'POINT'})
                    created_count += 1

                elif etype in ('TEXT', 'MTEXT'):
                    x, y, z = entity.dxf.insert
                    lon, lat = to_lonlat(x, y)
                    label = entity.dxf.text if etype == 'TEXT' else entity.plain_text()
                    layers[layer_name].append({'type': 'point', 'coords': [(lon, lat, z)], 'name': label})
                    created_count += 1

                elif etype == 'LINE':
                    x1, y1, z1 = entity.dxf.start
                    x2, y2, z2 = entity.dxf.end
                    lon1, lat1 = to_lonlat(x1, y1)
                    lon2, lat2 = to_lonlat(x2, y2)
                    layers[layer_name].append({'type': 'line', 'coords': [(lon1, lat1, z1), (lon2, lat2, z2)], 'name': 'LINE'})
                    created_count += 1

                elif etype == 'LWPOLYLINE':
                    points = list(entity.get_points())
                    coords = []
                    for point in points:
                        x, y = point[0], point[1]
                        z = point[2] if len(point) > 2 else 0
                        lon, lat = to_lonlat(x, y)
                        coords.append((lon, lat, z))
                    is_closed = bool(entity.dxf.flags & 1) if entity.dxf.hasattr('flags') else False
                    if is_closed and coords:
                        coords.append(coords[0])
                    geom_type = 'polygon' if is_closed else 'line'
                    layers[layer_name].append({'type': geom_type, 'coords': coords, 'name': 'POLYLINE'})
                    created_count += 1

                elif etype == 'POLYLINE':
                    points = [vertex.dxf.location for vertex in entity.vertices]
                    coords = []
                    for point in points:
                        x, y = point[0], point[1]
                        z = point[2] if len(point) > 2 else 0
                        lon, lat = to_lonlat(x, y)
                        coords.append((lon, lat, z))
                    layers[layer_name].append({'type': 'line', 'coords': coords, 'name': 'POLYLINE'})
                    created_count += 1

                elif etype == 'CIRCLE':
                    cx, cy, cz = entity.dxf.center
                    r = entity.dxf.radius
                    coords = []
                    for i in range(37):
                        angle = math.radians(i * 10)
                        px = cx + r * math.cos(angle)
                        py = cy + r * math.sin(angle)
                        lon, lat = to_lonlat(px, py)
                        coords.append((lon, lat, cz))
                    layers[layer_name].append({'type': 'polygon', 'coords': coords, 'name': 'CIRCLE'})
                    created_count += 1

                elif etype == 'ARC':
                    cx, cy, cz = entity.dxf.center
                    r = entity.dxf.radius
                    start_angle = entity.dxf.start_angle
                    end_angle = entity.dxf.end_angle
                    if end_angle < start_angle:
                        end_angle += 360
                    num_points = max(int((end_angle - start_angle) / 5), 2)
                    coords = []
                    for i in range(num_points + 1):
                        angle = math.radians(start_angle + (end_angle - start_angle) * i / num_points)
                        px = cx + r * math.cos(angle)
                        py = cy + r * math.sin(angle)
                        lon, lat = to_lonlat(px, py)
                        coords.append((lon, lat, cz))
                    layers[layer_name].append({'type': 'line', 'coords': coords, 'name': 'ARC'})
                    created_count += 1

            except Exception as ex:
                print(f"Warning: Error processing entity: {ex}")

        kml_content = generate_kml(layers, os.path.basename(input_file))
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(kml_content)

        message = f"KML export complete!\nEntities processed: {found_count}\nEntities exported: {created_count}\nOutput: {os.path.basename(output_file)}"
        return True, message, output_file

    except Exception as ex:
        return False, f"Error exporting to KML: {str(ex)}", None


if __name__ == "__main__":
    input_file = input("Enter input DXF file path: ").strip()
    output_file = input("Enter output DXF file path (press Enter for default): ").strip()

    success, message, output_path = convert_dxf_file(input_file, output_file if output_file else None)
    print(message)
    if success:
        print(f"Output saved to: {output_path}")
