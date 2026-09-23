from reporting import render_report


def test_unknown_metrics_are_null():
    report = render_report({"status": "completed", "campaigns": [], "trace": [], "metrics": {}})
    assert "net_arpu_gain: null" in report
    assert "Status: completed" in report
