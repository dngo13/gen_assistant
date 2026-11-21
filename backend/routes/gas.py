from flask import Blueprint, request, jsonify
import json
import datetime
from backend.utils import generate_code27_reminder
import os
gas_bp = Blueprint('gas', __name__)

# File name for the JSON log
#log_file = '../../gas_log.json'
# C:\Users\diane\Nextcloud\Documents\AI-Files\gen_assistant\gas_log.json

log_file = os.path.join(os.getcwd(), 'gas_log.json')

# Gas reminder for Prius
@gas_bp.route('/fuel_reminder', methods=['GET'])
def fuel_reminder():
    response = generate_code27_reminder(
        "Give Mizuki a brief, natural reminder to get gas for her Prius. Only speak as Sirius.",
        "Reminder: Please get gas for the Prius.",
    )
    return jsonify({"response": response})


# Log gas to file
@gas_bp.route('/log_gas', methods=['POST'])
def log_gas():
    try:
        # Get data from request
        data = request.get_json()
        print("Received data:", data)
        date = data.get('date')
        odometer = data.get('odometer')
        amount_paid = data.get('amount_paid')
        # Ensure required fields are present
        if not date or not odometer or not amount_paid:
            return jsonify({'error': 'Missing required fields'}), 400
        
        try:
            print(date)
            # Format the date to MM-DD-YYYY if it's in another format
            formatted_date = datetime.datetime.strptime(date, "%Y-%m-%d").strftime("%m-%d-%Y")
            print(formatted_date)
        except Exception as e:
            print("error", str(e))
            return jsonify({'error formatting date'})
        # Create the log entry
        log_entry = {
            'date': str(formatted_date),
            'odometer': float(odometer),
            'amount_paid': str(amount_paid)
        }
    
        # Initialize or read existing log
        try:
            with open(log_file, 'r') as f:
                gas_log = json.load(f)
        except FileNotFoundError:
            gas_log = []

        # Add the new entry
        gas_log.append(log_entry)

        # Write back to the JSON file
        with open(log_file, 'w') as f:
            json.dump(gas_log, f, indent=4)
    except Exception as e:
        # Catch all errors and return a 400 with the error message
        return jsonify({'error': str(e)}), 400
    return jsonify({"message": "Gas entry logged successfully", "entry": log_entry}), 201

# Get gas log
@gas_bp.route('/get_gas_log', methods=['GET'])
def get_gas_log():
    try:
        with open(log_file, 'r') as f:
            gas_log = json.load(f)
        return jsonify(gas_log), 200
    except FileNotFoundError:
        print("Error getting gas log")
        return jsonify({"message": "Log file not found"}), 404
