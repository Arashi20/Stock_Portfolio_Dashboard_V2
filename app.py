from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from datetime import datetime, timedelta
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///stocks.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Session timeout configuration (15 minutes of inactivity)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=15)

# Hardcoded credentials (for development only)
HARDCODED_USERNAME = 'admin'
HARDCODED_PASSWORD = 'stockanalysis2026'

# Initialize database
db = SQLAlchemy(app)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'

# User class for Flask-Login
class User(UserMixin):
    def __init__(self, id, username):
        self.id = id
        self.username = username

@login_manager.user_loader
def load_user(user_id):
    if user_id == '1':
        return User(1, HARDCODED_USERNAME)
    return None

# Session management - 15 minute timeout
@app.before_request
def before_request():
    session.permanent = True
    app.permanent_session_lifetime = timedelta(minutes=15)
    session.modified = True

# Database Models
class DCFAnalysis(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticker = db.Column(db.String(10), nullable=False)
    free_cash_flow = db.Column(db.Float, nullable=False)
    growth_rate_5yr = db.Column(db.Float, nullable=False)
    growth_rate_6_10yr = db.Column(db.Float, nullable=False)
    terminal_growth_rate = db.Column(db.Float, nullable=False)
    discount_rate = db.Column(db.Float, nullable=False)
    shares_outstanding = db.Column(db.Float, nullable=False)
    share_dilution = db.Column(db.Float, nullable=False)
    intrinsic_value = db.Column(db.Float, nullable=False)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<DCFAnalysis {self.ticker}>'

class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticker = db.Column(db.String(10), nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    notes = db.Column(db.Text, nullable=False)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Report {self.ticker}>'

class Wishlist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticker = db.Column(db.String(10), nullable=False, unique=True)
    target_price = db.Column(db.Float, nullable=False)
    date_added = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Wishlist {self.ticker}>'

# Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = request.form.get('remember', False)
        
        if username == HARDCODED_USERNAME and password == HARDCODED_PASSWORD:
            user = User(1, username)
            login_user(user, remember=remember)
            session.permanent = True  # Enable session timeout
            flash('Login successful! Welcome back.', 'success')
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('home'))
        else:
            flash('Invalid username or password. Please try again.', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    """Logout user"""
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def home():
    """Home page with overview and quick links"""
    return render_template('home.html')

@app.route('/dcf')
@login_required
def dcf():
    """DCF analysis page"""
    return render_template('dcf.html')

@app.route('/reports')
@login_required
def reports():
    """Reports listing page"""
    all_reports = Report.query.order_by(Report.date_created.desc()).all()
    return render_template('reports.html', reports=all_reports)

@app.route('/report/<int:report_id>')
@login_required
def view_report(report_id):
    """View individual report"""
    report = Report.query.get_or_404(report_id)
    return render_template('view_report.html', report=report)

@app.route('/report/edit/<int:report_id>', methods=['GET', 'POST'])
@login_required
def edit_report(report_id):
    """Edit individual report"""
    report = Report.query.get_or_404(report_id)
    if request.method == 'POST':
        report.ticker = request.form['ticker']
        report.date = datetime.strptime(request.form['date'], '%Y-%m-%d')
        report.notes = request.form['notes']
        db.session.commit()
        flash('Report updated successfully!', 'success')
        return redirect(url_for('view_report', report_id=report.id))
    return render_template('edit_report.html', report=report)


@app.route('/wishlist')
@login_required
def wishlist():
    """Wishlist page"""
    wishlist_items = Wishlist.query.order_by(Wishlist.date_added.desc()).all()
    return render_template('wishlist.html', wishlist=wishlist_items)

# Initialize database tables
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)
