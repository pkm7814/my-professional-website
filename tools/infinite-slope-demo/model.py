"""Infinite slope with seepage parallel to the slope (analytical).

    sigma_n = gamma z cos^2(beta)            normal stress on slip plane
    u       = m z gamma_w cos^2(beta)        pore pressure
    tau_d   = gamma z sin(beta) cos(beta)    driving shear stress
    tau_f   = c' + (sigma_n - u) tan(phi')   available shear strength
    FS      = tau_f / tau_d

Pure Python (no numpy) so it loads instantly in the browser and runs in tests.
"""
from math import cos, radians, sin, tan

GAMMA_W = 9.81  # kN/m3


def factor_of_safety(c, phi, gamma, z, m, beta):
    b, p = radians(beta), radians(phi)
    sigma_n = gamma * z * cos(b) ** 2
    u = m * z * GAMMA_W * cos(b) ** 2
    tau_d = gamma * z * sin(b) * cos(b)
    tau_f = c + max(sigma_n - u, 0.0) * tan(p)
    return {"fs": tau_f / tau_d, "sigma_n": sigma_n, "u": u, "tau_d": tau_d, "tau_f": tau_f}


def _status(fs):
    return "fail" if fs < 1.0 else ("warn" if fs < 1.5 else "ok")


def _range(a, b, n):
    return [a + (b - a) * i / (n - 1) for i in range(n)]


def compute(inputs):
    c, phi, gamma = float(inputs["c"]), float(inputs["phi"]), float(inputs["gamma"])
    z, m, beta = float(inputs["z"]), float(inputs["m"]), float(inputs["beta"])
    if not 0 < beta < 90:
        raise ValueError("Slope angle must be between 0° and 90°.")
    if gamma <= GAMMA_W * m:
        raise ValueError("Unit weight must exceed γw·m for a meaningful effective stress.")

    r = factor_of_safety(c, phi, gamma, z, m, beta)

    # FS vs slope angle for three water conditions (multi-line, different styles) + driving stress on y2
    betas = _range(5, 70, 66)
    series = []
    for label, mm, dash, marker in (("Dry (m = 0)", 0.0, "solid", "circle"),
                                    (f"Current (m = {m:g})", m, "dash", "square"),
                                    ("Saturated (m = 1)", 1.0, "dot", "diamond")):
        series.append({"name": label, "x": betas, "dash": dash, "marker": marker, "mode": "lines",
                       "y": [factor_of_safety(c, phi, gamma, z, mm, bb)["fs"] for bb in betas]})
    series.append({"name": "Driving shear stress τd", "axis": "y2", "x": betas, "dash": "longdash",
                   "y": [factor_of_safety(c, phi, gamma, z, m, bb)["tau_d"] for bb in betas], "color": "#6b7280"})
    series.append({"name": "Current design point", "x": [beta], "y": [r["fs"]], "mode": "markers",
                   "marker": "x", "size": 13, "color": "#dc2626"})

    fig1 = {"title": "Factor of safety vs slope angle", "x_label": "Slope angle β (°)",
            "y_label": "Factor of safety F<sub>s</sub>", "y2_label": "τ<sub>d</sub> (kPa)",
            "series": series, "hlines": [{"y": 1.0, "label": "F<sub>s</sub> = 1"}],
            "vlines": [{"x": phi, "label": "β = φ′"}]}

    # FS and shear stresses vs depth
    depths = _range(max(0.2, z / 10), max(2 * z, 1.0), 40)
    rows = [factor_of_safety(c, phi, gamma, d, m, beta) for d in depths]
    fig2 = {"title": "Factor of safety and stresses vs depth", "x_label": "Depth z (m)",
            "y_label": "Factor of safety F<sub>s</sub>", "y2_label": "Stress (kPa)",
            "series": [
                {"name": "F<sub>s</sub>", "x": depths, "y": [q["fs"] for q in rows], "mode": "lines+markers", "marker": "circle", "size": 5},
                {"name": "τ<sub>f</sub> (strength)", "axis": "y2", "x": depths, "y": [q["tau_f"] for q in rows], "dash": "dash"},
                {"name": "τ<sub>d</sub> (driving)", "axis": "y2", "x": depths, "y": [q["tau_d"] for q in rows], "dash": "dot"},
            ],
            "hlines": [{"y": 1.0, "label": "F<sub>s</sub> = 1"}]}

    table = {"title": "Factor of safety at selected slope angles", "digits": 3,
             "columns": ["β (°)", "σn (kPa)", "u (kPa)", "τd (kPa)", "τf (kPa)", "FS"],
             "rows": [[bb, q["sigma_n"], q["u"], q["tau_d"], q["tau_f"], q["fs"]]
                      for bb in (10, 15, 20, 25, 30, 35, 40, 45, 50)
                      for q in [factor_of_safety(c, phi, gamma, z, m, bb)]]}

    messages = []
    if c == 0 and m == 0:
        messages.append("Cohesionless dry slope: FS = tan φ′ / tan β, independent of depth.")
    if r["fs"] < 1:
        messages.append("FS < 1 — the slope is unstable for these parameters.")

    return {
        "summary": [
            {"label": "Factor of safety", "value": r["fs"], "status": _status(r["fs"])},
            {"label": "Driving stress τd", "value": r["tau_d"], "unit": "kPa", "digits": 2},
            {"label": "Shear strength τf", "value": r["tau_f"], "unit": "kPa", "digits": 2},
            {"label": "Pore pressure u", "value": r["u"], "unit": "kPa", "digits": 2},
        ],
        "figures": [fig1, fig2],
        "tables": [table],
        "messages": messages,
    }
