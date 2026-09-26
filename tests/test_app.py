from streamlit.testing.v1 import AppTest


def test_demo_family_runs_end_to_end():
    at = AppTest.from_file("../app/streamlit_app.py", default_timeout=60)
    at.run()
    assert not at.exception
    at.radio[0].set_value("none").run()
    at.button[0].click().run()
    assert not at.exception
    text = " ".join(m.value for m in at.markdown) + " ".join(s.value for s in at.subheader)
    assert "Assets" in text and "Liabilities" in text and "This week" in text
    assert any("not legal or financial advice" in i.value for i in at.info)
    assert any("Still being debited" in w.value for w in at.warning)
