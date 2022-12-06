from dotenv import load_dotenv
from os import getenv as env
from pathlib import Path

load_dotenv()

rootdir = env("ROOTDIR")
definitionsfile = env("DEFINITIONS")
templatefile = env("TEMPLATE")
fieldsfile = env("FIELDS")
host = env("HOST")
token = env("TOKEN")

root = Path(rootdir)
setup_root = root / "setup"
merged_root = root / "merged"
