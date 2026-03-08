import json

from quizlet_exporter import extract_flashcards, extract_next_data_json


def test_extract_next_data_json():
    data = {"props": {"pageProps": {"foo": "bar"}}}
    html = f"""
    <html><body>
      <script id=\"__NEXT_DATA__\" type=\"application/json\">{json.dumps(data)}</script>
    </body></html>
    """

    parsed = extract_next_data_json(html)
    assert parsed == data


def test_extract_flashcards_from_card_sides_shape():
    next_data = {
        "props": {
            "pageProps": {
                "set": {
                    "items": [
                        {"cardSides": [{"label": "cat"}, {"label": "gato"}]},
                        {"cardSides": [{"label": "dog"}, {"label": "perro"}]},
                    ]
                }
            }
        }
    }

    cards = extract_flashcards(next_data)
    assert ("cat", "gato") in cards
    assert ("dog", "perro") in cards
