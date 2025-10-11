"""
This file is used to run the flask backend application.
"""
from backend import create_app

app = create_app()

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000, threaded=True)