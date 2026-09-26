.PHONY: demo eval app test lint

demo:
	uv run python -m anvesha.synth.persona

eval: demo
	uv run python eval/score.py

app: demo
	uv run streamlit run app/streamlit_app.py

test:
	uv run pytest -q

lint:
	uv run ruff check . && uv run ruff format .
