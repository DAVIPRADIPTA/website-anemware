from flask import jsonify

def response(status_code, message, data=None):
    """
    Format standar respon API
    """
    res_structure = {
        "status": status_code,
        "message": message,
        "data": data
    }
    return jsonify(res_structure), status_code

def success(data=None, message="Success", status_code=200):
    return response(status_code, message, data)

def error(message="Something went wrong", status_code=400, data=None):
    return response(status_code, message, data)