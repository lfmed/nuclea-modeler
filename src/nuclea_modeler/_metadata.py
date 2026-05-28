from pathlib import Path

app_name = "nuclea-modeler"
app_entrypoint = "nuclea_modeler.backend.app:app"
app_slug = "nuclea_modeler"
api_prefix = "/api"
dist_dir = Path(__file__).parent / "__dist__"
