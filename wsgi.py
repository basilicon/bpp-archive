import sys
import os
from dotenv import load_dotenv

# Path to your project
path = '/home/basilicon/your_project_folder'
if path not in sys.path:
    sys.path.append(path)

load_dotenv(os.path.join(path, '.env'))

from app import app as application