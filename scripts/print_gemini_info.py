import pkgutil
import importlib
import sys
from pathlib import Path

# Ensure project root is on sys.path so `import app` works when running from scripts/
project_root = str(Path(__file__).resolve().parents[1])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.config import settings
s = settings
print('GEMINI_API_KEY:', 'SET' if s.GEMINI_API_KEY else 'MISSING')
print('GEMINI_MODEL:', s.GEMINI_MODEL)
print('GEMINI_TIMEOUT:', s.GEMINI_TIMEOUT)
print('google-generativeai installed:', 'yes' if pkgutil.find_loader('google.generativeai') else 'no')
try:
    import google.generativeai as genai
    print('genai.__version__ =', getattr(genai, '__version__', 'unknown'))
except Exception as e:
    print('genai import failed:', e)
