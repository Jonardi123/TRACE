import io
import shutil
import pytest
from PIL import Image, ImageDraw, ImageFont
from osint_workbench.evidence import screenshot_text


def test_real_tesseract_transcription():
    if not shutil.which('tesseract'):
        pytest.skip('Tesseract executable not installed')
    image = Image.new('RGB', (1400,180), 'white')
    ImageDraw.Draw(image).text((40,45), 'AUTHORIZED EVIDENCE 12345', fill='black',
                              font=ImageFont.load_default(size=42))
    raw = io.BytesIO()
    image.save(raw, format='PNG')
    text, confidence, warnings = screenshot_text(raw.getvalue())
    assert 'AUTHORIZED' in text and '12345' in text
    assert confidence is not None and confidence > 50
