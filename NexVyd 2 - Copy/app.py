from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import mysql.connector as connector
from werkzeug.utils import secure_filename
import os
from ultralytics import YOLO
import bcrypt
from collections import Counter
from dotenv import load_dotenv
import config

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')

# Database connection helper
def connect_to_db():
    try:
        connection = connector.connect(**config.mysql_credentials)
        return connection
    except connector.Error as e:
        print(f"Error connecting to database: {e}")
        return None

# Home route
@app.route('/')
def home():
    return render_template('index.html')

# Signup route
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form.get('name')
        password = request.form.get('password')
        email = request.form.get('email')
        vehicle_id = request.form.get('vehicleId')
        contact_number = request.form.get('phoneNumber')
        address = request.form.get('address')
        car_brand = request.form.get('carBrand')
        model = request.form.get('carModel')

        if not all([name, password, email, vehicle_id, contact_number, address, car_brand, model]):
            flash("All fields are required!", "error")
            return render_template('signup.html')

        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        connection = connect_to_db()
        if connection:
            try:
                with connection.cursor() as cursor:
                    query = '''
                    INSERT INTO user_info (name, password, email, vehicle_id, contact_number, address, car_brand, model)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    '''
                    cursor.execute(query, (name, hashed_password, email, vehicle_id, contact_number, address, car_brand, model))
                    connection.commit()
                flash("Signup successful!", "success")
                return redirect(url_for('dashboard'))
            except connector.IntegrityError as e:
                if 'Duplicate entry' in str(e):
                    flash("Email already exists. Please use a different email.", "error")
                else:
                    flash("An error occurred while signing up. Please try again.", "error")
            except connector.Error as e:
                print(f"Error executing query: {e}")
                flash("An error occurred while signing up. Please try again.", "error")
        else:
            flash("Database connection failed. Please try again later.", "error")

    return render_template('signup.html')

# Login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        if not email or not password:
            return jsonify({"success": False, "message": "Email and password are required!"})

        connection = connect_to_db()
        if connection:
            try:
                with connection.cursor() as cursor:
                    query = "SELECT password FROM user_info WHERE email = %s"
                    cursor.execute(query, (email,))
                    result = cursor.fetchone()
                    if result and bcrypt.checkpw(password.encode('utf-8'), result[0].encode('utf-8')):
                        session['user_email'] = email  # Store user email in session
                        return jsonify({"success": True, "redirect": url_for('dashboard')})
                    else:
                        return jsonify({"success": False, "message": "Invalid email or password."})
            except connector.Error as e:
                print(f"Error executing query: {e}")
                return jsonify({"success": False, "message": "An error occurred during login. Please try again."})
        else:
            return jsonify({"success": False, "message": "Database connection failed. Please try again later."})

    return render_template('login.html')

# Logout route
@app.route('/logout')
def logout():
    session.pop('user_email', None)  # Remove user email in session
    flash("You have been logged out.", "info")
    return redirect(url_for('login'))

# Load YOLO model
model_path = r"C:\Users\naban\Downloads\Car damage Hackathon\NexVyd 2 - Copy\models\model weights\best.pt"
model = YOLO(model_path)

# Helper function to classify damage severity
def classify_damage_severity(detected_parts):
    num_damaged_parts = len(detected_parts)  # Count the number of damaged parts
    if num_damaged_parts == 1:
        return "Minor"
    elif 2 <= num_damaged_parts <= 3:
        return "Moderate"
    else:
        return "Severe"

# Dashboard route
@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if request.method == 'POST':
        file = request.files.get('image')
        if not file:
            flash('Please upload an image.', 'error')
            return render_template('dashboard.html')

        filename = secure_filename(file.filename)
        if not filename.lower().endswith(('.png', '.jpg', '.jpeg')):
            flash('Invalid file type. Please upload an image.', 'error')
            return render_template('dashboard.html')

        # Save the uploaded image
        STATIC_FOLDER = r"C:\Users\naban\Downloads\Car damage Hackathon\NexVyd 2 - Copy\static"
        image_path = os.path.join(STATIC_FOLDER, 'uploaded_image.jpg')
        file.save(image_path)

        # Make predictions using YOLO
        result = model(image_path)
        detected_objects = result[0].boxes
        class_ids = [box.cls.item() for box in detected_objects]
        class_counts = Counter(class_ids)

        # Get the list of detected parts
        detected_parts = [get_part_name_from_id(class_id) for class_id in class_ids if get_part_name_from_id(class_id)]

        # Classify damage severity
        severity = classify_damage_severity(detected_parts)

        # Save the image with detections
        detected_image_path = os.path.join(STATIC_FOLDER, 'detected_image.jpg')
        result[0].save(detected_image_path)

        # Get the user's email from session
        user_email = session.get('user_email')
        if not user_email:
            flash('You need to log in to get an estimate.', 'error')
            return redirect(url_for('login'))

        # Fetch part prices from the database
        part_prices = get_part_prices(user_email, class_counts)

        # Calculate total repair cost
        total_repair_cost = sum(part_data['total'] for part_data in part_prices.values())

        # Fetch insurance companies, damage types, and policy types
        connection = connect_to_db()
        if connection:
            with connection.cursor(dictionary=True) as cursor:
                cursor.execute("SELECT * FROM insurance_companies")
                insurance_companies = cursor.fetchall()

                cursor.execute("SELECT * FROM damage_types")
                damage_types = cursor.fetchall()

                cursor.execute("SELECT * FROM insurance_policy_types")
                policy_types = cursor.fetchall()
        else:
            insurance_companies = []
            damage_types = []
            policy_types = []

        return render_template('estimate.html', 
                             original_image='uploaded_image.jpg', 
                             detected_image='detected_image.jpg', 
                             part_prices=part_prices,
                             total_repair_cost=total_repair_cost,
                             damage_severity=severity,
                             insurance_companies=insurance_companies,
                             damage_types=damage_types,
                             policy_types=policy_types)

    return render_template('dashboard.html')

# Calculate claim route
@app.route('/calculate_claim', methods=['POST'])
def calculate_claim():
    data = request.json
    print("Incoming data:", data)  # Debugging statement

    # Ensure all required keys are present
    required_keys = ['company_id', 'policy_type_id', 'severity_level', 'estimated_repair_cost', 'damage_type_id']
    for key in required_keys:
        if key not in data:
            return jsonify({"error": f"Missing key in request: {key}"}), 400

    company_id = data['company_id']
    policy_type_id = data['policy_type_id']
    severity_level = data['severity_level']
    estimated_repair_cost = float(data['estimated_repair_cost'])
    damage_type_id = data['damage_type_id']

    connection = connect_to_db()
    if connection:
        try:
            with connection.cursor(dictionary=True) as cursor:
                # Fetch Insurance Rate from insurance_companies table
                cursor.execute("SELECT InsuranceRate FROM insurance_companies WHERE id = %s", (company_id,))
                insurance_company_result = cursor.fetchone()
                if not insurance_company_result:
                    return jsonify({"error": "Insurance company not found."}), 404
                insurance_rate = insurance_company_result['InsuranceRate']

                # Fetch Coverage Percentage from insurance_policy_types table
                cursor.execute("SELECT CoveragePercentage FROM insurance_policy_types WHERE id = %s", (policy_type_id,))
                policy_type_result = cursor.fetchone()
                if not policy_type_result:
                    return jsonify({"error": "Policy type not found."}), 404
                coverage_percentage = policy_type_result['CoveragePercentage']

                # Fetch Severity Factor from damage_severity table
                cursor.execute("SELECT SeverityFactor FROM damage_severity WHERE level = %s", (severity_level,))
                severity_result = cursor.fetchone()
                if not severity_result:
                    return jsonify({"error": "Severity level not found."}), 404
                severity_factor = severity_result['SeverityFactor']

                # Fetch Damage Multiplier from damage_types table
                cursor.execute("SELECT multiplier FROM damage_types WHERE id = %s", (damage_type_id,))
                damage_type_result = cursor.fetchone()
                if not damage_type_result:
                    return jsonify({"error": "Damage type not found."}), 404
                damage_multiplier = damage_type_result['multiplier']

                # Calculate claimable amount using the formula
                claimable_amount = (
                    estimated_repair_cost 
                    * (insurance_rate / 100)  # Convert InsuranceRate to a percentage
                    * (coverage_percentage / 100)  # Convert CoveragePercentage to a percentage
                    * severity_factor 
                    * damage_multiplier
                )

                # Return the result
                response = {
                    "company_id": company_id,
                    "policy_type_id": policy_type_id,
                    "severity_level": severity_level,
                    "estimated_repair_cost": estimated_repair_cost,
                    "claimable_amount": claimable_amount
                }
                return jsonify(response), 200
        except connector.Error as e:
            print(f"Error executing query: {e}")
            return jsonify({"error": "An error occurred while calculating the claim."}), 500
        finally:
            connection.close()  # Ensure the connection is closed
    else:
        return jsonify({"error": "Database connection failed."}), 500

# Helper function to fetch part prices
def get_part_prices(email, class_counts):
    connection = connect_to_db()
    if connection:
        try:
            with connection.cursor(dictionary=True) as cursor:
                # Get user's car brand and model
                cursor.execute("SELECT car_brand, model FROM user_info WHERE email = %s", (email,))
                user_data = cursor.fetchone()
                if not user_data:
                    print("User not found")
                    return {}

                car_brand = user_data['car_brand']
                car_model = user_data['model']

                # Fetch part prices
                prices = {}
                for class_id, count in class_counts.items():
                    part_name = get_part_name_from_id(class_id)
                    if part_name:
                        cursor.execute(
                            "SELECT price FROM car_models WHERE brand = %s AND model = %s AND part = %s",
                            (car_brand, car_model, part_name)
                        )
                        price_data = cursor.fetchone()
                        if price_data:
                            price_per_part = price_data['price']
                            total_price = price_per_part * count
                            prices[part_name] = {'count': count, 'price': price_per_part, 'total': total_price}
                return prices
        except connector.Error as e:
            print(f"Error executing query: {e}")
            return {}
    print("Connection failed")
    return {}

# Helper function to get part name from class ID
def get_part_name_from_id(class_id):
    class_names = ['Bonnet', 'Bumper', 'Dickey', 'Door', 'Fender', 'Light', 'Windshield']
    if 0 <= class_id < len(class_names):
        return class_names[int(class_id)]
    return None

# Run the app
if __name__ == '__main__':
    app.run(debug=True)