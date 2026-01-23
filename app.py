from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///stocks.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
db = SQLAlchemy(app)

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
    current_price = db.Column(db.Float)
    date_added = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Wishlist {self.ticker}>'

# Routes
@app.route('/')
def home():
    """Home page with overview and quick links"""
    return render_template('home.html')

@app.route('/dcf')
def dcf():
    """DCF analysis page"""
    return render_template('dcf.html')

@app.route('/reports')
def reports():
    """Reports listing page"""
    all_reports = Report.query.order_by(Report.date_created.desc()).all()
    return render_template('reports.html', reports=all_reports)

@app.route('/wishlist')
def wishlist():
    """Wishlist page"""
    wishlist_items = Wishlist.query.order_by(Wishlist.date_added.desc()).all()
    return render_template('wishlist.html', wishlist=wishlist_items)

# Initialize database tables
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)
