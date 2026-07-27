import os

from pos_app import create_app
from pos_app.runtime_paths import load_runtime_config


app = create_app()


if __name__ == "__main__":
    config = load_runtime_config(os.path.dirname(os.path.abspath(__file__)))
    app.run(host=config.host, port=config.port, debug=False)
