"""
Product Sentiment Analyzer and Review Dashboard
Flask Backend API
"""
from flask import Flask, jsonify, request, render_template, send_from_directory
from flask_cors import CORS
import pandas as pd
import os

from database import Database
from sentiment_analyzer import SentimentAnalyzer
from scraper import ReviewScraper, is_valid_product

app = Flask(__name__)
CORS(app)

db = Database()
analyzer = SentimentAnalyzer()
scraper = ReviewScraper()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/service-worker.js')
def service_worker():
    # Served from root (not /static/) so its PWA scope covers the whole app
    return send_from_directory(
        os.path.join(app.root_path, 'static'),
        'service-worker.js',
        mimetype='application/javascript'
    )


@app.route('/api/scrape', methods=['POST'])
def scrape_product():
    """
    Body: { "product_name": "iPhone 15", "source": "flipkart", "use_mock": true }
    Set use_mock=false to attempt a real Selenium scrape (requires Chrome installed).
    """
    data = request.get_json(force=True)
    product_name = (data.get('product_name') or '').strip()
    source = (data.get('source') or 'flipkart').lower()
    use_mock = data.get('use_mock', True)

    if not product_name:
        return jsonify({'error': 'product_name is required'}), 400

    if not is_valid_product(product_name):
        return jsonify({
            'error': 'Invalid product',
            'message': f'"{product_name}" doesn\'t look like a real product. '
                       f'Try a proper product name (e.g. "iPhone 16", "Boat Headphones").'
        }), 422

    if use_mock:
        raw_reviews = scraper.generate_mock_reviews(product_name)
    else:
        raw_reviews = scraper.scrape_reviews(product_name, source)

    if not raw_reviews:
        return jsonify({'error': 'No reviews found / scraping failed'}), 404

    product_id = db.add_product(product_name, source)

    analyzed = []
    for r in raw_reviews:
        result = analyzer.analyze(r['text'])
        r.update(result)
        analyzed.append(r)

    db.add_reviews(product_id, analyzed)

    return jsonify({
        'product_id': product_id,
        'product_name': product_name,
        'reviews_added': len(analyzed)
    })


@app.route('/api/products', methods=['GET'])
def get_products():
    return jsonify(db.get_products())


@app.route('/api/reviews/<int:product_id>', methods=['GET'])
def get_reviews(product_id):
    return jsonify(db.get_reviews(product_id))


@app.route('/api/analytics/<int:product_id>', methods=['GET'])
def get_analytics(product_id):
    reviews = db.get_reviews(product_id)
    if not reviews:
        return jsonify({'error': 'No reviews found for this product'}), 404

    df = pd.DataFrame(reviews)

    sentiment_counts = df['sentiment'].value_counts().to_dict()

    df['date'] = pd.to_datetime(df['date'])
    trend_df = (
        df.groupby([df['date'].dt.to_period('M').astype(str), 'sentiment'])
        .size()
        .unstack(fill_value=0)
        .reset_index()
        .rename(columns={'date': 'month'})
    )
    trend = trend_df.to_dict('records')

    word_freq = analyzer.get_word_frequency(df['text'].tolist())

    return jsonify({
        'sentiment_distribution': sentiment_counts,
        'trend': trend,
        'word_frequency': word_freq,
        'average_score': round(float(df['score'].mean()), 3),
        'total_reviews': len(df)
    })


if __name__ == '__main__':
    app.run(debug=True, port=5000)
