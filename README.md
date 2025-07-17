# Kasta Feed

This repository contains a Flask-based service to generate an XML feed compatible with Kasta marketplace:
- **/export/kasta.xml** - endpoint to fetch the generated feed.

## Setup

1. **Clone** this repo and navigate into it.
2. **Create** a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
3. **Install** dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. **Set** environment variables:
   - `KEYCRM_API_KEY` - your KeyCRM API key.
   - `KEYCRM_API_URL` - (optional) default is `https://openapi.keycrm.app/v1`.
5. **Run** locally:
   ```bash
   python main.py
   ```
6. **Deploy** on Render or any hosting:
   - Build: `pip install -r requirements.txt`
   - Start: `gunicorn main:app --bind 0.0.0.0:$PORT`

## License

MIT
