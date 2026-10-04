# Copy to clawd_secrets.py (git-ignored) and list your 2.4 GHz WiFi networks as (name, password).
# At boot Clawd joins the strongest one in range; if an hourly check fails he tries the next one.
NETWORKS = [
    ("home-network-name", "home-password"),
    ("work-network-name", "work-password"),
]
