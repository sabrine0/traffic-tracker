import logging
from flask import Blueprint, jsonify, request, send_file, current_app, url_for
from app.errors import ValidationError
from app.validators import validate_polygon, validate_area, validate_options
from app.services.export_pipeline import export
from app.services.file_manager import FileManager

logger = logging.getLogger(__name__)

export_bp = Blueprint("export", __name__)


@export_bp.route("/api/export", methods=["POST"])
def export_dxf():
    """Accept polygon + options, run full export pipeline, return download URL."""
    data = request.get_json(silent=True)
    if data is None:
        raise ValidationError("Request body must be JSON", code="INVALID_REQUEST")

    polygon_data = data.get("polygon")
    if polygon_data is None:
        raise ValidationError("Missing 'polygon' field", code="INVALID_REQUEST")

    # Validate polygon
    polygon_coords = validate_polygon(polygon_data)

    # Validate area
    max_area = current_app.config.get("MAX_EXPORT_AREA_KM2", 25)
    validate_area(polygon_coords, max_area)

    # Validate options
    options = validate_options(data.get("options"))

    logger.info(f"Export request: {len(polygon_coords)} vertices, options={options}")

    # Run full pipeline
    result = export(polygon_coords, options)
    download_url = url_for("export.download_file", filename=result["filename"])

    return jsonify({
        "status": "success",
        "download_url": download_url,
        "filename": result["filename"],
        "stats": result["stats"],
        "warnings": result["warnings"],
    })


@export_bp.route("/downloads/<filename>")
def download_file(filename):
    """Serve a generated DXF file for download."""
    if "/" in filename or "\\" in filename or ".." in filename:
        return jsonify({"status": "error", "code": "NOT_FOUND", "message": "File not found"}), 404

    output_dir = current_app.config.get("TEMP_DIR", "output")
    fm = FileManager(output_dir)
    filepath = fm.get_download_path(filename)

    if filepath is None:
        return jsonify({"status": "error", "code": "NOT_FOUND", "message": "File not found"}), 404

    return send_file(
        filepath,
        as_attachment=True,
        download_name=filename,
        mimetype="application/octet-stream",
    )
