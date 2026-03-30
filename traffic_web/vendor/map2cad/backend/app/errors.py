from flask import jsonify, Flask


class AppError(Exception):
    status_code = 500
    code = "INTERNAL_ERROR"

    def __init__(self, message: str, code: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code


class ValidationError(AppError):
    status_code = 400
    code = "VALIDATION_ERROR"


class OverpassError(AppError):
    status_code = 502
    code = "OVERPASS_ERROR"


class ExportError(AppError):
    status_code = 500
    code = "EXPORT_FAILED"


class ConversionError(AppError):
    status_code = 500
    code = "CONVERSION_FAILED"


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(AppError)
    def handle_app_error(error: AppError):
        return jsonify({"status": "error", "code": error.code, "message": error.message}), error.status_code

    @app.errorhandler(404)
    def handle_not_found(_):
        return jsonify({"status": "error", "code": "NOT_FOUND", "message": "Resource not found"}), 404

    @app.errorhandler(413)
    def handle_too_large(_):
        return jsonify({"status": "error", "code": "PAYLOAD_TOO_LARGE", "message": "Request body too large"}), 413

    @app.errorhandler(500)
    def handle_internal(_):
        return jsonify({"status": "error", "code": "INTERNAL_ERROR", "message": "Internal server error"}), 500
