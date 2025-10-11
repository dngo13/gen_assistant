from flask import Blueprint, request, jsonify
import json
import os
import datetime
from backend.utils import send_event_to_llm
prescriptions_bp = Blueprint('prescriptions', __name__)

# File to store prescriptions
# PRESCRIPTIONS_FILE = '../../prescriptions.json'
PRESCRIPTIONS_FILE = os.path.join(os.getcwd(), 'prescriptions.json')

def load_prescriptions():
    if os.path.exists(PRESCRIPTIONS_FILE):
        with open(PRESCRIPTIONS_FILE, 'r') as file:
            return json.load(file)
    return []

def save_prescriptions(prescriptions):
    with open(PRESCRIPTIONS_FILE, 'w') as file:
        json.dump(prescriptions, file, indent=4)

@prescriptions_bp.route('/get_prescriptions', methods=['GET'])
def get_prescriptions():
    print("current wd: ", os.getcwd())
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    print("project root :", project_root)
    prescriptions = load_prescriptions()
    return jsonify({'prescriptions': prescriptions})

@prescriptions_bp.route('/add_prescription', methods=['POST'])
def add_prescription():
    prescription_data = request.get_json()
    prescription = prescription_data.get('prescription')
    if not prescription:
        return jsonify({'error': 'Prescription is required.'}), 400
    prescriptions = load_prescriptions()
    if prescription not in prescriptions:
        prescriptions.append(prescription)
        save_prescriptions(prescriptions)
        return jsonify({'message': 'Prescription added.'})
    return jsonify({'error': 'Prescription already exists.'}), 400

@prescriptions_bp.route('/remove_prescription', methods=['POST'])
def remove_prescription():
    prescription_data = request.get_json()
    prescription = prescription_data.get('prescription')
    if not prescription:
        return jsonify({'error': 'Prescription is required.'}), 400
    prescriptions = load_prescriptions()
    if prescription in prescriptions:
        prescriptions.remove(prescription)
        save_prescriptions(prescriptions)
        return jsonify({'message': 'Prescription removed.'})
    return jsonify({'error': 'Prescription not found.'}), 404

def send_daily_prescription_reminder():
    prescriptions = load_prescriptions()
    event_summary = "Medicine reminder"

    reminder_message = "Reminder to take your prescriptions:\n" + "\n".join(prescriptions)
    
    # llm_response = None
    fallback_response = f"Mizuki, it's time to take your medication.\n {prescriptions}"
    try:
        # Get LLM response
        llm_response = send_event_to_llm(event_summary, datetime.datetime.now().isoformat(), reminder_message)
        if not llm_response or "error" in llm_response.lower():
            llm_response = fallback_response
    except Exception as e:
        print(f'LLM Exception: {e}')
        # If no llm response, use fallback generic message.
        llm_response = fallback_response
