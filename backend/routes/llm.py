"""
This file defines the llm routes for getting model parameters and setting.
"""
from flask import Blueprint, request, jsonify
import json
import os

llm_bp = Blueprint('llm', __name__)

#model_config_file = '../bot_config/model.json'
model_config_file = os.path.join(os.getcwd(),"bot_config/model.json")
# Get model params
@llm_bp.route('/get_model_params', methods=['GET'])
def get_model_params():
    #print("current wd: ", os.getcwd())
    #print("test wd: ", os.path.join(os.getcwd(),"bot_config/model.json"))
    try:
        with open(model_config_file, 'r') as f:
            model_params = json.load(f)
        return jsonify(model_params), 200
    except FileNotFoundError:
        print("Error getting model params")
        return jsonify({"message": "LLM model params file not found"}), 404
    
# Set model params
@llm_bp.route('/set_model_param', methods=['POST'])
def set_model_param():
    try:
        data = request.get_json()
        param = data.get("param")
        value = data.get("value")

        with open(model_config_file, 'r', encoding='utf-8') as f:
            model_params = json.load(f)

        if param not in model_params:
            return jsonify({"message": f"Parameter '{param}' not found"}), 404

        new_value = float(value)
        model_params[param] = new_value

        with open(model_config_file, 'w', encoding='utf-8') as f:
            json.dump(model_params, f, indent=4)

        return jsonify({"message": f"Updated {param} to {new_value}"}), 200

    except Exception as e:
        print(f"Error updating model param: {e}")
        return jsonify({"message": "Error updating model parameter"}), 500
