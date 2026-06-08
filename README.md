# DXF Coordinate Converter

A web application and command-line tool to convert DXF files from UTM Zone 42N (meters) to WGS84 (latitude/longitude in degrees).

## Features

- **Web Application**: User-friendly drag-and-drop interface
- **Command-line Tool**: Convert files directly from the terminal
- **Batch Conversion**: Process multiple entity types
- **High Precision**: 8 decimal places for accurate coordinates

### Supported Entity Types
- POINT
- TEXT
- LINE
- LWPOLYLINE
- POLYLINE
- CIRCLE
- ARC

### Conversion Details
- **Source CRS**: EPSG:32642 (UTM Zone 42N) - Meters
- **Target CRS**: EPSG:4326 (WGS84) - Degrees/Minutes/Seconds format

## Installation

### Prerequisites
- Python 3.7+
- pip

### Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

### Web Application

1. Start the Flask server:
```bash
python app.py
```

2. Open your browser and navigate to:
```
http://127.0.0.1:5000
```

3. Upload your DXF file (drag & drop or click to select)
4. Click "Convert" button
5. Download the converted file

### Command-line Tool

Run the conversion script directly:
```bash
python coordinate_conversion.py
```

When prompted:
- Enter the input DXF file path
- Enter the output DXF file path (optional - will auto-generate if left blank)

Example:
```
Enter input DXF file path: input_file.dxf
Enter output DXF file path (press Enter for default): 
Output saved to: input_file_LATLONG.dxf
```

## File Structure

```
coordinate_conversion/
├── app.py                      # Flask web application
├── coordinate_conversion.py    # Core conversion module
├── requirements.txt            # Python dependencies
├── templates/
│   └── index.html             # Web interface
├── A16c-BL10,11,12,13.dxf     # Example DXF file
└── README.md                   # This file
```

## Output

- **Web App**: Downloads converted file to your default downloads folder
- **Command-line**: Saves file with `_LATLONG` suffix in the same directory
  - Example: `input.dxf` → `input_LATLONG.dxf`

## API Endpoints

### POST `/api/convert`
Upload and convert a DXF file.

**Request:**
- Content-Type: multipart/form-data
- File parameter: DXF file to convert

**Response:**
```json
{
    "success": true,
    "message": "Conversion complete!...",
    "output_file": "filename_LATLONG.dxf",
    "download_url": "/api/download/filename_LATLONG.dxf"
}
```

### GET `/api/download/<filename>`
Download a converted DXF file.

### GET `/api/info`
Get conversion metadata and supported entity types.

## Limitations

- Maximum file size: 50MB
- Only supports DXF format
- UTM Zone 42N only (can be modified in the script)

## Troubleshooting

### "ModuleNotFoundError" errors
Make sure all dependencies are installed:
```bash
pip install -r requirements.txt
```

### Web app won't start
Check if port 5000 is already in use:
```bash
netstat -ano | findstr :5000
```

### Conversion errors
- Ensure the DXF file is valid and not corrupted
- Check that coordinates are in UTM Zone 42N
- Some unsupported entity types will be skipped

## Technical Details

### Coordinate Transformation
Uses the `pyproj` library to transform coordinates using EPSG definitions:
- Source: EPSG:32642 (UTM Zone 42N, meters)
- Target: EPSG:4326 (WGS84, degrees)

### DXF Processing
Uses the `ezdxf` library to:
- Read DXF files in any supported version
- Parse entity coordinates
- Write converted entities to new DXF files
- Preserve layer information and entity properties

## License

This project is provided as-is for coordinate conversion purposes.

## Support

For issues or questions, refer to:
- [ezdxf Documentation](https://ezdxf.readthedocs.io/)
- [pyproj Documentation](https://pyproj4.github.io/pyproj/stable/)
- [Flask Documentation](https://flask.palletsprojects.com/)
