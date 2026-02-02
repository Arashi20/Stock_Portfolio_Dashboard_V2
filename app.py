from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os
import yfinance as yf
import requests
from dcf.dcf_default import dcf_valuation_advanced

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///stocks.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Session timeout configuration (15 minutes of inactivity)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=15)

# Hardcoded credentials (for development only)
HARDCODED_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
HARDCODED_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'stockanalysis2026')

# OpenExchange API Key for currency conversion
OPENEXCHANGE_API_KEY = os.environ.get('OPENEXCHANGE_API_KEY', '')

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
    if current_user.is_authenticated:
        session.permanent = True
        app.permanent_session_lifetime = timedelta(minutes=15)

# Currency conversion helper function
def convert_to_eur(amount, currency_symbol):
    """Convert amount from given currency symbol to EUR"""
    if not OPENEXCHANGE_API_KEY:
        return None
    
    # Mapping from currency symbols to currency codes
    currency_map = {
        '$': 'USD',
        '€': 'EUR',
        '£': 'GBP',
        '¥': 'JPY',
        '₹': 'INR',
        'C$': 'CAD',
        'A$': 'AUD',
        'CHF': 'CHF',
        'CNY': 'CNY',
        'SEK': 'SEK',
        'NZD': 'NZD',
        'MXN': 'MXN',
        'SGD': 'SGD',
        'HKD': 'HKD',
        'NOK': 'NOK',
        'KRW': 'KRW',
        'TRY': 'TRY',
        'RUB': 'RUB',
        'BRL': 'BRL',
        'ZAR': 'ZAR',
        'SAR': 'SAR'
    }
    
    currency_code = currency_map.get(currency_symbol, 'USD')
    
    # If already in EUR, return the amount
    if currency_code == 'EUR':
        return amount
    
    try:
        # Get exchange rates from OpenExchange API
        url = f"https://openexchangerates.org/api/latest.json?app_id={OPENEXCHANGE_API_KEY}"
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            rates = data.get('rates', {})
            
            # OpenExchange uses USD as base, so we need to convert:
            # 1. From currency_code to USD
            # 2. From USD to EUR
            if currency_code in rates and 'EUR' in rates:
                usd_amount = amount / rates[currency_code]
                eur_amount = usd_amount * rates['EUR']
                return round(eur_amount, 2)
        
        return None
    except Exception as e:
        print(f"Error converting currency: {e}")
        return None

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
    currency = db.Column(db.String(10), default='$')
    date_created = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<DCFAnalysis {self.ticker}>'

class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticker = db.Column(db.String(10), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    notes = db.Column(db.Text, nullable=False)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Report {self.ticker}>'

class Wishlist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticker = db.Column(db.String(10), nullable=False, unique=True)
    target_price = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(10), default='$')
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
            # Remember me extends to 30 days, otherwise 15 minutes
            duration = timedelta(days=30) if remember else timedelta(minutes=15)
            login_user(user, remember=remember, duration=duration)
            session.permanent = True
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
    # Fetch all saved analyses ordered by most recent first
    saved_analyses = DCFAnalysis.query.order_by(DCFAnalysis.date_created.desc()).all()
    return render_template('dcf.html', saved_analyses=saved_analyses)

@app.route('/calculate-dcf', methods=['POST'])
@login_required
def calculate_dcf():
    """Calculate DCF intrinsic value"""
    try:
        # Get form data
        ticker = request.form.get('ticker', '').upper().strip()
        print(f"DEBUG: Received ticker from form: '{request.form.get('ticker')}'")
        print(f"DEBUG: Processed ticker: '{ticker}'")
        free_cash_flow = float(request.form.get('free_cash_flow'))
        growth_rate_5yr = float(request.form.get('growth_rate_5yr'))
        growth_rate_6_10yr = float(request.form.get('growth_rate_6_10yr'))
        terminal_growth_rate = float(request.form.get('terminal_growth_rate'))
        discount_rate = float(request.form.get('discount_rate'))
        shares_outstanding = float(request.form.get('shares_outstanding'))
        share_dilution = float(request.form.get('share_dilution'))
        currency = request.form.get('currency', '$')  # Get manual currency input
        
        # Calculate intrinsic value using DCF model
        intrinsic_value = dcf_valuation_advanced(
            initial_fcf=free_cash_flow,
            growth_rate_1_5=growth_rate_5yr,
            growth_rate_6_10=growth_rate_6_10yr,
            discount_rate=discount_rate,
            terminal_growth_rate=terminal_growth_rate,
            shares_outstanding=shares_outstanding,
            share_change_rate=share_dilution
        )
        
        # Get current stock price from Yahoo Finance (using method from working project)
        current_price = None
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            current_price = info.get("regularMarketPrice")
            if current_price:
                print(f"Found price for {ticker}: {current_price}")
        except Exception as e:
            print(f"Error fetching price for {ticker}: {e}")
            pass
        
        # Prepare result data
        result = {
            'ticker': ticker,
            'free_cash_flow': free_cash_flow,
            'growth_rate_5yr': growth_rate_5yr,
            'growth_rate_6_10yr': growth_rate_6_10yr,
            'terminal_growth_rate': terminal_growth_rate,
            'discount_rate': discount_rate,
            'shares_outstanding': shares_outstanding,
            'share_dilution': share_dilution,
            'intrinsic_value': intrinsic_value,
            'current_price': current_price,
            'currency': currency,        
            'intrinsic_value': intrinsic_value,
            'current_price': current_price
        }
        
        flash(f'DCF calculation completed for {ticker}!', 'success')
        return render_template('dcf.html', result=result, **request.form)
        
    except ValueError as e:
        flash(f'Calculation error: {str(e)}', 'danger')
        return render_template('dcf.html', **request.form)
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'danger')
        return render_template('dcf.html', **request.form)

@app.route('/save-dcf-analysis', methods=['POST'])
@login_required
def save_dcf_analysis():
    """Save DCF analysis to database"""
    try:
        analysis = DCFAnalysis(
            ticker=request.form.get('ticker'),
            free_cash_flow=float(request.form.get('free_cash_flow')),
            growth_rate_5yr=float(request.form.get('growth_rate_5yr')),
            growth_rate_6_10yr=float(request.form.get('growth_rate_6_10yr')),
            terminal_growth_rate=float(request.form.get('terminal_growth_rate')),
            discount_rate=float(request.form.get('discount_rate')),
            shares_outstanding=float(request.form.get('shares_outstanding')),
            share_dilution=float(request.form.get('share_dilution')),
            intrinsic_value=float(request.form.get('intrinsic_value')),
            currency=request.form.get('currency', '$')
        )
        db.session.add(analysis)
        db.session.commit()
        flash(f'DCF analysis for {analysis.ticker} saved successfully!', 'success')
    except Exception as e:
        flash(f'Error saving analysis: {str(e)}', 'danger')
    
    return redirect(url_for('dcf'))

@app.route('/delete-dcf-analysis/<int:id>', methods=['POST'])
@login_required
def delete_dcf_analysis(id):
    """Delete a saved DCF analysis"""
    try:
        analysis = DCFAnalysis.query.get_or_404(id)
        ticker = analysis.ticker  # Save for flash message
        db.session.delete(analysis)
        db.session.commit()
        flash(f'Analysis for {ticker} deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting analysis: {str(e)}', 'danger')
    
    return redirect(url_for('dcf'))

@app.route('/api/stock-lookup/<ticker>')
@login_required
def stock_lookup(ticker):
    """API endpoint to search saved DCF analyses for a ticker"""
    try:
        # Search database for saved DCF analyses for this ticker
        analyses = DCFAnalysis.query.filter_by(ticker=ticker.upper()).order_by(DCFAnalysis.date_created.desc()).all()
        
        if not analyses:
            return jsonify({'error': f'No saved analyses found for {ticker}'}), 404
        
        # Return list of saved analyses
        data = {
            'ticker': ticker.upper(),
            'count': len(analyses),
            'analyses': [
                {
                    'id': analysis.id,
                    'date': analysis.date_created.strftime('%Y-%m-%d %H:%M'),
                    'free_cash_flow': analysis.free_cash_flow,
                    'shares_outstanding': analysis.shares_outstanding,
                    'growth_rate_5yr': analysis.growth_rate_5yr,
                    'growth_rate_6_10yr': analysis.growth_rate_6_10yr,
                    'terminal_growth_rate': analysis.terminal_growth_rate,
                    'discount_rate': analysis.discount_rate,
                    'share_dilution': analysis.share_dilution,
                    'intrinsic_value': analysis.intrinsic_value,
                    'currency': analysis.currency
                }
                for analysis in analyses
            ]
        }
        
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': f'Error searching for {ticker}: {str(e)}'}), 500

def format_market_cap(value):
    """Format market cap to readable string"""
    if value >= 1e12:
        return f"{value/1e12:.2f}T"
    elif value >= 1e9:
        return f"{value/1e9:.2f}B"
    elif value >= 1e6:
        return f"{value/1e6:.2f}M"
    else:
        return f"{value:,.0f}"

@app.route('/reports')
@login_required
def reports():
    """Reports listing page"""
    all_reports = Report.query.order_by(Report.date_created.desc()).all()
    return render_template('reports.html', reports=all_reports)

@app.route('/create-report', methods=['POST'])
@login_required
def create_report():
    """Create a new report"""
    try:
        ticker = request.form.get('ticker', '').upper().strip()
        title = request.form.get('title', '').strip()
        date_str = request.form.get('date')
        notes = request.form.get('notes', '').strip()
        
        if not ticker or not title or not notes:
            flash('Please fill in all required fields.', 'danger')
            return redirect(url_for('reports'))
        
        # Parse the date
        report_date = datetime.strptime(date_str, '%Y-%m-%d')
        
        # Create new report
        new_report = Report(
            ticker=ticker,
            title=title,
            date=report_date,
            notes=notes
        )
        db.session.add(new_report)
        db.session.commit()
        flash(f'Report for {ticker} created successfully!', 'success')
    except ValueError as e:
        flash('Invalid date format.', 'danger')
    except Exception as e:
        db.session.rollback()
        flash(f'Error creating report: {str(e)}', 'danger')
    
    return redirect(url_for('reports'))

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
        try:
            report.ticker = request.form.get('ticker', '').upper().strip()
            report.title = request.form.get('title', '').strip()
            report.date = datetime.strptime(request.form.get('date'), '%Y-%m-%d')
            report.notes = request.form.get('notes', '').strip()
            db.session.commit()
            flash('Report updated successfully!', 'success')
            return redirect(url_for('view_report', report_id=report.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating report: {str(e)}', 'danger')
    return render_template('edit_report.html', report=report)

@app.route('/delete-report/<int:report_id>', methods=['POST'])
@login_required
def delete_report(report_id):
    """Delete a report"""
    try:
        report = Report.query.get_or_404(report_id)
        ticker = report.ticker
        db.session.delete(report)
        db.session.commit()
        flash(f'Report for {ticker} deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting report: {str(e)}', 'danger')
    
    return redirect(url_for('reports'))


@app.route('/wishlist')
@login_required
def wishlist():
    """Wishlist page"""
    wishlist_items = Wishlist.query.order_by(Wishlist.date_added.desc()).all()
    
    # Fetch current prices and convert target prices to EUR
    for item in wishlist_items:
        try:
            stock = yf.Ticker(item.ticker)
            info = stock.info
            current_price = info.get("regularMarketPrice") or info.get("currentPrice") or info.get("previousClose")
            item.current_price = current_price
        except Exception as e:
            print(f"Error fetching price for {item.ticker}: {e}")
            item.current_price = None
        
        # Convert target price to EUR
        item.target_price_eur = convert_to_eur(item.target_price, item.currency)
    
    return render_template('wishlist.html', wishlist=wishlist_items)

@app.route('/add-to-wishlist', methods=['POST'])
@login_required
def add_to_wishlist():
    """Add a stock to the wishlist"""
    try:
        ticker = request.form.get('ticker', '').upper().strip()
        target_price = float(request.form.get('target_price'))
        currency = request.form.get('currency', '$')
        
        if not ticker:
            flash('Please enter a ticker symbol.', 'danger')
            return redirect(url_for('wishlist'))
        
        # Check if ticker already exists in wishlist
        existing = Wishlist.query.filter_by(ticker=ticker).first()
        if existing:
            flash(f'{ticker} is already in your wishlist.', 'warning')
            return redirect(url_for('wishlist'))
        
        # Add to wishlist
        wishlist_item = Wishlist(
            ticker=ticker,
            target_price=target_price,
            currency=currency
        )
        db.session.add(wishlist_item)
        db.session.commit()
        flash(f'{ticker} added to wishlist successfully!', 'success')
    except ValueError:
        flash('Please enter a valid target price.', 'danger')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding to wishlist: {str(e)}', 'danger')
    
    return redirect(url_for('wishlist'))

@app.route('/delete-wishlist/<int:id>', methods=['POST'])
@login_required
def delete_wishlist(id):
    """Delete a stock from the wishlist"""
    try:
        wishlist_item = Wishlist.query.get_or_404(id)
        ticker = wishlist_item.ticker  # Save for flash message
        db.session.delete(wishlist_item)
        db.session.commit()
        flash(f'{ticker} removed from wishlist successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error removing from wishlist: {str(e)}', 'danger')
    
    return redirect(url_for('wishlist'))

# Initialize database tables
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=False)
