from flask import Flask ,render_template
import subprocess
import sys

# Create an instance of the Flask class
app = Flask(__name__)

# Define a route and a view function
@app.route('/')
def hello_world():
    return render_template('index.html')

# This block allows you to run the app directly

@app.route('/user/<names>')
def greet_user(names):
    return f'Hello, {names}!'

@app.route('/run_kai')
def run_kai():
    try:
        result = subprocess.Popen([sys.executable, 'kai.py'],)
        return f'KAI script executed successfully. Output: {result.stdout}' 
        
    except subprocess.CalledProcessError as e:
        return f'Error executing KAI script: {e.stderr}'
    
@app.route('/sleep')
def sleep():
    try:
        result = subprocess.Popen([sys.executable, 'sleep.py'],)
        return f'Sleep script executed successfully. Output: {result.stdout}' 
        
    except subprocess.CalledProcessError as e:
        return f'Error executing Sleep script: {e.stderr}'
    
if __name__ == '__main__':
    app.run(debug=True)