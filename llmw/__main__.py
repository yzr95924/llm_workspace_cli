"""支持 `python -m llmw ...` 调用"""
import sys
from llmw.cli import main

if __name__ == "__main__":
    sys.exit(main())