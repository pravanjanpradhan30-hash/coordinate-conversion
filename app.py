from flask import Flask, render_template, request, send_file, jsonify
import os
import uuid
from werkzeug.utils import secure_filename
from coordinate_conversion import convert_dxf_file, dxf_to_kml, dwg_to_dxf
import tempfile

app = Flask(__name__)

# Configuration
UPLOAD_FOLDER = tempfile.gettempdir()
ALLOWED_EXTENSIONS = {'dxf'}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def parse_utm_zone(utm_zone_str):
    """Parse e.g. '42N' or '5S' into an EPSG code string. Returns None if invalid."""
    if not utm_zone_str:
        return None
    s = utm_zone_str.strip().upper()
    if len(s) < 2:
        return None
    hemisphere = s[-1]
    if hemisphere not in ('N', 'S'):
        return None
    try:
        zone = int(s[:-1])
    except ValueError:
        return None
    if not (1 <= zone <= 60):
        return None
    epsg_num = 32600 + zone if hemisphere == 'N' else 32700 + zone
    return f"EPSG:{epsg_num}"


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/convert', methods=['POST'])
def convert():
    """API endpoint to convert DXF file"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': 'No file provided'}), 400

        file = request.files['file']

        if file.filename == '':
            return jsonify({'success': False, 'message': 'No file selected'}), 400

        if not allowed_file(file.filename):
            return jsonify({'success': False, 'message': 'Only DXF and DWG files are allowed'}), 400

        if file.filename.rsplit('.', 1)[1].lower() == 'dwg':
            return jsonify({
                'success': False,
                'message': 'DWG files can only be exported to KML. Select "KML (Google Earth)" as the output format.'
            }), 400

        direction = request.form.get('direction', 'forward').lower()
        if direction not in {'forward', 'reverse'}:
            return jsonify({'success': False, 'message': 'Invalid conversion direction'}), 400

        source_epsg = parse_utm_zone(request.form.get('utm_zone', '42N'))
        if not source_epsg:
            return jsonify({'success': False, 'message': 'Invalid UTM zone. Use format like 42N or 5S.'}), 400

        filename = secure_filename(file.filename)
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(input_path)

        base, ext = os.path.splitext(filename)
        zone_label = request.form.get('utm_zone', '42N').upper()
        suffix = f"_UTM{zone_label}" if direction == 'reverse' else "_LATLONG"
        output_filename = f"{base}{suffix}{ext}"
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)

        success, message, result_path = convert_dxf_file(
            input_path,
            output_path,
            reverse=(direction == 'reverse'),
            source_epsg=source_epsg
        )

        if not success:
            try:
                os.remove(input_path)
            except:
                pass
            return jsonify({'success': False, 'message': message}), 400

        return jsonify({
            'success': True,
            'message': message,
            'output_file': output_filename,
            'download_url': f'/api/download/{output_filename}'
        }), 200

    except Exception as e:
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500


@app.route('/api/download/<filename>')
def download(filename):
    """API endpoint to download converted file"""
    try:
        if '..' in filename or '/' in filename or '\\' in filename:
            return jsonify({'success': False, 'message': 'Invalid filename'}), 400

        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        if not os.path.exists(file_path):
            return jsonify({'success': False, 'message': 'File not found'}), 404

        return send_file(
            file_path,
            as_attachment=True,
            download_name=filename,
            mimetype='application/octet-stream'
        )

    except Exception as e:
        return jsonify({'success': False, 'message': f'Download error: {str(e)}'}), 500


@app.route('/api/convert-to-kml', methods=['POST'])
def convert_to_kml():
    """API endpoint to export DXF or DWG file as KML"""
    temp_dxf_path = None
    input_path = None
    ext = None
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': 'No file provided'}), 400

        file = request.files['file']

        if file.filename == '':
            return jsonify({'success': False, 'message': 'No file selected'}), 400

        if not allowed_file(file.filename):
            return jsonify({'success': False, 'message': 'Only DXF and DWG files are allowed'}), 400

        input_crs = request.form.get('input_crs', 'latlong').lower()
        if input_crs not in {'latlong', 'utm'}:
            return jsonify({'success': False, 'message': 'Invalid input CRS'}), 400

        source_epsg = parse_utm_zone(request.form.get('utm_zone', '42N'))
        if not source_epsg:
            return jsonify({'success': False, 'message': 'Invalid UTM zone. Use format like 42N or 5S.'}), 400

        filename = secure_filename(file.filename)
        if not filename:
            filename = f"{uuid.uuid4().hex}{os.path.splitext(file.filename)[1].lower()}"

        ext = filename.rsplit('.', 1)[1].lower()
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(input_path)

        if ext == 'dwg':
            base = os.path.splitext(filename)[0]
            temp_dxf_name = f"{base}_from_dwg_{uuid.uuid4().hex[:8]}.dxf"
            temp_dxf_path = os.path.join(app.config['UPLOAD_FOLDER'], temp_dxf_name)

            ok, msg = dwg_to_dxf(input_path, temp_dxf_path)
            try:
                os.remove(input_path)
                input_path = None
            except Exception:
                pass

            if not ok:
                return jsonify({'success': False, 'message': f'DWG conversion failed: {msg}'}), 400

            dxf_input = temp_dxf_path
        else:
            dxf_input = input_path

        base = os.path.splitext(filename)[0]
        output_filename = f"{base}.kml"
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)

        success, message, _ = dxf_to_kml(dxf_input, output_path, is_utm_input=(input_crs == 'utm'), source_epsg=source_epsg)

        if not success:
            return jsonify({'success': False, 'message': message}), 400

        return jsonify({
            'success': True,
            'message': message,
            'output_file': output_filename,
            'download_url': f'/api/download/{output_filename}'
        }), 200

    except Exception as e:
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500

    finally:
        if temp_dxf_path and os.path.exists(temp_dxf_path):
            try:
                os.remove(temp_dxf_path)
            except Exception:
                pass
        if input_path and ext != 'dwg' and os.path.exists(input_path):
            try:
                os.remove(input_path)
            except Exception:
                pass


@app.route('/api/info')
def info():
    """Get conversion information"""
    return jsonify({
        'forward_conversion': 'UTM Zone (selectable) -> EPSG:4326 (WGS84 - Degrees)',
        'reverse_conversion': 'EPSG:4326 (WGS84 - Degrees) -> UTM Zone (selectable)',
        'supported_entities': [
            'POINT',
            'TEXT',
            'LINE',
            'LWPOLYLINE',
            'POLYLINE',
            'CIRCLE',
            'ARC'
        ],
        'decimal_places': 8
    })


@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({'success': False, 'message': 'File too large (max 50MB)'}), 413


if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
