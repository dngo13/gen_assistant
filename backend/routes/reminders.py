from flask import Blueprint, jsonify, request

from backend.utils import generate_code27_reminder

reminders_bp = Blueprint("reminders", __name__)


@reminders_bp.route("/generate_reminder", methods=["POST"])
def generate_reminder():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "A JSON reminder request is required."}), 400

    prompt = data.get("prompt")
    fallback = data.get("fallback")
    if not isinstance(prompt, str) or not prompt.strip():
        return jsonify({"error": "A non-empty prompt is required."}), 400
    if not isinstance(fallback, str) or not fallback.strip():
        return jsonify({"error": "A non-empty fallback is required."}), 400
    if len(prompt) > 2000 or len(fallback) > 1000:
        return jsonify({"error": "The prompt or fallback is too long."}), 400

    response = generate_code27_reminder(prompt.strip(), fallback.strip())
    return jsonify({"response": response})
