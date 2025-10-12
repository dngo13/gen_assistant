# initialization file
"""
This file initializes the flask backend application.
"""
# Imports
from flask import Flask, render_template_string
from backend.routes.calendar import get_upcoming_events
from backend.routes.prescriptions import send_daily_prescription_reminder

def create_app():
    # Create the flask app
    app = Flask(__name__)

    from .routes.calendar import calendar_bp
    from .routes.prescriptions import prescriptions_bp
    from .routes.gas import gas_bp
    from .routes.llm import llm_bp

    app.register_blueprint(calendar_bp)
    app.register_blueprint(prescriptions_bp)
    app.register_blueprint(gas_bp)
    app.register_blueprint(llm_bp)
    # Start scheduler
    from .scheduler import scheduler, start_scheduler
    start_scheduler()
    scheduler.add_job(get_upcoming_events, 'interval', minutes=30)
    scheduler.add_job(send_daily_prescription_reminder, 'cron', hour=22, minute=30)

    @app.route('/')
    def index():
        # Get all routes in the app
        routes = []
        for rule in app.url_map.iter_rules():
            # Exclude static files
            if rule.endpoint != 'static':
                routes.append({
                    'endpoint': rule.endpoint,
                    'methods': list(rule.methods),
                    'url': str(rule)
                })

        # Define the HTML template as a string
        html_template = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <body style="background-color:#4ab6ff;">
            <title>Backend Flask Routes</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    margin: 20px;
                }
                table {
                    width: 100%;
                    border-collapse: collapse;
                }
                table, th, td {
                    border: 1px solid black;
                }
                th, td {
                    padding: 8px;
                    text-align: left;
                }
                th {
                    background-color: #4ab6ff;
                }
                .status {
                    font-weight: bold;
                    color: green;
                }
            </style>
        </head>
        <body>
            <h1>Flask Application Routes</h1>
            <table>
                <thead>
                    <tr>
                        <th>Endpoint</th>
                        <th>Methods</th>
                        <th>URL</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    {% for route in routes %}
                    <tr>
                        <td>{{ route['endpoint'] }}</td>
                        <td>{{ ', '.join(route['methods']) }}</td>
                        <td>{{ route['url'] }}</td>
                        <td><span class="status">Active</span></td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </body>
        </html>
        """

        # Use Flask's render_template_string to dynamically inject routes into HTML
        return render_template_string(html_template, routes=routes)

    return app