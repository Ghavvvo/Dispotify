import subprocess
import sys
from pathlib import Path

proto_dir = Path(__file__).parent
proto_files = list(proto_dir.glob("*.proto"))

for proto_file in proto_files:
    cmd = [
        sys.executable, "-m", "grpc_tools.protoc",
        f"--proto_path={proto_dir}",
        f"--python_out={proto_dir}",
        f"--grpc_python_out={proto_dir}",
        str(proto_file)
    ]
    subprocess.run(cmd, check=True)
