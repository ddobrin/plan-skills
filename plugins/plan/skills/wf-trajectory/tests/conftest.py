import os
import sys

# Make the skill dir (parent of tests/) importable as top-level modules.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
